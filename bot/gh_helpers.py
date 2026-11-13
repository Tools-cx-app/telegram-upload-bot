# Copyright (C) 2026 meta-magic_mount-rs developers
# SPDX-License-Identifier: GPL-v3

import json
import os
import subprocess
from asyncio import create_subprocess_exec
from fnmatch import fnmatchcase
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from . import cache, logger, settings


def get_artifacts() -> dict[str, str]:
    patterns = list(dict.fromkeys(
        pattern.strip()
        for line in settings.artifact_names.splitlines()
        for pattern in line.split(",")
        if pattern.strip()
    ))
    if not patterns:
        return {}
    if not settings.github_token:
        raise ValueError("A GitHub token with actions:read permission is required for artifact lookup")

    api_url = settings.github_api_url.rstrip("/")
    run_path = f"{settings.github_repository}/actions/runs/{settings.run_id}"
    found: dict[str, str] = {}
    page = 1
    while True:
        request = Request(
            f"{api_url}/repos/{run_path}/artifacts?per_page=100&page={page}",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {settings.github_token}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        try:
            with urlopen(request, timeout=30) as response:
                artifacts = json.load(response)["artifacts"]
        except HTTPError as exc:
            exc.close()
            raise RuntimeError(
                f"GitHub artifact lookup failed (HTTP {exc.code}); check actions:read permission"
            ) from exc
        except URLError as exc:
            raise RuntimeError(f"GitHub artifact lookup failed: {exc.reason}") from exc
        for artifact in artifacts:
            name = artifact["name"]
            if not artifact.get("expired", False) and any(
                fnmatchcase(name, pattern) for pattern in patterns
            ):
                found[name] = (
                    f"{settings.github_server_url.rstrip('/')}/{run_path}"
                    f"/artifacts/{artifact['id']}"
                )
        if len(artifacts) < 100:
            break
        page += 1

    missing = [
        pattern for pattern in patterns
        if not any(fnmatchcase(name, pattern) for name in found)
    ]
    if missing:
        raise ValueError(f"Artifacts not found or expired in this workflow run: {', '.join(missing)}")
    return {
        name: url
        for pattern in patterns
        for name, url in found.items()
        if fnmatchcase(name, pattern)
    }


async def get_git_root() -> Path | None:
    if cache.git_root:
        return cache.git_root

    configured_root = os.environ.get("GITHUB_WORKSPACE")
    candidates = [Path(configured_root)] if configured_root else []
    candidates.extend([Path.cwd(), Path(__file__).resolve().parents[3]])
    for candidate in candidates:
        if await _is_git_worktree(candidate):
            cache.git_root = candidate
            return cache.git_root

    logger.warning("No local Git worktree found; commit history is unavailable")
    return None


async def _is_git_worktree(path: Path) -> bool:
    if not path.is_dir():
        return False
    process = await create_subprocess_exec(
        "git",
        "rev-parse",
        "--is-inside-work-tree",
        cwd=path,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    stdout, _ = await process.communicate()
    return process.returncode == 0 and stdout.strip().decode("ascii", errors="ignore") == "true"


async def run_git(*args: str) -> str:
    git_root = await get_git_root()
    if not git_root:
        return ""
    try:
        process = await create_subprocess_exec(
            "git",
            *args,
            cwd=git_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
    except (FileNotFoundError, OSError) as e:
        logger.warning(f"Failed to run git {' '.join(args)}: {e}")
        return ""
    if process.returncode != 0:
        detail = stderr.decode("utf-8", errors="replace").strip()
        logger.warning(f"Git command failed: git {' '.join(args)}: {detail}")
        return ""
    return stdout.decode("utf-8", errors="replace")


def load_event_payload() -> dict:
    event_path = settings.github_event_path or os.environ.get("GITHUB_EVENT_PATH")
    if not event_path:
        logger.info("No GITHUB_EVENT_PATH configured")
        return {}
    path = Path(event_path)
    if not path.is_file():
        logger.warning(f"GITHUB_EVENT_PATH does not point to a valid file: {event_path}")
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            logger.info(f"Loaded event payload from {event_path} (keys: {list(data.keys())})")
            return data
    except Exception as e:
        logger.warning(f"Failed to read event payload from {event_path}: {e}")
        return {}


def get_commits_from_event(payload: dict) -> list[str]:
    commits = payload.get("commits", [])
    msgs: list[str] = []
    for commit in commits:
        sha = commit.get("id", "")
        message = commit.get("message", "")
        if sha and message:
            first_line = message.splitlines()[0]
            msgs.append(f"{sha[:7]} {first_line}")
    if not msgs and payload.get("head_commit"):
        head = payload["head_commit"]
        sha = head.get("id", "")
        message = head.get("message", "")
        if sha and message:
            first_line = message.splitlines()[0]
            msgs.append(f"{sha[:7]} {first_line}")
    # Return in newest-first order matching parse_git_log's input convention.
    return list(reversed(msgs))


def get_url_from_event(payload: dict) -> str:
    compare_url = payload.get("compare")
    before = payload.get("before")
    is_initial_push = before is not None and set(before) == {"0"}
    if compare_url and not is_initial_push and "000000000000" not in compare_url:
        return compare_url
    if payload.get("head_commit", {}).get("url"):
        return payload["head_commit"]["url"]
    repo = payload.get("repository", {}).get("full_name") or settings.github_repository
    sha = payload.get("after") or settings.github_sha
    return f"https://github.com/{repo}/commit/{sha}"


async def get_git_log(base: str, head: str) -> str:
    logger.info(f"Getting commit messages between {base} and {head}")
    if base == head:
        logger.info("Base and head are identical, skipping git log comparison")
        return ""
    output = await run_git(
        "log",
        "--reverse",
        "--format=%h %s",
        f"{base}..{head}",
    )
    if not output:
        return ""
    return "\n".join(line for line in output.splitlines() if line)

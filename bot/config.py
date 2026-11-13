# Copyright (C) 2026 meta-magic_mount-rs developers
# SPDX-License-Identifier: GPL-v3

PARSING_MAX_LEN = 800

TG_MSG_TEMPLATE_CI = """
New push to Github
{artifacts}<pre><code class="language-git">{commit_message}</code></pre>
See commit detail <a href="{commit_url}">here</a>
<a href="https://github.com/{github_repository}/actions/runs/{run_id}">#ci_{run_no}</a>
""".strip()
TG_MSG_EXPECTED_PARSE_MODE_CI = "html"

TG_MSG_TEMPLATE_RELEASE = """
New release available: <b>{name}</b>
{artifacts}<a href="{url}">Detail</a>
"""
TG_MSG_EXPECTED_PARSE_MODE_RELEASE = "html"

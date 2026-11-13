import io
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.error import HTTPError, URLError

from bot.gh_helpers import get_artifacts
from bot.msg_gen import generate_msg_ci, generate_msg_release
from bot.telegram import post


class TestArtifacts(unittest.TestCase):
    def setUp(self):
        self.settings = SimpleNamespace(
            artifact_names="linux, windows\nlinux",
            github_token="test-token",
            github_api_url="https://api.github.com",
            github_server_url="https://github.com",
            github_repository="test/repo",
            run_id=42,
        )
        self.settings_patch = patch("bot.gh_helpers.settings", self.settings
        )
        self.settings_patch.start()
        self.addCleanup(self.settings_patch.stop)

    def response(self, artifacts):
        return io.StringIO(json.dumps({"artifacts": artifacts}))

    def test_pagination_order_and_duplicates(self):
        first_page = [{"id": 2, "name": "windows", "expired": False}]
        first_page += [{"id": i + 10, "name": f"other-{i}"} for i in range(99)]
        with patch("bot.gh_helpers.urlopen", side_effect=[
            self.response(first_page),
            self.response([{"id": 1, "name": "linux", "expired": False}]),
        ]) as request:
            artifacts = get_artifacts()
        self.assertEqual(list(artifacts), ["linux", "windows"])
        self.assertEqual(
            artifacts["linux"],
            "https://github.com/test/repo/actions/runs/42/artifacts/1",
        )
        self.assertTrue(request.call_args_list[1].args[0].full_url.endswith("page=2"))
        self.assertEqual(
            request.call_args_list[0].args[0].get_header("Authorization"),
            "Bearer test-token",
        )

    def test_no_names_skips_api_and_token(self):
        self.settings.artifact_names = " \n, "
        self.settings.github_token = ""
        with patch("bot.gh_helpers.urlopen") as request:
            self.assertEqual(get_artifacts(), {})
        request.assert_not_called()

    def test_wildcard_matches_all_pages_and_deduplicates(self):
        self.settings.artifact_names = "app-*, app-linux\napp-*"
        first_page = [{"id": 1, "name": "app-linux"}]
        first_page += [{"id": i + 10, "name": f"other-{i}"} for i in range(99)]
        with patch("bot.gh_helpers.urlopen", side_effect=[
            self.response(first_page),
            self.response([
                {"id": 2, "name": "app-windows"},
                {"id": 3, "name": "app-old", "expired": True},
            ]),
        ]):
            self.assertEqual(list(get_artifacts()), ["app-linux", "app-windows"])

    def test_question_mark_character_set_and_case(self):
        self.settings.artifact_names = "app-?, build-[ab]"
        with patch("bot.gh_helpers.urlopen", return_value=self.response([
            {"id": 1, "name": "build-a"},
            {"id": 2, "name": "app-x"},
            {"id": 3, "name": "app-xy"},
            {"id": 4, "name": "App-y"},
            {"id": 5, "name": "build-c"},
        ])):
            self.assertEqual(list(get_artifacts()), ["app-x", "build-a"])

    def test_unmatched_wildcard_fails(self):
        self.settings.artifact_names = "app-*, missing-*"
        with patch("bot.gh_helpers.urlopen", return_value=self.response([
            {"id": 1, "name": "app-linux"},
            {"id": 2, "name": "missing-old", "expired": True},
        ])):
            with self.assertRaisesRegex(ValueError, r"not found or expired.*missing-\*"):
                get_artifacts()

    def test_missing_or_expired_artifacts_fail(self):
        for artifacts in ([], [{"id": 1, "name": "linux", "expired": True}]):
            with self.subTest(artifacts=artifacts), patch(
                "bot.gh_helpers.urlopen", return_value=self.response(artifacts)
            ):
                with self.assertRaisesRegex(ValueError, "not found or expired.*linux, windows"):
                    get_artifacts()

    def test_missing_token_fails_without_api_call(self):
        self.settings.github_token = ""
        with patch("bot.gh_helpers.urlopen") as request:
            with self.assertRaisesRegex(ValueError, "actions:read"):
                get_artifacts()
        request.assert_not_called()

    def test_api_errors(self):
        errors = [
            (HTTPError("https://api.github.com", 403, "Forbidden", {}, None), "HTTP 403"),
            (URLError("connection failed"), "connection failed"),
        ]
        for error, message in errors:
            with self.subTest(error=error), patch("bot.gh_helpers.urlopen", side_effect=error):
                with self.assertRaisesRegex(RuntimeError, message):
                    get_artifacts()


class TestArtifactMessages(unittest.IsolatedAsyncioTestCase):
    async def test_links_above_commit_and_html_escaped(self):
        payload = {
            "commits": [{"id": "abcdef123", "message": "Build app"}],
            "head_commit": {"url": "https://github.com/test/repo/commit/abcdef123"},
        }
        with patch("bot.msg_gen.load_event_payload", return_value=payload), patch(
            "bot.msg_gen.get_artifacts",
            return_value={'linux <app> & "tools"': "https://github.com/test/repo/actions/runs/42/artifacts/1"},
        ):
            message = await generate_msg_ci()
        self.assertLess(message.index("artifacts:"), message.index("<pre>"))
        self.assertIn('href="https://github.com/test/repo/actions/runs/42/artifacts/1"', message)
        self.assertIn("linux &lt;app&gt; &amp; &quot;tools&quot;", message)
        self.assertIn("Build app", message)

    async def test_release_includes_artifact_links(self):
        with patch("bot.msg_gen.load_event_payload", return_value={}), patch(
            "bot.msg_gen.settings", github_ref_name="v1.0.0", github_repository="test/repo"
        ), patch(
            "bot.msg_gen.get_artifacts",
            return_value={"app": "https://github.com/test/repo/actions/runs/42/artifacts/1"},
        ):
            message = await generate_msg_release()
        self.assertIn("v1.0.0", message)
        self.assertLess(message.index("artifacts:"), message.index(">Detail</a>"))

    async def test_custom_tags_are_above_ci_link(self):
        payload = {
            "commits": [{"id": "abcdef123", "message": "Build app"}],
            "head_commit": {"url": "https://github.com/test/repo/commit/abcdef123"},
        }
        with patch("bot.msg_gen.load_event_payload", return_value=payload), patch(
            "bot.msg_gen.get_artifacts", return_value={}
        ), patch("bot.msg_gen.settings", tags="preview, stable"):
            message = await generate_msg_ci()
        tags = "#preview\n#stable"
        self.assertIn(tags, message)
        self.assertLess(message.index(tags), message.index("#ci_42"))

    async def test_custom_tags_are_above_release_detail_link(self):
        with patch("bot.msg_gen.load_event_payload", return_value={}), patch(
            "bot.msg_gen.get_artifacts", return_value={}
        ), patch("bot.msg_gen.settings", github_ref_name="v1.0.0",
                 github_repository="test/repo", tags="preview, stable"):
            message = await generate_msg_release()
        tags = "#preview\n#stable"
        self.assertIn(tags, message)
        self.assertLess(message.index(tags), message.index(">Detail</a>"))

    async def test_only_sends_text(self):
        client = MagicMock()
        client.send_message = AsyncMock()
        client.send_document = AsyncMock()
        client.send_media_group = AsyncMock()
        with patch("bot.telegram.telegram.Bot") as bot, patch("bot.telegram.settings") as settings:
            settings.chat_id = 123
            bot.return_value.__aenter__.return_value = client
            await post("test message", "html")
        client.send_message.assert_awaited_once_with(123, text="test message", parse_mode="html")
        client.send_document.assert_not_called()
        client.send_media_group.assert_not_called()

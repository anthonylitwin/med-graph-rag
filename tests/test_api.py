from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest import mock


PROJECT_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = Path(__file__).resolve().parents[1] / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.services.qa_service import answer_question, get_active_model_runtime, get_app_model_profile


class ChatServiceTests(unittest.TestCase):
    def test_app_model_runtime_defaults_to_local_non_instruct(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            profile = get_app_model_profile()

        self.assertEqual(profile.name, "local-non-instruct")
        self.assertEqual(profile.qa_provider, "ollama")
        self.assertEqual(profile.extractor_provider, "non_instruct")

    def test_app_model_runtime_uses_launch_time_local_model(self) -> None:
        with mock.patch.dict(
            os.environ,
            {"APP_MODEL_PROFILE": "local-non-instruct", "LOCAL_MODEL": "qwen-custom"},
            clear=True,
        ):
            profile = get_app_model_profile()

        self.assertEqual(profile.name, "local-non-instruct")
        self.assertEqual(profile.qa_model, "qwen-custom")

    def test_model_options_reports_only_active_runtime(self) -> None:
        with mock.patch.dict(os.environ, {"APP_MODEL_PROFILE": "noop"}, clear=True):
            runtime = get_active_model_runtime()

        self.assertEqual(runtime["activeProfile"]["name"], "noop")
        self.assertNotIn("profiles", runtime)

    def test_answer_question_honors_noop_profile_metadata(self) -> None:
        with mock.patch.dict(os.environ, {"APP_MODEL_PROFILE": "noop"}, clear=True):
            result = answer_question("What risk may aspirin increase?", model_profile="frontier")

        self.assertEqual(result["provider"], "noop")
        self.assertEqual(result["modelProfile"], "noop")
        self.assertEqual(result["model"], "noop-language-model-v0")
        self.assertFalse(result["abstained"])

    def test_app_model_runtime_rejects_experiment_profiles(self) -> None:
        for profile_name in ("frontier", "openai", "api", "local-qwen25", "local-qwen3"):
            with self.subTest(profile_name=profile_name):
                with mock.patch.dict(os.environ, {"APP_MODEL_PROFILE": profile_name}, clear=True):
                    with self.assertRaisesRegex(ValueError, "reserved for experiments"):
                        get_app_model_profile()

    def test_chat_page_does_not_render_model_selector(self) -> None:
        chat_page = (PROJECT_ROOT / "apps" / "web" / "src" / "routes" / "ChatPage.vue").read_text(encoding="utf-8")

        self.assertNotIn("<select", chat_page)
        self.assertNotIn("getChatModelOptions", chat_page)
        self.assertNotIn("v-model=\"modelProfile\"", chat_page)

    def test_chat_request_payload_contains_only_message(self) -> None:
        api_client = (PROJECT_ROOT / "apps" / "web" / "src" / "lib" / "apiClient.ts").read_text(encoding="utf-8")

        self.assertIn("message: string;", api_client)
        self.assertNotIn("modelProfile?:", api_client)


if __name__ == "__main__":
    unittest.main()

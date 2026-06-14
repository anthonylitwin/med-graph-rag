from __future__ import annotations

import sys
import unittest
from pathlib import Path


API_ROOT = Path(__file__).resolve().parents[1] / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.services.qa_service import answer_question, get_model_options


class ChatServiceTests(unittest.TestCase):
    def test_model_options_include_local_profiles(self) -> None:
        options = get_model_options()
        profile_names = {profile["name"] for profile in options["profiles"]}

        self.assertIn(options["defaultProfile"], profile_names)
        self.assertIn("local-qwen25", profile_names)
        self.assertIn("local-qwen3", profile_names)
        self.assertIn("noop", profile_names)

    def test_answer_question_honors_noop_profile_metadata(self) -> None:
        result = answer_question("What risk may aspirin increase?", model_profile="noop")

        self.assertEqual(result["provider"], "noop")
        self.assertEqual(result["modelProfile"], "noop")
        self.assertEqual(result["model"], "noop-language-model-v0")
        self.assertFalse(result["abstained"])


if __name__ == "__main__":
    unittest.main()

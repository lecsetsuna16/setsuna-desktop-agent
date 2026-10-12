import json
from pathlib import Path
import unittest

from resona_desktop_pet.llm_response_utils import structured_reasoning_fallback


ROOT = Path(__file__).resolve().parents[1]


def _json_response(display="恢复成功"):
    return json.dumps(
        {
            "thought": "test",
            "emotion": "<E:smile>",
            "text_display": display,
            "text_tts": "大丈夫だよ。",
        },
        ensure_ascii=False,
    )


class EmptyContentRecoveryTests(unittest.TestCase):
    def test_accepts_complete_json_from_reasoning_content(self):
        response = _json_response("从 reasoning 恢复")
        self.assertEqual(response, structured_reasoning_fallback(response))

    def test_accepts_fenced_complete_json(self):
        response = _json_response()
        fenced = f"```json\n{response}\n```"
        self.assertEqual(fenced, structured_reasoning_fallback(fenced))

    def test_rejects_internal_prose_and_incomplete_objects(self):
        self.assertEqual("", structured_reasoning_fallback("internal prose only"))
        self.assertEqual("", structured_reasoning_fallback('{"text_display": "missing tts"}'))

    def test_chat_path_uses_recovery_then_one_controlled_retry(self):
        source = (ROOT / "resona_desktop_pet" / "backend" / "llm_backend.py").read_text(
            encoding="utf-8"
        )
        start = source.index("    async def _query_litellm(")
        end = source.index("    async def query_raw(", start)
        method = source[start:end]
        self.assertIn("structured_reasoning_fallback(reasoning)", method)
        self.assertEqual(
            1,
            method.count("Chat model returned empty content; requesting one structured retry"),
        )
        self.assertEqual(1, method.count("Do not leave message.content empty."))
        self.assertIn("Empty response from LLM after one retry", method)


if __name__ == "__main__":
    unittest.main()

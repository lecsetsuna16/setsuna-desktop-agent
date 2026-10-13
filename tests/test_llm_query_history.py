import asyncio
from types import SimpleNamespace
import unittest

from resona_desktop_pet.backend.llm_backend import ConversationHistory, LLMBackend, LLMResponse


class _Config(SimpleNamespace):
    def get_llm_config(self):
        return {"model_type": 2, "model_name": "test-model", "api_key": "k", "base_url": ""}

    def get_ocr_config(self):
        return {}


class QueryHistoryTests(unittest.TestCase):
    def test_successful_reply_is_recorded_in_history(self):
        backend = object.__new__(LLMBackend)
        backend.config = _Config(skills_enabled=False, enable_time_context=False, enable_ip_context=False)
        backend._mcp_manager = None
        backend._ip_context = None
        backend._active_model_signature = (2, "test-model", "k", "")
        backend.history = ConversationHistory()
        backend._build_messages = lambda question, *args, **kwargs: [{"role": "user", "content": f"[ctx] {question}"}]

        async def fake_query_litellm(*args, **kwargs):
            return LLMResponse(text_display="你好", raw_response='{"text_display": "你好"}')

        backend._query_litellm = fake_query_litellm

        response = asyncio.run(backend.query("在吗", source="web"))

        self.assertIsNone(response.error)
        self.assertEqual("你好", response.text_display)
        self.assertEqual(
            [{"role": "user", "content": "[ctx] 在吗"}],
            backend.history.get_messages()[:1],
        )
        self.assertEqual("assistant", backend.history.get_messages()[1]["role"])

    def test_desktop_tool_and_image_replies_use_requested_history(self):
        async def run_case(with_tools, with_image, failed):
            backend = object.__new__(LLMBackend)
            backend.config = _Config(skills_enabled=False, enable_time_context=False, enable_ip_context=False)
            backend.config.get_ocr_config = lambda: {"vlm_enabled": with_image}
            backend._ip_context = None
            backend._active_model_signature = (2, "test-model", "k", "")
            backend.history = ConversationHistory()
            backend._mcp_manager = (SimpleNamespace(enabled=True, has_tools=lambda: True,
                get_tools=lambda **_: [{"type": "function", "function": {"name": "test_tool"}}],
                max_tool_rounds=2) if with_tools else None)
            backend._prepare_image_base64 = lambda: "synthetic-image"
            backend._build_messages = lambda *a, **k: [{"role": "user", "content": "processed question"}]
            backend._build_messages_with_image = lambda *a, **k: [{"role": "user", "content": [
                {"type": "text", "text": "processed question"},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,synthetic"}}]}]
            daily_logs = []
            calls = []

            async def no_ocr(*_): return None
            async def record_log(question, pack): daily_logs.append(question)
            async def plain(*args, **kwargs):
                calls.append('plain')
                return reply()
            async def tools(*args, **kwargs):
                calls.append('tools')
                return reply()
            def reply():
                return (LLMResponse(error='synthetic failure') if failed else
                        LLMResponse(text_display='ok', raw_response='{"text_display":"ok","thought":"internal"}'))

            backend._get_ocr_context = no_ocr
            backend._write_daily_log = record_log
            backend._query_litellm = plain
            backend._query_with_tools = tools
            history = ConversationHistory()
            response = await backend.query('question', history=history, source='desktop')
            await asyncio.sleep(0)
            self.assertEqual(calls, ['tools' if with_tools else 'plain'])
            self.assertEqual(bool(response.error), failed)
            self.assertEqual(backend.history.get_messages(), [])
            if failed:
                self.assertEqual(history.get_messages(), [])
                self.assertEqual(daily_logs, [])
            else:
                messages = history.get_messages()
                self.assertEqual(messages[0], {'role': 'user', 'content': 'processed question'})
                self.assertEqual(messages[1]['role'], 'assistant')
                self.assertNotIn('thought', messages[1]['content'])
                self.assertEqual(daily_logs, ['question'])

        for with_tools, with_image, failed in ((False, False, False), (True, False, False),
                                               (True, True, False), (True, True, True)):
            with self.subTest(tools=with_tools, image=with_image, failed=failed):
                asyncio.run(run_case(with_tools, with_image, failed))


if __name__ == "__main__":
    unittest.main()

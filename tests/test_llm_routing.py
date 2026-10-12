import unittest

from resona_desktop_pet.model_routing import select_request_model, should_use_fallback


class LLMRoutingTests(unittest.TestCase):
    def test_routing_is_opt_in_and_disabled_mode_always_uses_main(self):
        config = {
            "model_name": "deepseek-flash",
            "chat_model_name": "legacy-chat",
            "routing_enabled": False,
        }
        for mcp_active, has_tool_intent, skill_wants_reasoner in (
            (False, False, False),
            (True, False, False),
            (True, True, False),
            (True, False, True),
        ):
            with self.subTest(
                mcp_active=mcp_active,
                has_tool_intent=has_tool_intent,
                skill_wants_reasoner=skill_wants_reasoner,
            ):
                model, reason = select_request_model(
                    config,
                    mcp_active=mcp_active,
                    has_tool_intent=has_tool_intent,
                    skill_wants_reasoner=skill_wants_reasoner,
                )
                self.assertEqual("deepseek-flash", model)
                self.assertIn("Manual routing disabled", reason)

    def test_enabled_routing_preserves_chat_and_tool_split(self):
        config = {
            "model_name": "tool-model",
            "chat_model_name": "chat-model",
            "routing_enabled": True,
        }
        chat, _ = select_request_model(
            config,
            mcp_active=True,
            has_tool_intent=False,
            skill_wants_reasoner=False,
        )
        tool, _ = select_request_model(
            config,
            mcp_active=True,
            has_tool_intent=True,
            skill_wants_reasoner=False,
        )
        skill, _ = select_request_model(
            config,
            mcp_active=True,
            has_tool_intent=False,
            skill_wants_reasoner=True,
        )
        self.assertEqual("chat-model", chat)
        self.assertEqual("tool-model", tool)
        self.assertEqual("tool-model", skill)

    def test_disabled_routing_never_uses_legacy_fallback(self):
        config = {
            "model_name": "deepseek-flash",
            "fallback_model_name": "deepseek-v4-pro",
            "routing_enabled": False,
        }
        self.assertFalse(
            should_use_fallback(
                config,
                has_error=True,
                has_tools=True,
                selected_model="deepseek-flash",
            )
        )


if __name__ == "__main__":
    unittest.main()

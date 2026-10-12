"""Model-selection policy without backend or image-processing dependencies."""

from typing import Any, Dict, Tuple


def select_request_model(
    llm_config: Dict[str, Any],
    *,
    mcp_active: bool,
    has_tool_intent: bool,
    skill_wants_reasoner: bool,
) -> Tuple[str, str]:
    """Select one model while keeping manual routing explicitly opt-in."""
    main_model = llm_config["model_name"]
    if not llm_config.get("routing_enabled", False):
        return main_model, f"Manual routing disabled → single model: {main_model}"

    chat_model = llm_config.get("chat_model_name", "")
    if skill_wants_reasoner:
        return main_model, f"Skill requires reasoner → main model: {main_model}"
    if not chat_model:
        return main_model, f"No chat model configured → main model: {main_model}"
    if not mcp_active:
        return chat_model, f"MCP inactive → chat model: {chat_model}"
    if not has_tool_intent:
        return chat_model, f"No tool intent → chat model: {chat_model}"
    return main_model, f"Tool intent detected → main model: {main_model}"


def should_use_fallback(
    llm_config: Dict[str, Any],
    *,
    has_error: bool,
    has_tools: bool,
    selected_model: str,
) -> bool:
    """Return whether the opt-in dual-model fallback path may run."""
    fallback_model = llm_config.get("fallback_model_name", "")
    return bool(
        llm_config.get("routing_enabled", False)
        and has_error
        and has_tools
        and fallback_model
        and fallback_model != selected_model
    )

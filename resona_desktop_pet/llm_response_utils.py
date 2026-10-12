"""Small response-normalization helpers that do not depend on an LLM SDK."""

import json
import re


def structured_reasoning_fallback(reasoning: str) -> str:
    """Return reasoning only when it contains a complete final-response object."""
    candidate = (reasoning or "").strip()
    if not candidate or "text_display" not in candidate or "text_tts" not in candidate:
        return ""

    json_candidate = candidate
    if "```" in json_candidate:
        match = re.search(r"```(?:json)?\s*(.*?)\s*```", json_candidate, re.DOTALL)
        if match:
            json_candidate = match.group(1).strip()
    if not json_candidate.startswith("{"):
        match = re.search(r"({.*})", json_candidate, re.DOTALL)
        if match:
            json_candidate = match.group(1).strip()

    try:
        data = json.loads(json_candidate)
    except (TypeError, json.JSONDecodeError):
        return ""
    if not isinstance(data, dict):
        return ""
    if not isinstance(data.get("text_display"), str):
        return ""
    if not isinstance(data.get("text_tts"), str):
        return ""
    return candidate

"""Register semantic functions in the existing MCP dispatch without a subprocess."""
import asyncio
import json
from .protocol import tool_definitions, validate_perform, validate_sing


def install_live2d_tools(manager, character):
    async def call(name, arguments):
        try:
            if not isinstance(arguments, dict):
                raise ValueError("arguments must be an object")
            pack = arguments.get("pack_id")
            active = character.parent().config.pack_manager.active_pack_id
            aliases = character.parent().config.pack_manager.id_map
            if pack and aliases.get(pack, pack) != active:
                raise ValueError("Tool target is not the active desktop character")
            if name == "setsuna_local_music":
                from .local_music import validate_music
                payload, kind = validate_music(arguments), "local_music"
            elif name == "setsuna_perform":
                payload = validate_perform(arguments)
                kind = "perform"
            elif name == "setsuna_sing":
                payload, kind = validate_sing(arguments), "sing"
            else:
                if set(arguments) - {"pack_id"}:
                    raise ValueError("This tool does not accept arguments")
                payload, kind = {}, "status" if name == "setsuna_status" else "reset"
            future = character.request_live2d(kind, payload)
            result = await asyncio.wait_for(asyncio.wrap_future(future), timeout=8)
            return json.dumps(result, ensure_ascii=False, allow_nan=False)
        except Exception as exc:
            return json.dumps({"ok": False, "error": str(exc) or type(exc).__name__}, ensure_ascii=False)

    for definition in tool_definitions():
        name = definition["function"]["name"]
        async def handler(arguments, tool_name=name):
            return await call(tool_name, arguments)
        manager.register_local_tool(definition, handler)

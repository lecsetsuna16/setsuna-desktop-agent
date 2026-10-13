import asyncio
import json
import logging
import sys
from contextlib import AsyncExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from ..cleanup_manager import register_cleanup
from ..config import ConfigManager

logger = logging.getLogger("MCP")


@dataclass
class MCPServerSpec:
    name: str
    command: str
    args: List[str]
    env: Optional[Dict[str, str]] = None
    cwd: Optional[str] = None


class MCPManager:
    def __init__(self, config: ConfigManager):
        self.config = config
        self.enabled = config.mcp_enabled
        self.server_dir = Path(config.config_path).parent / config.mcp_server_dir
        self.startup_timeout = config.mcp_startup_timeout
        self.max_tool_rounds = config.mcp_max_tool_rounds
        self._loop = None
        self._lifecycle_task = None
        self._ready = None
        self._stop_event = None
        self._sessions: Dict[str, ClientSession] = {}
        self._tool_index: Dict[str, Dict[str, Any]] = {}
        self._tools_cache: List[Dict[str, Any]] = []
        self._tools_cache_meta: List[Dict[str, Any]] = []
        self._server_has_public: Dict[str, bool] = {}
        self._started = False
        self._local_tools = {}
        self._pending_calls = {}
        register_cleanup(self.stop_sync)

    def has_tools(self) -> bool:
        return bool(self._tools_cache or self._local_tools)

    def get_tools(self, public_only: bool = True) -> List[Dict[str, Any]]:
        if not self.enabled:
            return []
        combined = self._tools_cache + [entry["definition"] for entry in self._local_tools.values()]
        if not public_only:
            return list(combined)
        tools = [t for t in combined if "[PRIVATE]" not in t.get("function", {}).get("description", "")]
        hide_prefixes = self.config.get("MCP", "hide_public_prefixes", "")
        if hide_prefixes:
            prefixes = [p.strip() for p in hide_prefixes.split(",") if p.strip()]
            if prefixes:
                tools = [t for t in tools if not any(t.get("function", {}).get("name", "").startswith(p) for p in prefixes)]
        return tools

    def get_tool_metadata(self, name: str) -> Dict[str, Any]:
        if name in self._local_tools:
            return {"server": "live2d.local", "public": True, "subagent": False}
        return self._tool_index.get(name, {})

    # ── Auto-generated routing keywords cache ───────────────────────────────
    @property
    def _auto_cache_path(self) -> Path:
        return self.server_dir / "auto_keywords.json"

    def _load_auto_cache(self) -> Dict[str, List[str]]:
        """Load LLM-generated keywords cache. Written by backend only, never by LLM tools."""
        try:
            if self._auto_cache_path.exists():
                return json.loads(self._auto_cache_path.read_text(encoding="utf-8"))
        except Exception:
            pass
        return {}

    def save_auto_keyword(self, server_name: str, keywords: List[str]) -> None:
        """Persist auto-generated routing keywords for a server. Called by LLMBackend, not via tool."""
        cache = self._load_auto_cache()
        cache[server_name] = [k for k in keywords if isinstance(k, str) and k.strip()]
        try:
            self._auto_cache_path.write_text(
                json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            logger.info(f"[MCP] Auto keywords saved for {server_name}: {keywords}")
        except Exception as e:
            logger.warning(f"[MCP] Failed to save auto keywords: {e}")

    def get_mcps_needing_keywords(self) -> List[tuple]:
        """Return [(server_name, tools_info_str)] for loaded MCPs missing ROUTING_KEYWORDS
        in both their .py source and the auto cache."""
        import ast as _ast
        import re as _re

        has_in_py: set = set()
        if self.server_dir.exists():
            for path in self.server_dir.iterdir():
                if path.is_file() and path.name.lower().endswith(".mcp.py"):
                    try:
                        content = path.read_text(encoding="utf-8")
                        if _re.search(r'^ROUTING_KEYWORDS\s*=\s*\[', content, _re.MULTILINE):
                            has_in_py.add(path.stem)  # e.g. "command_proxy.mcp"
                    except Exception:
                        pass

        has_in_cache = set(self._load_auto_cache().keys())

        from collections import defaultdict
        server_tools: Dict[str, List[str]] = defaultdict(list)
        for tool in self._tools_cache:
            func = tool.get("function", {})
            name = func.get("name", "")
            server = self._tool_index.get(name, {}).get("server", "")
            if not server or server in has_in_py or server in has_in_cache:
                continue
            desc = func.get("description", "").split("\n")[0][:80]  # first line, max 80 chars
            server_tools[server].append(f"{name}: {desc}")

        return [(srv, "\n".join(tools)) for srv, tools in server_tools.items()]

    # ────────────────────────────────────────────────────────────────────────

    def _clean_orphan_auto_cache(self) -> None:
        """Remove auto_keywords.json entries whose .mcp.py source file no longer exists."""
        cache = self._load_auto_cache()
        if not cache:
            return
        existing = {p.stem for p in self.server_dir.iterdir()
                    if p.is_file() and (p.name.lower().endswith(".mcp.py")
                                        or p.name.lower().endswith(".mcp.json"))}
        orphans = [key for key in cache if key not in existing]
        if orphans:
            for key in orphans:
                del cache[key]
            try:
                self._auto_cache_path.write_text(
                    json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                logger.info(f"[MCP] Cleaned orphan auto-keyword entries: {orphans}")
            except Exception as e:
                logger.warning(f"[MCP] Failed to clean orphan cache: {e}")

    def get_routing_keywords(self) -> List[str]:
        """Scan MCP source files for ROUTING_KEYWORDS declarations + auto-generated cache.
        Uses ast.literal_eval for safe parsing — no code execution."""
        import ast as _ast
        import re as _re
        self._clean_orphan_auto_cache()
        keywords: List[str] = []

        # 1. Read from .py source files
        if self.server_dir.exists():
            for path in sorted(self.server_dir.iterdir()):
                if not path.is_file() or not path.name.lower().endswith(".mcp.py"):
                    continue
                try:
                    content = path.read_text(encoding="utf-8")
                    m = _re.search(r'^ROUTING_KEYWORDS\s*=\s*(\[[\s\S]*?\])', content, _re.MULTILINE)
                    if m:
                        kws = _ast.literal_eval(m.group(1))
                        if isinstance(kws, list):
                            keywords.extend(k for k in kws if isinstance(k, str) and k.strip())
                except Exception:
                    pass

        # 2. Merge auto-generated cache (written by backend, protected from LLM tool writes)
        for kw_list in self._load_auto_cache().values():
            if isinstance(kw_list, list):
                keywords.extend(k for k in kw_list if isinstance(k, str) and k.strip())

        return keywords

    def _scan_server_specs(self) -> List[MCPServerSpec]:
        if not self.server_dir.exists():
            return []
        candidates = []
        for path in sorted(self.server_dir.iterdir()):
            if not path.is_file():
                continue
            name = path.name.lower()
            if name.endswith(".mcp.json") or name.endswith(".mcp.py") or name.endswith(".mcp.js"):
                candidates.append(path)
        specs: List[MCPServerSpec] = []
        for path in candidates:
            if path.suffix == ".json":
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                except Exception as e:
                    logger.error(f"[MCP] Failed to parse {path.name}: {e}")
                    continue
                command = data.get("command")
                if not command:
                    logger.error(f"[MCP] Missing command in {path.name}")
                    continue
                args = data.get("args", [])
                if not isinstance(args, list):
                    args = [str(args)]
                env = data.get("env")
                if env is not None and not isinstance(env, dict):
                    env = None
                cwd = data.get("cwd")
                if cwd:
                    cwd_path = Path(cwd)
                    if not cwd_path.is_absolute():
                        cwd_path = (self.server_dir / cwd_path).resolve()
                    cwd = str(cwd_path)
                else:
                    cwd = str(path.parent)

                name = data.get("name") or path.stem
                
                if command == "python":
                    command = sys.executable

                specs.append(MCPServerSpec(name=name, command=command, args=[str(a) for a in args], env=env, cwd=cwd))
            else:
                command = sys.executable if path.suffix == ".py" else "node"
                specs.append(MCPServerSpec(name=path.stem, command=command, args=[str(path)], cwd=str(path.parent)))
        return specs

    async def start(self) -> None:
        if not self.enabled:
            return
        loop = asyncio.get_running_loop()
        if self._lifecycle_task is None or self._lifecycle_task.done():
            self._loop = loop
            self._ready = asyncio.Event()
            self._stop_event = asyncio.Event()
            self._lifecycle_task = loop.create_task(self._lifecycle(), name="MCP lifecycle")
            # A task cancelled before its first step never executes its finally.
            # Wake callers even in that case, using this generation's event.
            ready = self._ready
            self._lifecycle_task.add_done_callback(lambda _: ready.set())
        elif loop is not self._loop:
            raise RuntimeError("MCP must be started on its owning event loop")
        task, ready, stop_event = self._lifecycle_task, self._ready, self._stop_event
        try:
            await ready.wait()
            if task.done():
                await task
        except asyncio.CancelledError:
            stop_event.set()
            task.cancel()
            raise

    async def _lifecycle(self) -> None:
        # Each transport's AnyIO scopes must be entered and exited by ONE task.
        # Independent owner tasks also let failed/slow servers clean up in parallel.
        servers = []
        try:
            for spec in self._scan_server_specs():
                ready = self._loop.create_future()
                task = self._loop.create_task(self._serve(spec, ready), name=f"MCP {spec.name}")
                servers.append((spec, task, ready))
            await asyncio.gather(*(self._wait_ready(*entry) for entry in servers))
            self._started = True
            self._ready.set()
            await self._stop_event.wait()
        finally:
            self._stop_event.set()
            for call in list(self._pending_calls):
                call.cancel()
            for _, task, ready in servers:
                if not ready.done():
                    task.cancel()
            await asyncio.gather(*(task for _, task, _ in servers), return_exceptions=True)
            await asyncio.gather(*list(self._pending_calls), return_exceptions=True)
            self._sessions.clear()
            self._tool_index.clear()
            self._tools_cache.clear()
            self._tools_cache_meta.clear()
            self._server_has_public.clear()
            self._started = False
            self._ready.set()

    async def _wait_ready(self, spec, task, ready):
        try:
            await asyncio.wait_for(asyncio.shield(ready), timeout=self.startup_timeout)
        except asyncio.TimeoutError:
            logger.error("[MCP] Startup timed out: %s", spec.name)
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("[MCP] Server failed: %s error=%s", spec.name, exc)

    async def _serve(self, spec, ready):
        try:
            async with AsyncExitStack() as stack:
                params = StdioServerParameters(command=spec.command, args=spec.args,
                                               env=spec.env, cwd=spec.cwd)
                read, write = await stack.enter_async_context(stdio_client(params))
                session = await stack.enter_async_context(ClientSession(read, write))
                await session.initialize()
                result = await session.list_tools()
                self._register_server_tools(spec, session, result.tools or [])
                ready.set_result(None)
                await self._stop_event.wait()
        except asyncio.CancelledError:
            if not ready.done():
                ready.cancel()
            raise
        except Exception as exc:
            if not ready.done():
                ready.set_exception(exc)
            else:
                logger.warning("[MCP] Server stopped unexpectedly: %s error=%s", spec.name, exc)
        finally:
            self._remove_server(spec.name)

    def _register_server_tools(self, spec, session, tools):
        tool_names = []
        for tool in tools:
            if tool.name in self._tool_index:
                logger.warning(f"[MCP] Tool name conflict skipped: {tool.name}")
                continue
            params = tool.inputSchema or {"type": "object", "properties": {}}
            if tool.name == "schedule_timer_event":
                props = params.get("properties")
                if isinstance(props, dict):
                    props.pop("pack_id", None)
                req = params.get("required")
                if isinstance(req, list) and "pack_id" in req:
                    params["required"] = [r for r in req if r != "pack_id"]
            tool_def = {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description or "",
                    "parameters": params
                }
            }
            desc = tool.description or ""
            is_public = "[PUBLIC]" in desc
            is_subagent = "[SUBAGENT]" in desc
            if is_public:
                self._server_has_public[spec.name] = True
            self._tool_index[tool.name] = {
                "session": session,
                "server": spec.name,
                "public": is_public,
                "subagent": is_subagent
            }
            self._tools_cache.append(tool_def)
            self._tools_cache_meta.append({
                "tool": tool_def,
                "server": spec.name,
                "public": is_public,
                "subagent": is_subagent
            })
            tool_names.append(tool.name)
        self._sessions[spec.name] = session
        logger.info(f"[MCP] Server ready: {spec.name} tools={tool_names}")

    def _remove_server(self, name):
        for call, server in list(self._pending_calls.items()):
            if server == name:
                call.cancel()
        self._sessions.pop(name, None)
        removed = {key for key, value in self._tool_index.items() if value["server"] == name}
        for key in removed:
            self._tool_index.pop(key, None)
        self._tools_cache[:] = [t for t in self._tools_cache if t["function"]["name"] not in removed]
        self._tools_cache_meta[:] = [t for t in self._tools_cache_meta if t["server"] != name]
        self._server_has_public.pop(name, None)

    async def stop(self) -> None:
        task = self._lifecycle_task
        if task is None or task.done():
            return
        if asyncio.get_running_loop() is not self._loop:
            raise RuntimeError("MCP must be stopped on its owning event loop")
        self._stop_event.set()
        if not self._started:
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    def stop_sync(self) -> None:
        if self._lifecycle_task is None or self._lifecycle_task.done():
            return
        if self._loop is None or not self._loop.is_running():
            logger.warning("[MCP] Owning event loop stopped before MCP cleanup")
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop is self._loop:
            loop.create_task(self.stop())
        else:
            asyncio.run_coroutine_threadsafe(self.stop(), self._loop).result(timeout=10)

    def register_local_tool(self, definition, handler):
        name = definition["function"]["name"]
        if name in self._tool_index:
            raise ValueError(f"Local tool conflicts with MCP server: {name}")
        self._local_tools[name] = {"definition": definition, "handler": handler}

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> str:
        if name in self._local_tools:
            return await self._local_tools[name]["handler"](arguments)
        entry = self._tool_index.get(name)
        if not entry:
            raise RuntimeError(f"MCP tool not found: {name}")
        session: ClientSession = entry["session"]
        if self._stop_event is not None and self._stop_event.is_set():
            raise RuntimeError("MCP is stopping")
        call = asyncio.create_task(session.call_tool(name, arguments))
        self._pending_calls[call] = entry["server"]
        try:
            result = await call
            logger.info(f"[MCP] Raw tool result for {name}: {result}")
            formatted = self._format_result_content(result)
            if not formatted:
                logger.warning(f"[MCP] Tool {name} returned empty content. Raw: {result}")
            return formatted
        except Exception as e:
            logger.error(f"[MCP] Error calling tool {name}: {e}")
            raise
        finally:
            self._pending_calls.pop(call, None)

    def _format_result_content(self, result: Any) -> str:
        content = getattr(result, "content", None)
        if content is None and isinstance(result, dict):
            content = result.get("content")
        
        if content is None:
            if hasattr(result, "text"):
                return getattr(result, "text")
            return str(result) if result is not None else ""

        if isinstance(content, list):
            parts = []
            for item in content:
                item_type = item.get("type") if isinstance(item, dict) else getattr(item, "type", None)
                item_text = item.get("text") if isinstance(item, dict) else getattr(item, "text", None)
                
                if item_type == "text" and item_text is not None:
                    parts.append(item_text)
                elif item_text is not None:
                    parts.append(item_text)
                else:
                    parts.append(str(item))
            return "\n".join([p for p in parts if p is not None]).strip()
        
        if isinstance(content, str):
            return content.strip()
            
        return str(content).strip()

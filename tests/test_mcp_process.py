import asyncio
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

import psutil
from resona_desktop_pet.backend.mcp_manager import MCPManager
from resona_desktop_pet.cleanup_manager import cleanup_manager


class MCPProcessTests(unittest.IsolatedAsyncioTestCase):
    async def test_stop_closes_real_transport_and_wakes_inflight_call(self):
        with tempfile.TemporaryDirectory(prefix='setsuna-mcp-test-') as directory:
            root = Path(directory)
            script = root / 'slow.mcp.py'
            script.write_text('''from mcp.server.fastmcp import FastMCP
import asyncio
from pathlib import Path
mcp = FastMCP("shutdown-test")
@mcp.tool()
async def slow() -> str:
    Path(__file__).with_suffix(".started").touch()
    await asyncio.sleep(30)
    return "done"
if __name__ == "__main__":
    mcp.run()
''', encoding='utf-8')
            config = SimpleNamespace(config_path=str(root / 'config.cfg'), mcp_enabled=True,
                mcp_server_dir=str(root), mcp_startup_timeout=10, mcp_max_tool_rounds=2, get=lambda *a: '')
            manager = MCPManager(config)
            call = None
            previous = {p.pid for p in psutil.Process().children(recursive=True)}
            try:
                await asyncio.wait_for(manager.start(), 15)
                children = [p for p in psutil.Process().children(recursive=True) if p.pid not in previous]
                self.assertTrue(children, 'The test must exercise an actual MCP subprocess')
                call = asyncio.create_task(manager.call_tool('slow', {}))
                for _ in range(250):
                    if script.with_suffix('.started').exists(): break
                    await asyncio.sleep(.02)
                self.assertTrue(script.with_suffix('.started').exists())
                await asyncio.wait_for(asyncio.to_thread(manager.stop_sync), 10)
                done, _ = await asyncio.wait({call}, timeout=1)
                self.assertIn(call, done, 'MCP caller stayed blocked after transport shutdown')
                self.assertTrue(call.cancelled())
                _, alive = await asyncio.to_thread(psutil.wait_procs, children, timeout=3)
                self.assertEqual(alive, [], 'MCP child survived shutdown')
            finally:
                if call is not None:
                    call.cancel()
                    await asyncio.gather(call, return_exceptions=True)
                await manager.stop()
                cleanup_manager.unregister(manager.stop_sync)

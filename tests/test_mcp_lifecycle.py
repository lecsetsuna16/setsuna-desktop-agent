import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import anyio
from resona_desktop_pet.backend.mcp_manager import MCPManager, MCPServerSpec
from resona_desktop_pet.cleanup_manager import cleanup_manager


class MCPLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        config = SimpleNamespace(mcp_enabled=True, config_path=str(Path('config.cfg').absolute()),
                                 mcp_server_dir='mcpserver', mcp_startup_timeout=.05,
                                 mcp_max_tool_rounds=2, get=lambda *args: '')
        self.manager = MCPManager(config)
        self.closed = []
        self.owners = {}
        self.call_started = asyncio.Event()
        call_started = self.call_started

        @asynccontextmanager
        async def transport(params):
            owner = asyncio.current_task()
            self.owners[params.command] = owner
            async with anyio.create_task_group():
                try:
                    yield params.command, None
                finally:
                    self.assertIs(asyncio.current_task(), owner)
                    self.closed.append(params.command)

        class Session:
            def __init__(self, name, _write): self.name = name
            async def __aenter__(self): return self
            async def __aexit__(self, *_args): pass
            async def initialize(self):
                if self.name == 'hang': await asyncio.Event().wait()
                if self.name == 'fail': raise ValueError('bad handshake')
            async def list_tools(self):
                tool = SimpleNamespace(name=self.name, description='[PUBLIC] test', inputSchema={})
                return SimpleNamespace(tools=[tool])
            async def call_tool(self, name, arguments):
                call_started.set()
                await asyncio.Event().wait()

        self.patches = [patch('resona_desktop_pet.backend.mcp_manager.stdio_client', transport),
                        patch('resona_desktop_pet.backend.mcp_manager.ClientSession', Session)]
        for p in self.patches: p.start()

    async def asyncTearDown(self):
        await asyncio.wait_for(self.manager.stop(), 2)
        cleanup_manager.unregister(self.manager.stop_sync)
        for p in self.patches: p.stop()

    def servers(self, *names):
        self.manager._scan_server_specs = lambda: [MCPServerSpec(n, n, []) for n in names]

    async def test_timeout_and_failure_do_not_break_healthy_server(self):
        self.servers('ok', 'hang', 'fail')
        await self.manager.start()
        self.assertEqual(set(self.manager._sessions), {'ok'})
        self.assertCountEqual(self.closed, ['hang', 'fail'])
        await asyncio.to_thread(self.manager.stop_sync)
        self.assertCountEqual(self.closed, ['ok', 'hang', 'fail'])
        self.assertFalse(self.manager.has_tools())

    async def test_cancel_during_handshake_closes_transport(self):
        self.servers('hang')
        start = asyncio.create_task(self.manager.start())
        while 'hang' not in self.owners: await asyncio.sleep(0)
        start.cancel()
        await asyncio.gather(start, return_exceptions=True)
        await self.manager.stop()
        self.assertEqual(self.closed, ['hang'])

    async def test_restart_creates_new_scopes(self):
        self.servers('ok')
        for _ in range(2):
            await self.manager.start()
            self.assertTrue(self.manager.has_tools())
            await self.manager.stop()
        self.assertEqual(self.closed, ['ok', 'ok'])

    async def test_stop_before_owner_task_runs_releases_start_waiter(self):
        self.servers('ok')
        start = asyncio.create_task(self.manager.start())
        await asyncio.sleep(0)  # start() created its owner, but the owner has not run.
        await self.manager.stop()
        done, _ = await asyncio.wait({start}, timeout=.1)
        if not done:
            start.cancel()
            await asyncio.gather(start, return_exceptions=True)
            self.fail('stop() left start() waiting forever')
        self.assertTrue(start.cancelled())
        self.assertFalse(self.manager._sessions)
        await self.manager.start()
        self.assertTrue(self.manager.has_tools())

    async def test_stop_cancels_waiting_tool_call(self):
        self.servers('ok')
        await self.manager.start()
        call = asyncio.create_task(self.manager.call_tool('ok', {}))
        await asyncio.wait_for(self.call_started.wait(), 1)
        await self.manager.stop()
        done, _ = await asyncio.wait({call}, timeout=.1)
        if not done:
            call.cancel()
            await asyncio.gather(call, return_exceptions=True)
            self.fail('Stopped MCP left a tool caller waiting for a response')
        self.assertTrue(call.cancelled())

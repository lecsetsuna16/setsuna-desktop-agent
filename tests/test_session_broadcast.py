import asyncio
from types import SimpleNamespace
import unittest

from resona_desktop_pet.web_server.session_manager import SessionManager


class SessionBroadcastTests(unittest.IsolatedAsyncioTestCase):
    async def test_expiry_during_send_does_not_abort_broadcast(self):
        for targeted in (False, True):
            with self.subTest(targeted=targeted):
                manager = SessionManager()
                first = manager.create_session('pack', 2)
                expired = manager.create_session('pack', 2)
                last = manager.create_session('pack', 2)
                expired.last_active = 0
                entered, release = asyncio.Event(), asyncio.Event()
                delivered = []

                async def first_send(message):
                    entered.set()
                    await release.wait()
                    delivered.append(('first', message))

                async def last_send(message):
                    delivered.append(('last', message))

                first.websocket = SimpleNamespace(send_json=first_send)
                last.websocket = SimpleNamespace(send_json=last_send)
                message = {'type': 'test'}
                operation = (manager.broadcast_to_pack('pack', message) if targeted
                             else manager.broadcast_all(message))
                task = asyncio.create_task(operation)
                await asyncio.wait_for(entered.wait(), 1)
                manager.cleanup_inactive(1)
                release.set()
                await asyncio.wait_for(task, 1)
                self.assertEqual(delivered, [('first', message), ('last', message)])

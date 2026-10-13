from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from resona_desktop_pet.config import ConfigManager
from resona_desktop_pet.web_server import server
from resona_desktop_pet.cleanup_manager import cleanup_manager

ROOT = Path(__file__).resolve().parents[1]


class WebBridgeTests(unittest.TestCase):
    def setUp(self):
        self.config = ConfigManager(str(ROOT / 'config.example.cfg'))
        # Use only public test config and the checked-in pack manifest.
        self.config.pack_manager.set_active_pack('setsuna')
        self.controller = SimpleNamespace(config=self.config, project_root=ROOT)

    def test_qq_handshake_ping_and_reconnect_with_web_page_enabled(self):
        with patch.object(server, 'controller_ref', self.controller), TestClient(server.app) as client:
            self.assertEqual(client.get('/').status_code, 200)
            with client.websocket_connect('/ws') as ws:
                ws.send_json({'client_type': 'qq', 'pack_id': 'setsuna'})
                ack = ws.receive_json()
                self.assertEqual(ack['type'], 'handshake_ack')
                sid = ack['session_id']
                ws.send_json({'type': 'ping'})
                self.assertEqual(ws.receive_json()['type'], 'pong')
            with client.websocket_connect('/ws') as ws:
                ws.send_json({'client_type': 'qq', 'session_id': sid})
                self.assertEqual(ws.receive_json()['session_id'], sid)
            server.session_manager.remove_session(sid)

    def test_disabled_page_does_not_disable_qq_websocket(self):
        self.config.set('HTML', 'webpage_enabled', False)
        with patch.object(server, 'controller_ref', self.controller), TestClient(server.app) as client:
            self.assertEqual(client.get('/').status_code, 404)
            with client.websocket_connect('/ws') as ws:
                ws.send_json({'client_type': 'qq'})
                sid = ws.receive_json()['session_id']
            server.session_manager.remove_session(sid)

    def test_default_start_does_not_broadcast_udp(self):
        thread = server.WebServerThread(self.controller, None, '127.0.0.1', 8000, 'html')
        try:
            with patch.object(server, 'start_udp_beacon') as beacon, \
                 patch.object(server.app, 'mount'), patch.object(server.uvicorn, 'Server'), \
                 patch('socket.socket'):
                thread.run()
                beacon.assert_not_called()
        finally:
            cleanup_manager.unregister(thread.stop)

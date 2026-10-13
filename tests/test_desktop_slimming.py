import json
import ast
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from types import SimpleNamespace

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtCore import QMimeData, QUrl, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication, QWidget
from resona_desktop_pet.config import ConfigManager
from resona_desktop_pet.logging_utils import prune_session_logs, write_diagnostic, _handler
from resona_desktop_pet.ui.luna.character_view import CharacterView
from resona_desktop_pet.ui.luna.main_window import MainWindow
from resona_desktop_pet.web_server.session_manager import SessionManager


class DesktopSlimmingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_character_and_native_routes_deduplicate_but_allow_later_drop(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'file.txt'
            path.write_text('test', encoding='utf-8')
            received = []
            parent = QWidget()
            parent._recent_drops = {}
            parent.file_dropped = SimpleNamespace(emit=received.append)
            parent.on_file_dropped = lambda info: MainWindow.on_file_dropped(parent, info)
            view = CharacterView(parent)
            mime = QMimeData()
            mime.setUrls([QUrl.fromLocalFile(str(path))])
            event = SimpleNamespace(mimeData=lambda: mime, acceptProposedAction=lambda: None)
            with patch('resona_desktop_pet.ui.luna.main_window.time.monotonic', return_value=10):
                view.dropEvent(event)
                parent.on_file_dropped({'path': str(path)})
            self.assertEqual(len(received), 1)
            with patch('resona_desktop_pet.ui.luna.main_window.time.monotonic', return_value=11):
                parent.on_file_dropped({'path': str(path)})
            self.assertEqual(len(received), 2)
            view.local_music._rescan.stop()
            parent.deleteLater()

    def test_unsupported_model_falls_back_to_painted_static_sprite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pack = root / 'packs/sample'
            pack.mkdir(parents=True)
            (pack / 'model.model3.json').write_text('{}', encoding='utf-8')
            (pack / 'pack.json').write_text(json.dumps({'pack_info': {'id': 'sample'},
                'character': {'live2d': {'enabled': True, 'model': 'model.model3.json'},
                              'outfits': [{'id': 'test', 'path': 'assets/test'}]}}), encoding='utf-8')
            sprites = pack / 'assets/test'
            sprites.mkdir(parents=True)
            (sprites / 'sum.json').write_text(json.dumps({'<E:smile>': ['smile']}), encoding='utf-8')
            pixmap = QPixmap(40, 40)
            pixmap.fill(Qt.GlobalColor.red)
            pixmap.save(str(sprites / 'smile.png'))
            (root / 'config.cfg').write_text('[General]\nactive_pack=sample\n', encoding='utf-8')
            parent = QWidget()
            parent.config = ConfigManager(str(root / 'config.cfg'))
            view = CharacterView(parent)
            view.setup(root, 'test')
            self.assertIsNone(view._live2d)
            view.resize(view.sizeHint())
            self.assertEqual(view.grab().toImage().pixelColor(20, 20), Qt.GlobalColor.red)
            parent.config.pack_manager.pack_data['character']['live2d']['enabled'] = False
            view._pixmap = QPixmap()
            view._setup_live2d()
            self.assertFalse(view._pixmap.isNull(), 'Turning off Live2D must load the static sprite')
            view.local_music._rescan.stop()
            parent.deleteLater()

    def test_disconnected_sessions_expire_but_connected_qq_survives(self):
        manager = SessionManager()
        old = manager.create_session('sample', 2)
        connected = manager.create_session('sample', 2)
        old.last_active = connected.last_active = 0
        connected.websocket = object()
        manager.cleanup_inactive(1)
        self.assertIsNone(manager.get_session(old.session_id))
        self.assertIs(manager.get_session(connected.session_id), connected)

    def test_log_retention_preserves_recent_groups_and_unrelated_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            names = ['app_20260101_010000.log', 'llm_20260101_010000.log.1',
                     'app_20260102_010000.log', 'llm_20260102_010000.log', 'notes.log']
            for name in names: (root / name).write_text('test', encoding='utf-8')
            prune_session_logs(root, keep=1)
            self.assertEqual({p.name for p in root.iterdir()}, set(names[2:]))

    def test_diagnostic_rotates_with_bounded_backups(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'app.log'
            handler = _handler(str(path.absolute()))
            handler.maxBytes = 30
            try:
                for _ in range(10): write_diagnostic(path, 'diagnostic text\n')
                self.assertEqual({p.name for p in path.parent.iterdir()}, {'app.log', 'app.log.1', 'app.log.2'})
            finally:
                handler.close()
                _handler.cache_clear()

    def test_startup_keeps_timer_state_and_only_expires_owned_audio(self):
        # Load this filesystem-only method without initializing the application.
        root = Path(__file__).resolve().parents[1]
        tree = ast.parse((root / 'main.py').read_text(encoding='utf-8'))
        controller = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'ApplicationController')
        method = next(n for n in controller.body if isinstance(n, ast.FunctionDef) and n.name == '_cleanup_temp_dir')
        scope = {'time': time}
        exec(compile(ast.Module(body=[method], type_ignores=[]), 'temp_cleanup', 'exec'), scope)
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory) / 'TEMP'
            temp.mkdir()
            names = ['output_old.wav', 'output_new.wav', 'timer_tasks.json', 'user.wav', 'evidence.log']
            for name in names: (temp / name).write_text('test', encoding='utf-8')
            old = time.time()-90000
            os.utime(temp / 'output_old.wav', (old, old))
            os.utime(temp / 'user.wav', (old, old))
            scope['_cleanup_temp_dir'](SimpleNamespace(project_root=Path(directory)))
            self.assertEqual({p.name for p in temp.iterdir()}, set(names[1:]))

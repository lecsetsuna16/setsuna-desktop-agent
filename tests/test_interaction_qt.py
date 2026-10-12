import os
import unittest
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication, QMenu
from resona_desktop_pet.ui.luna.character_view import CharacterView
from resona_desktop_pet.ui.luna.main_window import MainWindow

class InteractionQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_retired_actions_emit_nothing_and_start_no_animation(self):
        view = CharacterView()
        emitted = []
        view.physicalInteraction.connect(emitted.append)
        for kind in ("head_pat", "cheek_poke", "hug", "shoulder_pat", "unknown"):
            view.trigger_physical_interaction(kind)
            view.play_interaction_feedback(kind)
        self.assertEqual([], emitted)
        self.assertFalse(view.interaction_active)
        self.assertFalse(view.trigger_head_pat(QPoint(10, 10)))
        view.close()

    def test_context_menu_only_exposes_singing_and_stop(self):
        calls = []
        recorder = type("Character", (), {"live2d_enabled": True,
            "request_live2d": lambda self, kind, payload: calls.append((kind, payload))})()
        owner = type("Owner", (), {"character": recorder})()
        menu = QMenu()
        MainWindow.populate_interaction_menu(owner, menu)
        self.assertEqual(["唱歌动作", "停止唱歌"], [a.text() for a in menu.actions()])
        for action in menu.actions(): action.trigger()
        self.assertEqual([("sing", {"command": "start", "duration_seconds": 16}), ("sing", {"command": "stop"})], calls)

    def test_singing_disabled_without_live2d(self):
        owner = type("Owner", (), {"character": type("Character", (), {"live2d_enabled": False})()})()
        menu = QMenu()
        MainWindow.populate_interaction_menu(owner, menu)
        self.assertTrue(all(not a.isEnabled() for a in menu.actions()))

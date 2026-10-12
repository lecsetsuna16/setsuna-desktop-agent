import ast
from pathlib import Path
import unittest
ROOT = Path(__file__).resolve().parents[1]

class InteractionWiringTests(unittest.TestCase):
    def test_retired_controller_callbacks_do_not_send_chat_requests(self):
        tree = ast.parse((ROOT / "main.py").read_text(encoding="utf-8"))
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "ApplicationController")
        for name in ("_handle_physical_interaction", "_try_start_pending_physical_interaction"):
            method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == name)
            scope = {}
            method.decorator_list = []
            exec(compile(ast.Module(body=[method], type_ignores=[]), "callback", "exec"), scope)
            owner = type("Owner", (), {"_pending_physical_interaction": "hug"})()
            scope[name](owner, "hug" if "handle" in name else 0)
            self.assertIsNone(owner._pending_physical_interaction)

    def test_double_click_no_longer_routes_to_head_pat(self):
        source = (ROOT / "resona_desktop_pet/ui/luna/main_window.py").read_text(encoding="utf-8")
        cls = next(n for n in ast.parse(source).body if isinstance(n, ast.ClassDef) and n.name == "MainWindow")
        method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "eventFilter")
        self.assertNotIn("trigger_head_pat", ast.get_source_segment(source, method))

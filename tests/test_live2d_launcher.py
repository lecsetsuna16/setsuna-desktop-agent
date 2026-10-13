"""The Live2D launcher must never mix packages built for a different Python version."""
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("run_live2d", ROOT / "run_live2d.py")
run_live2d = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(run_live2d)


def _make_venv(root, version="3.10.8", home=None):
    venv = root / "venv"
    (venv / "Lib" / "site-packages").mkdir(parents=True)
    (venv / "Scripts").mkdir()
    (venv / "Scripts" / "pythonw.exe").touch()
    lines = [f"home = {home or root / 'missing-base'}", "include-system-site-packages = false"]
    if version is not None:
        lines.append(f"version = {version}")
    (venv / "pyvenv.cfg").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return venv


class BorrowedPackagesTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root)

    def test_portable_runtime_borrows_matching_venv(self):
        venv = _make_venv(self.root, "3.10.8")
        packages, mismatch = run_live2d.borrowed_packages(self.root, prefix=self.root / "runtime_live2d", version=(3, 10))
        self.assertEqual(venv / "Lib" / "site-packages", packages)
        self.assertIsNone(mismatch)

    def test_rejects_venv_built_for_another_version(self):
        _make_venv(self.root, "3.12.10")
        packages, mismatch = run_live2d.borrowed_packages(self.root, prefix=self.root / "runtime_live2d", version=(3, 10))
        self.assertIsNone(packages)
        self.assertIn("venv 是 Python 3.12", mismatch)
        self.assertIn("当前启动器是 Python 3.10", mismatch)

    def test_rejects_venv_without_version(self):
        _make_venv(self.root, version=None)
        packages, mismatch = run_live2d.borrowed_packages(self.root, prefix=self.root / "runtime_live2d", version=(3, 10))
        self.assertIsNone(packages)
        self.assertIn("无法读取 venv 的 Python 版本", mismatch)

    def test_venv_interpreter_uses_its_own_packages(self):
        venv = _make_venv(self.root, "3.12.10")
        self.assertEqual((None, None), run_live2d.borrowed_packages(self.root, prefix=venv, version=(3, 12)))

    def test_no_venv_means_self_contained_runtime(self):
        self.assertEqual((None, None), run_live2d.borrowed_packages(self.root, prefix=self.root / "runtime", version=(3, 12)))


@unittest.skipUnless(os.name == "nt", "cmd.exe launcher")
class FindPythonwTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="pick py "))  # space exercises quoting
        self.addCleanup(shutil.rmtree, self.root)
        (self.root / "tools").mkdir()
        shutil.copy(ROOT / "tools" / "find_pythonw.cmd", self.root / "tools")

    def pick(self):
        result = subprocess.run(
            # cmd /c leaves undefined variables unexpanded, so test definedness explicitly.
            ["cmd.exe", "/d", "/v:on", "/c",
             'call tools\\find_pythonw.cmd & if defined PYW (echo PYW=[!PYW!]) else (echo PYW=[])'],
            cwd=self.root, capture_output=True, text=True, timeout=30,
        )
        return result.stdout.strip().rsplit("PYW=[", 1)[-1].rstrip("]")

    def _runtime(self, name):
        (self.root / name).mkdir()
        (self.root / name / "pythonw.exe").touch()

    def test_prefers_setup_mode3_runtime(self):
        self._runtime("runtime")
        self._runtime("runtime_live2d")
        _make_venv(self.root)
        self.assertEqual("runtime\\pythonw.exe", self.pick())

    def test_uses_venv_while_its_base_interpreter_exists(self):
        base = self.root / "Python 312"
        base.mkdir()
        (base / "python.exe").touch()
        self._runtime("runtime_live2d")
        _make_venv(self.root, "3.12.10", home=base)
        self.assertEqual("venv\\Scripts\\pythonw.exe", self.pick())

    def test_falls_back_to_portable_runtime_when_venv_base_is_gone(self):
        self._runtime("runtime_live2d")
        _make_venv(self.root)
        self.assertEqual("runtime_live2d\\pythonw.exe", self.pick())

    def test_reports_nothing_usable(self):
        _make_venv(self.root)
        self.assertEqual("", self.pick())


if __name__ == "__main__":
    unittest.main()

"""Launch with project-local Python 3.10 and the existing dependency set."""
import os
from pathlib import Path
import runpy
import site
import sys

root = Path(__file__).resolve().parent
os.chdir(root)
if sys.stdout is None or sys.stderr is None:
    (root / "logs").mkdir(exist_ok=True)
    _launch_log = (root / "logs" / "live2d_launch.log").open("a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stderr = _launch_log
sys.path.insert(0, str(root))
site.addsitedir(str(root / "venv" / "Lib" / "site-packages"))
if os.name == "nt":
    _dll_handles = []
    for relative in ("venv/Lib/site-packages/pywin32_system32", "venv/Lib/site-packages/PySide6"):
        folder = root / relative
        if folder.is_dir():
            _dll_handles.append(os.add_dll_directory(str(folder)))
if "--preview" in sys.argv:
    runpy.run_path(str(root / "tools" / "live2d_preview.py"), run_name="__main__")
else:
    runpy.run_path(str(root / "main.py"), run_name="__main__")

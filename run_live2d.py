"""Start the Live2D pet (or its --preview panel) with whichever interpreter the launcher picked.

The launcher prefers runtime\\ or venv\\ (their own packages). The portable runtime_live2d\\
interpreter has no packages and borrows venv\\Lib\\site-packages, which only works when both
use the same Python minor version: compiled wheels such as NumPy and PySide6 are version-specific.
"""
import importlib.util
import os
from pathlib import Path
import runpy
import site
import sys


def venv_version(venv_dir):
    """Return (major, minor) from venv\\pyvenv.cfg, or None when it is missing or unreadable."""
    try:
        lines = (Path(venv_dir) / "pyvenv.cfg").read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in lines:
        key, _, value = line.partition("=")
        if key.strip() in ("version", "version_info"):
            try:
                major, minor = value.strip().split(".")[:2]
                return int(major), int(minor)
            except ValueError:
                return None
    return None


def borrowed_packages(root, prefix=sys.prefix, version=sys.version_info[:2]):
    """Decide whether this interpreter should borrow venv packages.

    Returns (site_packages_or_None, mismatch_message_or_None).
    """
    venv_dir = Path(root) / "venv"
    packages = venv_dir / "Lib" / "site-packages"
    if not packages.is_dir() or Path(prefix).resolve() == venv_dir.resolve():
        return None, None
    found = venv_version(venv_dir)
    if found == tuple(version):
        return packages, None
    return None, (
        f"venv 是 Python {found[0]}.{found[1]}，" if found else "无法读取 venv 的 Python 版本，"
    ) + (
        f"但当前启动器是 Python {version[0]}.{version[1]}，两者的二进制依赖不能混用。\n\n"
        "请重新运行 setup.ps1，或用 venv\\Scripts\\pythonw.exe 启动 run_live2d.py。"
    )


def _show_error(message):
    print(f"[Live2D] {message}")
    if os.name == "nt":
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, message, "Setsuna Desktop Pet", 0x10)


def main():
    root = Path(__file__).resolve().parent
    os.chdir(root)
    if sys.stdout is None or sys.stderr is None:
        (root / "logs").mkdir(exist_ok=True)
        launch_log = (root / "logs" / "live2d_launch.log").open("a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stderr = launch_log
    sys.path.insert(0, str(root))

    packages, mismatch = borrowed_packages(root)
    # A self-contained runtime (setup.ps1 mode 3) may sit next to an unrelated venv.
    if mismatch and importlib.util.find_spec("PySide6") is None:
        _show_error(mismatch)
        sys.exit(1)

    dll_handles = []
    if packages is not None:
        site.addsitedir(str(packages))
        if os.name == "nt":
            for folder in (packages / "pywin32_system32", packages / "PySide6"):
                if folder.is_dir():
                    dll_handles.append(os.add_dll_directory(str(folder)))

    script = "tools/live2d_preview.py" if "--preview" in sys.argv else "main.py"
    runpy.run_path(str(root / script), run_name="__main__")


if __name__ == "__main__":
    main()

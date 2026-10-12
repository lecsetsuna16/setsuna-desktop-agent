"""Open the actual desktop character window and local controls, without starting LLM/TTS services."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
from resona_desktop_pet.live2d.canvas import Live2DCanvas
from resona_desktop_pet.config import ConfigManager
from resona_desktop_pet.ui.luna.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    config = ConfigManager(str(ROOT / "config.cfg"))
    config.config.set("General", "active_pack", "setsuna")
    config.pack_manager.set_active_pack("setsuna")
    # Preview-only settings; do not write config.cfg.
    config.config.set("General", "always_show_ui", "true")
    for section, key, value in (("Physics", "enabled", "false"),):
        if config.config.has_section(section):
            config.config.set(section, key, value)
    window = MainWindow(config)
    window.setWindowTitle("雪菜 Live2D · 模型测试")
    window.show()
    screen = app.primaryScreen().availableGeometry()
    window.move(screen.right() - window.width() - 60, screen.bottom() - window.height() - 40)
    window.show_live2d_controls()
    window._live2d_controls.move(screen.center().x() - 400, screen.center().y() - 250)
    window.io.edit.setPlaceholderText("本地模型测试（Alt＋滚轮缩放）。AI 对话请打开「Live2D桌宠」。")
    window.io.edit.setReadOnly(True)
    app.exec()


if __name__ == "__main__":
    main()

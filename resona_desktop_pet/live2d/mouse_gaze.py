"""Read-only global modifier/cursor sampling; never registers or swallows keys."""
import ctypes
import sys
from PySide6.QtCore import QObject, QTimer, QPoint
from PySide6.QtGui import QCursor

HINT = '按住左 Ctrl＋左 Alt，移动鼠标控制目光；松开恢复'


def gaze_chord_down(key_state=None):
    if key_state is None:
        if sys.platform != 'win32':
            return False
        key_state = ctypes.windll.user32.GetAsyncKeyState
    pressed = lambda key: bool(key_state(key) & 0x8000)
    if not (pressed(0xA2) and pressed(0xA4)):  # Left Ctrl + Left Alt only
        return False
    if any(pressed(key) for key in (0x10, 0xA0, 0xA1, 0xA3, 0xA5, 0x5B, 0x5C)):
        return False
    # A third key (including Ctrl+Alt+0) belongs to another shortcut.
    modifiers = {0x10, 0x11, 0x12, *range(0xA0, 0xA6)}
    return not any(pressed(key) for key in range(8, 0xA6) if key not in modifiers)


def cursor_target(cursor, eye, character_size):
    x = (cursor.x() - eye.x()) / max(180.0, character_size.width() * 1.2)
    y = (eye.y() - cursor.y()) / max(160.0, character_size.height() * .55)
    return max(-1.0, min(1.0, x)), max(-1.0, min(1.0, y))


class MouseGazeController(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.active = False
        self.key_reader = gaze_chord_down
        self.cursor_reader = QCursor.pos
        self.timer = QTimer(self)
        self.timer.setInterval(33)
        self.timer.timeout.connect(self.poll)
        self.timer.start()

    def poll(self):
        window = self.window
        was_active = self.active
        canvas = window.character._live2d
        active = bool(canvas is not None and window.isVisible()
                      and not window.input_hard_locked and self.key_reader())
        if active:
            bounds = window.character.content_rect()
            eye = window.character.mapToGlobal(QPoint(bounds.center().x(), bounds.top() + round(bounds.height() * .22)))
            x, y = cursor_target(self.cursor_reader(), eye, bounds.size())
            canvas.send('mouse_gaze', {'active': True, 'x': x, 'y': y})
            if not self.active:
                window.cancel_idle_fade()
            window.dragging = window.dragging_started = False
        elif self.active and canvas is not None:
            canvas.send('mouse_gaze', {'active': False})
        self.active = active
        if was_active and not active:
            window.schedule_idle_fade()

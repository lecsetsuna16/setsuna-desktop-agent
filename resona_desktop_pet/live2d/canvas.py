import json
import time
import uuid
from pathlib import Path
from urllib.parse import quote
from PySide6.QtCore import QObject, Signal, Slot, Qt, QUrl, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWebEngineWidgets import QWebEngineView
from .assets import AssetServer


class PetBridge(QObject):
    command = Signal(str)

    def __init__(self, canvas):
        super().__init__(canvas)
        self.canvas = canvas

    @Slot(str)
    def report(self, raw):
        try:
            self.canvas.snapshot = json.loads(raw)
            self.canvas.observed_at = time.monotonic()
            if not self.canvas.snapshot.get("ready") and self.canvas.snapshot.get("error"):
                for future in self.canvas.pending.values():
                    if not future.done():
                        future.set_result(self.canvas.snapshot)
                self.canvas.pending.clear()
            if self.canvas.snapshot.get("ready") and not self.canvas.initialized:
                self.canvas.initialized = True
                self.canvas.send("opacity", {"value": self.canvas.model_opacity})
                self.canvas.send("emotion", {"emotion": self.canvas.emotion})
                self.canvas.send("state", {"state": self.canvas.activity})
        except (ValueError, TypeError):
            pass

    @Slot(str)
    def ack(self, raw):
        result = json.loads(raw)
        future = self.canvas.pending.pop(result.get("id"), None)
        if future is not None and not future.done():
            future.set_result(result)


class Live2DCanvas(QWebEngineView):
    def __init__(self, model_path, parent=None):
        super().__init__(parent)
        self.snapshot = {"ok": False, "ready": False, "error": "Model is loading"}
        self.observed_at = 0.0
        self.initialized = False
        self.pending = {}
        self.model_opacity = 1.0
        self.emotion = "neutral"
        self.activity = "idle"
        self.disposed = False
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self.setStyleSheet("background:transparent")
        self.page().setBackgroundColor(QColor(Qt.GlobalColor.transparent))
        self.bridge = PetBridge(self)
        self.channel = QWebChannel(self)
        self.channel.registerObject("petBridge", self.bridge)
        self.page().setWebChannel(self.channel)
        self.server = AssetServer(Path(__file__).parent / "web", Path(model_path).parent)
        renderer = "v081" if (Path(model_path).parent / "emotion-contract.json").is_file() else "legacy"
        self.setUrl(QUrl(self.server.url + "?model=" + quote(Path(model_path).name) + "&renderer=" + renderer))
        self._watchdog = QTimer(self)
        self._watchdog.setInterval(1000)
        self._watchdog.timeout.connect(self._expire)
        self._watchdog.start()
        QApplication.instance().aboutToQuit.connect(self.dispose)

    def _expire(self):
        for key, future in list(self.pending.items()):
            if future.done():
                self.pending.pop(key, None)

    def send(self, kind, payload=None, future=None):
        if self.disposed or not self.snapshot.get("ready") or time.monotonic() - self.observed_at > 3:
            if future is not None and not future.done():
                future.set_result({"ok": False, "error": self.snapshot.get("error", "Renderer is not responding"), "ready": False})
            return
        command_id = uuid.uuid4().hex
        if future is not None:
            self.pending[command_id] = future
            QTimer.singleShot(7500, lambda key=command_id: self._timeout(key))
        self.bridge.command.emit(json.dumps({"id": command_id, "type": kind, "payload": payload or {}}, allow_nan=False))

    def _timeout(self, command_id):
        future = self.pending.pop(command_id, None)
        if future is not None and not future.done():
            future.set_result({"ok": False, "error": "Renderer acknowledgement timed out"})

    def set_opacity(self, value):
        self.model_opacity = max(0.0, min(1.0, float(value)))
        self.send("opacity", {"value": self.model_opacity})

    def set_emotion(self, emotion):
        self.emotion = emotion.split("|")[0].replace("<E:", "").rstrip(">")
        self.send("emotion", {"emotion": self.emotion})

    def set_activity(self, state):
        self.activity = state
        self.send("state", {"state": state})

    def dispose(self):
        if self.disposed:
            return
        self.disposed = True
        self._watchdog.stop()
        for future in self.pending.values():
            if not future.done():
                future.set_result({"ok": False, "error": "Renderer closed or character changed"})
        self.pending.clear()
        self.stop()
        self.server.close()

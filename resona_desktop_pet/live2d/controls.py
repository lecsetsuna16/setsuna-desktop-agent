import json
from PySide6.QtCore import QTimer, Qt, QUrl
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox, QSlider, QTextEdit, QFileDialog
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from .protocol import EXPRESSIONS, MOTIONS, LOOKS
from .audio import AudioLipSync
from .mouse_gaze import HINT


class Live2DControls(QDialog):
    def __init__(self, character, parent=None):
        super().__init__(parent)
        self.character = character
        self.setWindowTitle("雪菜 Live2D · 14 表情与唱歌测试")
        self.resize(520, 580)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        layout = QVBoxLayout(self)
        intro = QLabel("可在这里测试基础表情、动作、视线与音频口型。\n聊天时 DeepSeek 使用同一动作接口；呼吸与自然眨眼自动运行。")
        intro.setText(intro.text() + "\n" + HINT)
        intro.setWordWrap(True)
        layout.addWidget(intro)
        self.expression = QComboBox(); self.expression.addItems(EXPRESSIONS)
        self.motion = QComboBox(); self.motion.addItems(MOTIONS)
        self.look = QComboBox(); self.look.addItems(LOOKS)
        for title, field in (("表情", self.expression), ("动作", self.motion), ("视线", self.look)):
            row = QHBoxLayout(); row.addWidget(QLabel(title)); row.addWidget(field); layout.addLayout(row)
        self.intensity = QSlider(Qt.Orientation.Horizontal); self.intensity.setRange(0, 100); self.intensity.setValue(60)
        layout.addWidget(QLabel("动作强度")); layout.addWidget(self.intensity)
        row = QHBoxLayout()
        for label, callback in (("播放组合", self.perform), ("复位", lambda: self.run("reset")), ("查询实际状态", lambda: self.run("status"))):
            button = QPushButton(label); button.clicked.connect(callback); row.addWidget(button)
        layout.addLayout(row)
        row = QHBoxLayout()
        for label, payload in (("唱歌动作（16秒循环）", {"command": "start", "duration_seconds": 16}), ("停止唱歌", {"command": "stop"})):
            button = QPushButton(label)
            button.clicked.connect(lambda checked=False, value=payload: self.run("sing", value))
            row.addWidget(button)
        layout.addLayout(row)
        layout.addWidget(QLabel("唱歌为模型动作，不含歌曲音频；入场与退场各约 4.2 秒。"))
        row = QHBoxLayout()
        for label, state in (("待机", "idle"), ("思考", "thinking"), ("聆听", "listening")):
            button = QPushButton(label); button.clicked.connect(lambda checked=False, value=state: character.set_live2d_activity(value)); row.addWidget(button)
        layout.addLayout(row)
        row = QHBoxLayout()
        for label, callback in (("播放语音文件测试口型", self.open_audio), ("停止语音", self.stop_audio)):
            button = QPushButton(label); button.clicked.connect(callback); row.addWidget(button)
        layout.addLayout(row)
        self.output = QTextEdit(); self.output.setReadOnly(True); layout.addWidget(self.output)
        self.player = QMediaPlayer(self); self.audio_output = QAudioOutput(self)
        self.player.setAudioOutput(self.audio_output)
        self.lipsync = AudioLipSync(self.player, self); self.lipsync.level.connect(character.set_live2d_audio)
        self.timer = QTimer(self); self.timer.setInterval(50); self.timer.timeout.connect(self.poll)
        self.pending = []
        self.timer.start()

    def perform(self):
        self.run("perform", {"expression": self.expression.currentText(), "motion": self.motion.currentText(),
                             "look": self.look.currentText(), "intensity": self.intensity.value()/100, "hold_ms": 2200})

    def run(self, kind, payload=None):
        self.pending.append(self.character.request_live2d(kind, payload))

    def poll(self):
        for future in list(self.pending):
            if future.done():
                self.pending.remove(future)
                self.output.setPlainText(json.dumps(future.result(), ensure_ascii=False, indent=2))

    def open_audio(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择语音", "", "音频 (*.wav *.ogg *.mp3 *.flac)")
        if path:
            self.player.setSource(QUrl.fromLocalFile(path)); self.player.play()

    def stop_audio(self):
        self.player.stop(); self.character.set_live2d_audio(0.0, False)

    def closeEvent(self, event):
        self.stop_audio()
        super().closeEvent(event)

"""Drive the mouth from the SAME decoded buffers that QMediaPlayer plays."""
from array import array
import math
from PySide6.QtCore import QObject, Signal, Slot, Qt
from PySide6.QtMultimedia import QAudioBuffer, QAudioBufferOutput, QAudioFormat, QMediaPlayer


def pcm_level(data, sample_format):
    if not data:
        return 0.0
    code, divisor, offset = {"float": ("f", 1.0, 0), "int16": ("h", 32768.0, 0),
                             "int32": ("i", 2147483648.0, 0), "uint8": ("B", 128.0, 128)}[sample_format]
    samples = array(code)
    usable = len(data) - len(data) % samples.itemsize
    if not usable:
        return 0.0
    samples.frombytes(data[:usable])
    rms = math.sqrt(sum(((x - offset) / divisor) ** 2 for x in samples) / len(samples))
    if not math.isfinite(rms) or rms < .008:
        return 0.0
    return min(1.0, (rms * 4.0) ** .75)


class AudioLipSync(QObject):
    level = Signal(float, bool)

    def __init__(self, player, parent=None):
        super().__init__(parent)
        self.player = player
        self.output = QAudioBufferOutput(self)
        player.setAudioBufferOutput(self.output)
        self.output.audioBufferReceived.connect(self._buffer, Qt.ConnectionType.QueuedConnection)
        player.playbackStateChanged.connect(self._state)
        player.errorOccurred.connect(lambda *_: self.level.emit(0.0, False))

    @Slot(QMediaPlayer.PlaybackState)
    def _state(self, state):
        self.level.emit(0.0, state == QMediaPlayer.PlaybackState.PlayingState)

    @Slot(QAudioBuffer)
    def _buffer(self, buffer):
        playing = self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        if not playing or not buffer.isValid() or not buffer.byteCount():
            self.level.emit(0.0, playing)
            return
        formats = {QAudioFormat.SampleFormat.Float: "float", QAudioFormat.SampleFormat.Int16: "int16",
                   QAudioFormat.SampleFormat.Int32: "int32", QAudioFormat.SampleFormat.UInt8: "uint8"}
        kind = formats.get(buffer.format().sampleFormat())
        value = pcm_level(bytes(buffer.constData())[:buffer.byteCount()], kind) if kind else 0.0
        self.level.emit(value, playing)

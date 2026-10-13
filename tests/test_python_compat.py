"""Audio and media backends must work without PyAudio/winsdk, which stop at Python 3.13/3.12."""
import asyncio
import importlib.util
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest import mock
import unittest

import numpy  # noqa: F401  (import before patching sys.modules so it is not reloaded)

from resona_desktop_pet.backend.stt_backend import STTBackend, STTResult

ROOT = Path(__file__).resolve().parents[1]


def _backend():
    backend = object.__new__(STTBackend)
    backend.config = SimpleNamespace(stt_max_duration=0.2, stt_silence_threshold=10)
    backend._sample_rate = 16000
    backend._is_recording = True
    backend._audio_data = []
    backend._model_loaded = False
    return backend


class _FakeRawInputStream:
    instances = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.events = []
        _FakeRawInputStream.instances.append(self)

    def start(self):
        self.events.append("start")

    def read(self, frames):
        self.events.append("read")
        return memoryview(b"\x00\x00" * frames), False

    def stop(self):
        self.events.append("stop")

    def close(self):
        self.events.append("close")


def _fake_sounddevice():
    module = ModuleType("sounddevice")
    module.RawInputStream = _FakeRawInputStream
    return module


class MicrophoneTests(unittest.TestCase):
    def setUp(self):
        _FakeRawInputStream.instances.clear()

    def test_records_through_sounddevice_and_closes_stream(self):
        backend = _backend()
        results = []
        backend._recognize_audio = lambda: STTResult(text="ok")
        with mock.patch.dict("sys.modules", {"sounddevice": _fake_sounddevice()}):
            backend._record_audio(results.append)

        stream = _FakeRawInputStream.instances[0]
        self.assertEqual({"samplerate": 16000, "channels": 1, "dtype": "int16", "blocksize": 1024}, stream.kwargs)
        self.assertEqual(["start", "stop", "close"], [e for e in stream.events if e != "read"])
        self.assertTrue(backend._audio_data)
        self.assertTrue(all(isinstance(block, bytes) and len(block) == 2048 for block in backend._audio_data))
        self.assertEqual("ok", results[0].text)

    def test_stream_is_closed_when_recording_fails(self):
        backend = _backend()
        results = []
        broken = _fake_sounddevice()

        class Broken(_FakeRawInputStream):
            def read(self, frames):
                raise OSError("device unplugged")

        broken.RawInputStream = Broken
        with mock.patch.dict("sys.modules", {"sounddevice": broken}):
            backend._record_audio(results.append)

        self.assertEqual(["start", "stop", "close"], _FakeRawInputStream.instances[0].events)
        self.assertEqual("device unplugged", results[0].error)
        self.assertFalse(backend._is_recording)

    def test_stream_is_closed_when_start_fails(self):
        backend = _backend()
        results = []
        broken = _fake_sounddevice()

        class Busy(_FakeRawInputStream):
            def start(self):
                self.events.append("start")
                raise OSError("device busy")

        broken.RawInputStream = Busy
        with mock.patch.dict("sys.modules", {"sounddevice": broken}):
            backend._record_audio(results.append)

        self.assertEqual(["start", "close"], _FakeRawInputStream.instances[0].events)
        self.assertEqual("device busy", results[0].error)

    def test_pyaudio_is_terminated_when_open_fails(self):
        backend = _backend()
        pyaudio = ModuleType("pyaudio")
        pyaudio.paInt16 = 8
        audio = mock.Mock(open=mock.Mock(side_effect=OSError("no input device")))
        pyaudio.PyAudio = mock.Mock(return_value=audio)
        with mock.patch.dict("sys.modules", {"sounddevice": None, "pyaudio": pyaudio}):
            with self.assertRaises(OSError):
                backend._open_microphone()
        audio.terminate.assert_called_once()

    def test_falls_back_to_pyaudio_without_sounddevice(self):
        backend = _backend()
        pyaudio = ModuleType("pyaudio")
        pyaudio.paInt16 = 8
        stream = mock.Mock()
        stream.read.return_value = b"\x00\x00" * 1024
        pyaudio.PyAudio = mock.Mock(return_value=mock.Mock(open=mock.Mock(return_value=stream)))
        with mock.patch.dict("sys.modules", {"sounddevice": None, "pyaudio": pyaudio}):
            read_block, close = backend._open_microphone()
            self.assertEqual(2048, len(read_block()))
            close()
        stream.close.assert_called_once()


class RecognizeFileTests(unittest.TestCase):
    def test_loads_model_from_worker_thread(self):
        backend = _backend()
        calls = []

        async def load_model():
            calls.append("load")
            return False

        backend.load_model = load_model

        async def caller():
            return await asyncio.to_thread(backend.recognize_file, "missing.wav")

        result = asyncio.run(caller())
        self.assertEqual(["load"], calls)
        self.assertEqual("Model load failed", result.error)


class MusicSenseBackendTests(unittest.TestCase):
    def _load(self):
        spec = importlib.util.spec_from_file_location("music_sense_test", ROOT / "mcpserver" / "music_sense.mcp.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_falls_back_to_winsdk_when_winrt_is_missing(self):
        winsdk_control = ModuleType("winsdk.windows.media.control")
        modules = {
            "winrt": None,
            "winrt.windows": None,
            "winrt.windows.foundation": None,
            "winrt.windows.media": None,
            "winrt.windows.media.control": None,
            "winsdk": ModuleType("winsdk"),
            "winsdk.windows": ModuleType("winsdk.windows"),
            "winsdk.windows.media": ModuleType("winsdk.windows.media"),
            "winsdk.windows.media.control": winsdk_control,
        }
        modules["winsdk"].windows = modules["winsdk.windows"]
        modules["winsdk.windows"].media = modules["winsdk.windows.media"]
        modules["winsdk.windows.media"].control = winsdk_control
        with mock.patch.dict("sys.modules", modules):
            self.assertIs(winsdk_control, self._load()._media_control())


if __name__ == "__main__":
    unittest.main()

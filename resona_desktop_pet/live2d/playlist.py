"""Portable library and playback order; no song-specific naming rules."""
import random
from pathlib import Path
EXTENSIONS = {'.wav', '.mp3', '.flac', '.m4a', '.ogg', '.aac', '.wma'}
MODES = ('sequence', 'list_loop', 'single_loop', 'shuffle')
LIBRARY = Path(__file__).resolve().parents[2] / '雪菜歌'

class Playlist:
    def __init__(self, library=LIBRARY, rng=None):
        self.library = Path(library).resolve()
        self.tracks = []
        self.current = None
        self.mode = 'sequence'
        self.history = []
        self.history_index = -1
        self.deck = []
        self.rng = rng or random.Random()

    def refresh(self):
        self.library.mkdir(parents=True, exist_ok=True)
        tracks = sorted((p.resolve() for p in self.library.iterdir()
                         if p.is_file() and p.suffix.lower() in EXTENSIONS
                         and p.resolve().parent == self.library), key=lambda p: p.name.casefold())
        changed = tracks != self.tracks
        self.tracks = tracks
        if changed:
            self.deck = []
            self.history = [p for p in self.history if p in tracks]
            self.history_index = len(self.history) - 1
        return changed

    def resolve_track(self, value):
        path = Path(value)
        if not path.is_absolute(): path = self.library / path
        path = path.resolve()
        if path.parent != self.library or path not in self.tracks or not path.is_file():
            raise ValueError('歌曲必须是当前「雪菜歌」文件夹内的音频，请刷新列表后选择')
        return path

    def select(self, path, record=True):
        path = self.resolve_track(path)
        self.current = path
        if record and (self.history_index < 0 or self.history[self.history_index] != path):
            self.history = self.history[:self.history_index + 1] + [path]
            self.history_index = len(self.history) - 1
        if path in self.deck: self.deck.remove(path)
        return path

    def set_mode(self, mode):
        if mode not in MODES: raise ValueError('Unknown playback mode')
        self.mode = mode
        self.deck = []

    def next(self, automatic=False):
        if not self.tracks: return None
        if automatic and self.mode == 'single_loop' and self.current in self.tracks:
            return self.select(self.current)
        if self.mode == 'shuffle':
            if self.history_index + 1 < len(self.history):
                self.history_index += 1
                return self.select(self.history[self.history_index], record=False)
            if not self.deck:
                self.deck = [p for p in self.tracks if p != self.current]
                self.rng.shuffle(self.deck)
            return self.select(self.deck[-1] if self.deck else self.tracks[0])
        index = self.tracks.index(self.current) + 1 if self.current in self.tracks else 0
        if index == len(self.tracks):
            if automatic and self.mode == 'sequence': return None
            index = 0
        return self.select(self.tracks[index])

    def previous(self):
        if not self.tracks: return None
        if self.mode == 'shuffle' and self.history_index > 0:
            self.history_index -= 1
            return self.select(self.history[self.history_index], record=False)
        index = self.tracks.index(self.current) - 1 if self.current in self.tracks else 0
        return self.select(self.tracks[index])

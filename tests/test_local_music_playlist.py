import random
import tempfile
import unittest
from pathlib import Path
from resona_desktop_pet.live2d.playlist import Playlist


class PlaylistTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name) / 'moved-app' / '雪菜歌'
        self.playlist = Playlist(self.folder, random.Random(7))
        self.playlist.refresh()

    def add_songs(self, *names):
        for name in names: (self.folder / name).write_bytes(b'test audio placeholder')
        self.playlist.refresh()

    def test_empty_and_new_user_library(self):
        self.assertIsNone(self.playlist.next())
        self.add_songs('arbitrary name.mp3', '任意曲目.wav')
        self.assertEqual(len(self.playlist.tracks), 2)
        self.assertEqual(self.playlist.next().parent, self.folder.resolve())

    def test_outside_library_and_nested_files_rejected(self):
        outside = self.folder.parent / 'outside.wav'; outside.touch()
        (self.folder / 'nested').mkdir(); (self.folder / 'nested/instrumental.wav').touch()
        self.playlist.refresh()
        self.assertEqual(self.playlist.tracks, [])
        for path in (outside, '../outside.wav', 'nested/instrumental.wav'):
            with self.assertRaises(ValueError): self.playlist.resolve_track(path)

    def test_sequence_end_and_loop_modes(self):
        self.add_songs('a.wav', 'b.wav')
        self.playlist.select('b.wav')
        self.assertIsNone(self.playlist.next(automatic=True))
        self.playlist.set_mode('list_loop')
        self.assertEqual(self.playlist.next(automatic=True).name, 'a.wav')
        self.playlist.set_mode('single_loop')
        self.assertEqual(self.playlist.next(automatic=True).name, 'a.wav')
        self.assertEqual(self.playlist.next().name, 'b.wav')

    def test_shuffle_cycle_and_history(self):
        self.add_songs('a.wav', 'b.wav', 'c.wav', 'd.wav')
        self.playlist.select('a.wav'); self.playlist.set_mode('shuffle')
        draws = [self.playlist.next() for _ in range(3)]
        self.assertEqual(len(set(draws)), 3)
        self.assertNotIn(self.folder / 'a.wav', draws)
        self.assertEqual(self.playlist.previous(), draws[-2])
        self.assertEqual(self.playlist.next(), draws[-1])
        self.assertNotEqual(self.playlist.next(), draws[-1])

    def test_removed_file_cannot_be_played_from_old_list(self):
        self.add_songs('a.wav', 'b.wav')
        (self.folder / 'a.wav').unlink()
        with self.assertRaises(ValueError): self.playlist.resolve_track('a.wav')
        self.playlist.refresh()
        self.assertEqual([p.name for p in self.playlist.tracks], ['b.wav'])

    def test_single_file_shuffle(self):
        self.add_songs('only.wav'); self.playlist.set_mode('shuffle')
        for _ in range(3): self.assertEqual(self.playlist.next().name, 'only.wav')

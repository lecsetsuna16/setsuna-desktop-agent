"""Shared local music transport for the desktop player and LLM tools."""
import logging
from pathlib import Path
from PySide6.QtCore import QObject, QTimer, QUrl, Signal, QFileSystemWatcher
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from .playlist import LIBRARY, EXTENSIONS, MODES, Playlist

def validate_music(args):
    if not isinstance(args, dict) or set(args) - {'command', 'path', 'query', 'mode', 'offset', 'pack_id'}:
        raise ValueError('Unknown local music arguments')
    command = args.get('command')
    if command not in {'list', 'play', 'pause', 'resume', 'stop', 'status', 'next', 'previous', 'set_mode'}:
        raise ValueError('Unknown local music command')
    for key in ('path', 'query'):
        if key in args and not isinstance(args[key], str): raise ValueError(key + ' must be text')
    if args.get('path') and command != 'play': raise ValueError('path is only used by play')
    if command == 'set_mode' and args.get('mode') not in MODES:
        raise ValueError('mode must be sequence/list_loop/single_loop/shuffle')
    if 'offset' in args and (type(args['offset']) is not int or args['offset'] < 0):
        raise ValueError('offset must be a nonnegative integer')
    return {k: v for k, v in args.items() if k != 'pack_id'}

class LocalMusic(QObject):
    playback_requested = Signal()
    changed = Signal()
    tracks_changed = Signal()

    def __init__(self, character, library=LIBRARY):
        super().__init__(character)
        self.character = character
        self.playlist = Playlist(library)
        self.player = QMediaPlayer(self)
        self.output = QAudioOutput(self)
        self.volume = .8
        self._ducked = False
        self.output.setVolume(self.volume)
        self.player.setAudioOutput(self.output)
        self.player.playbackStateChanged.connect(self._state_changed)
        self.player.mediaStatusChanged.connect(self._media_status)
        self.player.errorOccurred.connect(self._error)
        self.player.positionChanged.connect(lambda _: self.changed.emit())
        self.player.durationChanged.connect(lambda _: self.changed.emit())
        self.pending = None
        self.path = None
        self.last_error = ''
        self._future = None
        self._loading = False
        self._generation = 0
        self.trigger_suppressed = False
        self._load_timer = QTimer(self)
        self._load_timer.setSingleShot(True)
        self._load_timer.timeout.connect(lambda: self._error(None, '音频加载超时'))
        self.watcher = QFileSystemWatcher(self)
        self.watcher.directoryChanged.connect(lambda _: self._refresh_timer.start(350))
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.timeout.connect(self.refresh)
        self._rescan = QTimer(self)
        self._rescan.setInterval(3000)
        self._rescan.timeout.connect(self.refresh)
        self._rescan.start()
        QTimer.singleShot(0, self.refresh)

    @property
    def has_track(self):
        return bool(self.pending or self._loading or self.player.playbackState() != QMediaPlayer.PlaybackState.StoppedState)

    def refresh(self):
        try:
            changed = self.playlist.refresh()
            directory = str(self.playlist.library)
            if directory not in self.watcher.directories(): self.watcher.addPath(directory)
            if self.pending and self.pending not in self.playlist.tracks: self.stop()
            if self.path and self.path not in self.playlist.tracks:
                self.stop()
                self.path = None
                self.playlist.current = None
            if changed:
                self.tracks_changed.emit()
                self.changed.emit()
        except OSError as exc:
            self.last_error = '曲库无法读取：' + str(exc)
            self.changed.emit()

    def status(self):
        state = self.player.playbackState()
        name = ('queued_after_reply' if self.pending else 'loading' if self._loading else
                'playing' if state == QMediaPlayer.PlaybackState.PlayingState else
                'paused' if state == QMediaPlayer.PlaybackState.PausedState else 'stopped')
        return {'ok': not bool(self.last_error), 'source': 'desktop_pet_local_file', 'status': name,
                'library': str(self.playlist.library), 'path': str(self.pending or self.path or ''),
                'position_ms': self.player.position(), 'duration_ms': self.player.duration(),
                'mode': self.playlist.mode, 'track_count': len(self.playlist.tracks),
                'volume': self.volume, 'error': self.last_error}

    def _resolve(self, result):
        future, self._future = self._future, None
        if future is not None and not future.done(): future.set_result(result)

    def _animate(self, playing):
        canvas = self.character._live2d
        if canvas is not None: canvas.send('music_state', {'playing': playing})

    def _state_changed(self, state):
        playing = state == QMediaPlayer.PlaybackState.PlayingState
        self._animate(playing)
        if playing:
            self._loading = False
            self._load_timer.stop()
            self.last_error = ''
            self._resolve(self.status())
        self.changed.emit()

    def _media_status(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            generation = self._generation
            self._animate(False)
            QTimer.singleShot(0, lambda: self._advance_after_end(generation))

    def _advance_after_end(self, generation):
        if generation != self._generation: return
        self.refresh()
        if generation != self._generation: return
        logging.info("Local music ended: %s (mode=%s)", self.path, self.playlist.mode)
        path = self.playlist.next(automatic=True)
        if path: self._play(path)
        else:
            self.trigger_suppressed = False
            self.changed.emit()

    def _error(self, error, message):
        logging.warning("Local music error: %s: %s", self.path, message)
        self.trigger_suppressed = False
        self.last_error = str(message)
        self._generation += 1
        self._loading = False
        self._load_timer.stop()
        self.player.stop()
        self._animate(False)
        self._resolve(self.status())
        self.changed.emit()

    def cancel_pending(self):
        self.pending = None
        self.changed.emit()

    def stop(self, *, preserve_session=False):
        if not preserve_session:
            self.trigger_suppressed = False
        self._generation += 1
        self.pending = None
        self._loading = False
        self._load_timer.stop()
        self.player.stop()
        self._animate(False)
        self._resolve({'ok': False, 'error': 'Playback cancelled'})
        self.changed.emit()

    def _play(self, path, future=None):
        path = self.playlist.resolve_track(path)
        self.trigger_suppressed = True
        self.stop(preserve_session=True)
        self.path = self.playlist.select(path)
        logging.info("Local music play: %s (mode=%s)", self.path, self.playlist.mode)
        self.last_error = ''
        self._future = future
        self._loading = True
        self._load_timer.start(6000)
        self.player.setSource(QUrl.fromLocalFile(str(self.path)))
        self.player.play()
        self.changed.emit()

    def start_pending(self):
        path, self.pending = self.pending, None
        if path:
            try:
                self.refresh()
                self._play(path)
            except (ValueError, OSError) as exc: self._error(None, str(exc))

    def set_volume(self, value):
        self.volume = max(0., min(1., float(value)))
        self.output.setVolume(self.volume * (.25 if self._ducked else 1))
        self.changed.emit()

    def duck(self, speaking):
        self._ducked = speaking
        self.set_volume(self.volume)

    def seek(self, position):
        if self.player.isSeekable(): self.player.setPosition(max(0, min(int(position), self.player.duration())))

    def dispatch(self, payload, future, defer_for_reply=True):
        try:
            args = validate_music(payload)
            command = args['command']
            if command in ('list', 'play', 'next', 'previous'): self.refresh()
            if command == 'list':
                query = args.get('query', '').casefold()
                tracks = [p for p in self.playlist.tracks if query in p.name.casefold()]
                offset = args.get('offset', 0)
                result = {'ok': not bool(self.last_error), 'library': str(self.playlist.library),
                          'tracks': [{'name': p.name, 'path': str(p)} for p in tracks[offset:offset+80]],
                          'total': len(tracks), 'next_offset': offset+80 if offset+80 < len(tracks) else None,
                          'error': self.last_error}
            elif command in ('play', 'next', 'previous'):
                if command == 'next': path = self.playlist.next()
                elif command == 'previous': path = self.playlist.previous()
                elif args.get('path'): path = self.playlist.resolve_track(args['path'])
                else: path = self.playlist.current if self.playlist.current in self.playlist.tracks else self.playlist.next()
                if path is None: raise ValueError('曲库为空，请将成品音频放入「雪菜歌」文件夹')
                self.playback_requested.emit()
                self.character._reply_action = None
                if defer_for_reply and (self.character._reply_waiting or getattr(self.character.parent(), 'is_speaking', False)):
                    self.stop()
                    self.last_error = ''
                    self.pending = self.playlist.select(path)
                    result = self.status()
                    result['started'] = False
                else:
                    self._play(path, future)
                    return
            elif command == 'pause':
                if self.pending:
                    self.path = self.pending
                    self.cancel_pending()
                self._generation += 1
                self.player.pause()
                result = self.status()
            elif command == 'resume':
                if self.player.playbackState() != QMediaPlayer.PlaybackState.PausedState:
                    raise ValueError('没有暂停中的本地歌曲，请选择播放')
                self._future = future
                self._load_timer.start(6000)
                self.player.play()
                return
            elif command == 'set_mode':
                self.playlist.set_mode(args['mode'])
                result = self.status()
            elif command == 'stop':
                self.stop()
                self.last_error = ''
                result = self.status()
            else: result = self.status()
            self.changed.emit()
            future.set_result(result)
        except Exception as exc:
            if not future.done(): future.set_result({'ok': False, 'error': str(exc)})

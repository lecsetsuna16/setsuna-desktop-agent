import json
import os
import random
import re
from pathlib import Path
from typing import Dict, List, Optional
from PySide6.QtCore import Qt, QSize, QRect, Signal, QPoint, QTimer, QElapsedTimer, Property
from PySide6.QtGui import QPainter, QPaintEvent, QMouseEvent, QPixmap, QRegion
from PySide6.QtWidgets import QWidget, QGraphicsOpacityEffect
from resona_desktop_pet.interaction_effects import (
    INTERACTION_DURATIONS_MS,
    sample_interaction,
)

class CharacterView(QWidget):
    live2dRequested = Signal(object)
    leftClicked = Signal()
    rightClicked = Signal()
    physicalInteraction = Signal(str)
    
    def __init__(self, parent: QWidget = None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setSizePolicy(self.sizePolicy().Policy.Fixed, self.sizePolicy().Policy.Fixed)
        self._live2d = None
        self._reply_waiting = False
        self._reply_action = None
        from resona_desktop_pet.live2d.local_music import LocalMusic
        self.local_music = LocalMusic(self)
        self._render_opacity = 1.0
        self._sprite_opacity = None
        self.live2dRequested.connect(self._dispatch_live2d)
        self._pixmap: QPixmap = QPixmap()
        self._interaction_pixmap: QPixmap = QPixmap()
        self._interaction_opaque_bounds: QRect = QRect()
        self._scale: float = 1.0
        self.project_root: Optional[Path] = None
        self.current_outfit = "risona_outfit_00"
        self.current_emotion = "<E:smile>"
        self.emotion_map: Dict[str, List[str]] = {}
        self._opaque_bounds: QRect = QRect()
        self._interaction_kind = ""
        self._interaction_offset_x = 0
        self._interaction_offset_y = 0
        self._interaction_scale = 1.0
        self._interaction_scale_x = 1.0
        self._interaction_scale_y = 1.0
        self._interaction_rotation = 0.0
        self._interaction_progress = 0.0
        self._interaction_duration_ms = 0
        self._interaction_elapsed = QElapsedTimer()
        self._interaction_feedback_timer = QTimer(self)
        self._interaction_feedback_timer.setInterval(16)
        self._interaction_feedback_timer.timeout.connect(self._advance_interaction_feedback)
        
    def setup(self, project_root: Path, default_outfit: str = "risona_outfit_00"):
        self.project_root = project_root
        self.emotion_map = {}
        self.current_outfit = default_outfit
        print(f"[CharacterView] Setup with outfit: {default_outfit}")
        self._load_outfit(self.current_outfit)
        self._setup_live2d()

    def _resolve_pack_outfit(self, requested: str) -> str:
        try:
            config = getattr(self.parent(), "config", None)
            if config and hasattr(config, "pack_manager"):
                pack_manager = config.pack_manager
                outfits = pack_manager.get_info("character", {}).get("outfits", [])
                if outfits:
                    if any(o.get("id") == requested for o in outfits):
                        return requested
                    fallback = next((o for o in outfits if o.get("is_default")), outfits[0])
                    fallback_id = fallback.get("id")
                    if fallback_id:
                        print(f"[CharacterView] Outfit not in pack: {requested}, fallback: {fallback_id}")
                        return fallback_id
        except Exception as e:
            print(f"[CharacterView] Error resolving outfit id: {e}")
        return requested
        
    def _get_outfit_path(self, outfit: str, verbose: bool = False) -> Path:
        if not self.project_root: return Path(".")
        try:
            config = getattr(self.parent(), "config", None)
            if config and hasattr(config, "pack_manager"):
                pack_manager = config.pack_manager
                pack_id = pack_manager.active_pack_id
                pack_root = pack_manager.packs_dir / pack_id
                outfits = pack_manager.get_info("character", {}).get("outfits", [])
                target = next((o for o in outfits if o.get("id") == outfit), None)
                if target:
                    rel_path = target.get("path", "")
                    if rel_path:
                        candidate = Path(rel_path)
                        outfit_path = candidate if candidate.is_absolute() else pack_root / rel_path
                        if verbose: print(f"[CharacterView] Checking pack outfit path: {outfit_path}")
                        if outfit_path.exists() and (outfit_path / "sum.json").exists():
                            if verbose: print(f"[CharacterView] Using pack outfit path: {outfit_path}")
                            return outfit_path
                pack_outfit_path = pack_root / "assets" / "sprites" / outfit
                if verbose: print(f"[CharacterView] Checking pack outfit path: {pack_outfit_path}")
                if pack_outfit_path.exists() and (pack_outfit_path / "sum.json").exists():
                    if verbose: print(f"[CharacterView] Using pack outfit path: {pack_outfit_path}")
                    return pack_outfit_path
        except Exception as e:
            print(f"[CharacterView] Error resolving outfit path: {e}")
            pass
        return self.project_root / "resona_desktop_pet" / "ui" / "assets" / "modes" / outfit

    def get_available_outfits(self) -> List[str]:
        if not self.project_root: return []
        outfits = set()
        try:
            config = getattr(self.parent(), "config", None)
            if config and hasattr(config, "pack_manager"):
                pack_manager = config.pack_manager
                pack_id = pack_manager.active_pack_id
                pack_root = pack_manager.packs_dir / pack_id
                outfit_defs = pack_manager.get_info("character", {}).get("outfits", [])
                for outfit in outfit_defs:
                    outfit_id = outfit.get("id")
                    rel_path = outfit.get("path")
                    if outfit_id and rel_path:
                        candidate = Path(rel_path)
                        outfit_path = candidate if candidate.is_absolute() else pack_root / rel_path
                        if outfit_path.exists() and (outfit_path / "sum.json").exists():
                            outfits.add(outfit_id)
                if not outfits:
                    pack_sprites_path = pack_root / "assets" / "sprites"
                    if pack_sprites_path.exists():
                        for item in pack_sprites_path.iterdir():
                            if item.is_dir() and (item / "sum.json").exists(): outfits.add(item.name)
        except: pass
        modes_path = self.project_root / "resona_desktop_pet" / "ui" / "assets" / "modes"
        if modes_path.exists():
            for item in modes_path.iterdir():
                if item.is_dir() and (item / "sum.json").exists(): outfits.add(item.name)
        return sorted(list(outfits))

    def _load_outfit(self, outfit: str) -> bool:
        resolved = self._resolve_pack_outfit(outfit)
        outfit_path = self._get_outfit_path(resolved, verbose=True)
        print(f"[CharacterView] Loading outfit from: {outfit_path}")
        sum_json = outfit_path / "sum.json"
        if not sum_json.exists(): return False
        try:
            with open(sum_json, "r", encoding="utf-8") as f: self.emotion_map = json.load(f)
            self.current_outfit = resolved
            return True
        except: return False

    def set_outfit(self, outfit: str) -> bool:
        if self._load_outfit(outfit):
            self.set_emotion(self.current_emotion)
            return True
        return False

    def set_emotion(self, emotion: str, deterministic: bool = False) -> bool:
        self.current_emotion = emotion
        if self._live2d is not None:
            self._live2d.set_emotion(emotion)
            return True
        if emotion == "<E:smile>": deterministic = True
        if not self.emotion_map or self._resolve_pack_outfit(self.current_outfit) != self.current_outfit:
            self._load_outfit(self.current_outfit)
        if not self.emotion_map: return False
        sprites = self.emotion_map.get(emotion, [])
        if not sprites:
            base_emotion = emotion.split("|")[0] if "|" in emotion else emotion
            sprites = self.emotion_map.get(base_emotion, [])
        if not sprites:
            if emotion != "<E:smile>": return self.set_emotion("<E:smile>", deterministic=True)
            return False
        if deterministic:
            sprite_name = min(sprites, key=lambda s: sum(int(d) for d in s if d.isdigit()))
        else:
            sprite_name = random.choice(sprites)
        return self._load_sprite(sprite_name)

    def _load_sprite(self, sprite_name: str) -> bool:
        outfit_path = self._get_outfit_path(self.current_outfit)
        for ext in [".png", ".jpg", ".webp"]:
            sprite_path = outfit_path / f"{sprite_name}{ext}"
            if sprite_path.exists():
                pixmap = QPixmap(str(sprite_path))
                if not pixmap.isNull():
                    self._pixmap = pixmap
                    mask = pixmap.mask()
                    self._opaque_bounds = QRegion(mask).boundingRect() if not mask.isNull() else pixmap.rect()
                    self.updateGeometry(); self.update()
                    return True
        return False

    def set_scale(self, scale: float):
        minimum = 0.25 if self._live2d is not None else 0.5
        self._scale = max(minimum, min(scale, 1.0))
        self.updateGeometry(); self.update()
        
    def get_scale(self) -> float: return self._scale
        
    def sizeHint(self) -> QSize:
        if self._live2d is not None:
            return QSize(int(440 * self._scale), int(660 * self._scale))
        if not self._pixmap.isNull():
            return QSize(int(self._pixmap.width() * self._scale), int(self._pixmap.height() * self._scale))
        return QSize(int(320 * self._scale), int(360 * self._scale))
        
    def image_rect(self) -> QRect:
        tgt = self.sizeHint()
        return QRect((self.width() - tgt.width()) // 2, (self.height() - tgt.height()) // 2, tgt.width(), tgt.height())

    def content_rect(self) -> QRect:
        """Return the visible sprite bounds mapped into widget coordinates."""
        return self._content_rect_for_target(self.image_rect())

    def _content_rect_for_target(self, target: QRect) -> QRect:
        """Map visible source bounds into an arbitrary destination image rect."""
        if self._live2d is not None:
            return target.adjusted(int(target.width() * .08), int(target.height() * .03), -int(target.width() * .08), -int(target.height() * .03))
        pixmap = self._active_render_pixmap()
        source = (
            self._interaction_opaque_bounds
            if not self._interaction_pixmap.isNull()
            else self._opaque_bounds
        )
        if pixmap.isNull() or source.isEmpty():
            return target
        scale_x = target.width() / max(1, pixmap.width())
        scale_y = target.height() / max(1, pixmap.height())
        return QRect(
            target.left() + int(source.left() * scale_x),
            target.top() + int(source.top() * scale_y),
            max(1, int(source.width() * scale_x)),
            max(1, int(source.height() * scale_y)),
        )

    def head_interaction_rect(self) -> QRect:
        """Approximate the head from the visible character bounds, not PNG margins."""
        content = self.content_rect()
        side_margin = int(content.width() * 0.18)
        return QRect(
            content.left() + side_margin,
            content.top(),
            max(1, content.width() - side_margin * 2),
            max(1, int(content.height() * 0.38)),
        )

    def is_head_point(self, point: QPoint) -> bool:
        return self.head_interaction_rect().contains(point)

    def trigger_head_pat(self, point: QPoint) -> bool:
        return False

    def play_head_pat_feedback(self):
        """Backward-compatible entry point for the original head-pat effect."""
        self.play_interaction_feedback("head_pat")

    def trigger_physical_interaction(self, interaction: str):
        """Legacy touch actions are retired; retained for callers during reload."""
        return

    def play_interaction_feedback(self, interaction: str):
        """Ignore queued legacy touch animations."""
        return

    def _apply_interaction_frame(self, frame):
        self._interaction_offset_x = frame.offset_x
        self._interaction_offset_y = frame.offset_y
        self._interaction_scale = frame.scale
        self._interaction_scale_x = frame.scale_x
        self._interaction_scale_y = frame.scale_y
        self._interaction_rotation = frame.rotation

    @property
    def interaction_active(self) -> bool:
        return self._interaction_feedback_timer.isActive()

    def _active_render_pixmap(self) -> QPixmap:
        return self._interaction_pixmap if not self._interaction_pixmap.isNull() else self._pixmap

    def _load_hug_interaction_sprite(self) -> bool:
        sprite_names = {
            "setsuna_outfit_00": "set031124",
            "setsuna_outfit_01": "set025124",
        }
        sprite_name = sprite_names.get(self.current_outfit)
        if not sprite_name:
            return False
        outfit_path = self._get_outfit_path(self.current_outfit)
        for extension in (".png", ".webp", ".jpg"):
            path = outfit_path / f"{sprite_name}{extension}"
            if not path.exists():
                continue
            pixmap = QPixmap(str(path))
            if pixmap.isNull():
                continue
            self._interaction_pixmap = pixmap
            mask = pixmap.mask()
            self._interaction_opaque_bounds = (
                QRegion(mask).boundingRect() if not mask.isNull() else pixmap.rect()
            )
            return True
        return False

    def _reset_interaction_feedback(self):
        self._interaction_kind = ""
        self._interaction_offset_x = 0
        self._interaction_offset_y = 0
        self._interaction_scale = 1.0
        self._interaction_scale_x = 1.0
        self._interaction_scale_y = 1.0
        self._interaction_rotation = 0.0
        self._interaction_progress = 0.0
        self._interaction_pixmap = QPixmap()
        self._interaction_opaque_bounds = QRect()

    def _advance_interaction_feedback(self):
        duration = max(1, self._interaction_duration_ms)
        progress = self._interaction_elapsed.elapsed() / duration
        if progress >= 1.0:
            self._interaction_feedback_timer.stop()
            self._reset_interaction_feedback()
        else:
            self._interaction_progress = progress
            self._apply_interaction_frame(sample_interaction(self._interaction_kind, progress))
        self.update()

    def paintEvent(self, event: QPaintEvent):
        if self._live2d is not None:
            return
        painter = QPainter(self)
        painter.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform, True)
        rect = self.image_rect()
        width_scale = self._interaction_scale * self._interaction_scale_x
        height_scale = self._interaction_scale * self._interaction_scale_y
        width = max(1, int(rect.width() * width_scale))
        height = max(1, int(rect.height() * height_scale))
        if self._interaction_kind == "hug" and self._interaction_scale != 1.0:
            # Both requested hug sprites share the same canvas-aligned face point.
            # Keep that point visible while reframing toward a half-body close-up.
            face_x = rect.left() + int(rect.width() * 0.50)
            face_y = rect.top() + int(rect.height() * 0.285)
            zoom_fraction = min(
                1.0,
                max(0.0, (self._interaction_scale - 1.0) / 0.58),
            )
            desired_x = int(round(
                face_x + (rect.center().x() - face_x) * zoom_fraction
            ))
            desired_y_target = rect.top() + int(rect.height() * 0.31)
            desired_y = int(round(
                face_y + (desired_y_target - face_y) * zoom_fraction
            ))
            rect = QRect(
                desired_x - int(round(0.50 * width)),
                desired_y - int(round(0.285 * height)),
                width,
                height,
            )
        elif width_scale != 1.0 or height_scale != 1.0:
            center = rect.center()
            if self._interaction_kind == "head_pat":
                rect = QRect(
                    center.x() - width // 2,
                    rect.bottom() - height + 1,
                    width,
                    height,
                )
            else:
                rect = QRect(
                    center.x() - width // 2,
                    center.y() - height // 2,
                    width,
                    height,
                )
        rect.translate(
            int(round(self._interaction_offset_x)),
            int(round(self._interaction_offset_y)),
        )
        pixmap = self._active_render_pixmap()
        if not pixmap.isNull():
            if self._interaction_rotation:
                center = rect.center()
                painter.save()
                painter.translate(center.x(), center.y())
                painter.rotate(self._interaction_rotation)
                painter.translate(-center.x(), -center.y())
                painter.drawPixmap(rect, pixmap)
                painter.restore()
            else:
                painter.drawPixmap(rect, pixmap)
            
    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton: self.leftClicked.emit()
        elif event.button() == Qt.MouseButton.RightButton: self.rightClicked.emit()
        event.ignore()

    def dragEnterEvent(self, event):
        print(f"[CharacterView] dragEnterEvent")
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        print(f"[CharacterView] dropEvent")
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            parent = self.parent()
            if parent and hasattr(parent, 'on_file_dropped'):
                for url in event.mimeData().urls():
                    if url.isLocalFile():
                        file_path = url.toLocalFile()
                        if os.path.isfile(file_path):
                            path = Path(file_path)
                            file_info = {
                                "path": str(path),
                                "name": path.name,
                                "stem": path.stem,
                                "ext": path.suffix.lower() if path.suffix else ""
                            }
                            parent.on_file_dropped(file_info)

    @property
    def live2d_enabled(self):
        return self._live2d is not None

    def render_opacity(self):
        return self._render_opacity

    def set_render_opacity(self, value):
        self._render_opacity = max(0.0, min(1.0, float(value)))
        if self._live2d is not None:
            # QGraphicsEffect snapshots do not compose reliably with the
            # accelerated WebEngine child. Apply alpha in the model renderer.
            self._live2d.set_opacity(self._render_opacity)
        else:
            if self._sprite_opacity is None:
                self._sprite_opacity = QGraphicsOpacityEffect(self)
                self.setGraphicsEffect(self._sprite_opacity)
            self._sprite_opacity.setOpacity(self._render_opacity)

    renderOpacity = Property(float, render_opacity, set_render_opacity)

    def _setup_live2d(self):
        self.cancel_reply()
        self.local_music.stop()
        from resona_desktop_pet.live2d.protocol import live2d_settings
        if self._live2d is not None:
            self._live2d.dispose()
            self._live2d.hide()
            self._live2d.deleteLater()
            self._live2d = None
        if self._sprite_opacity is not None:
            self.setGraphicsEffect(None)
            self._sprite_opacity = None
        config = getattr(self.parent(), "config", None)
        if config is None:
            self.set_render_opacity(self._render_opacity)
            return
        pack_id, settings = live2d_settings(config)
        if not settings.get("enabled"):
            self.set_render_opacity(self._render_opacity)
            return
        root = (config.pack_manager.packs_dir / pack_id).resolve()
        model = (root / settings.get("model", "")).resolve()
        if not model.is_relative_to(root) or not model.is_file():
            raise ValueError("Live2D model is missing or outside the character pack")
        from resona_desktop_pet.live2d.canvas import Live2DCanvas
        self._live2d = Live2DCanvas(model, self)
        self.set_render_opacity(self._render_opacity)
        self._live2d.setGeometry(self.rect())
        self._live2d.show()
        self.updateGeometry()
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._live2d is not None:
            self._live2d.setGeometry(self.rect())

    def request_live2d(self, kind, payload=None):
        from concurrent.futures import Future
        future = Future()
        self.live2dRequested.emit((kind, payload or {}, future))
        return future

    def _dispatch_live2d(self, request):
        kind, payload, future = request
        if future.done():
            return
        if self._live2d is None:
            future.set_result({"ok": False, "ready": False, "error": "Active character has no Live2D renderer"})
        else:
            if kind == "local_music":
                self.local_music.dispatch(payload, future)
                return
            if kind == "status":
                # Renderer status remains authoritative; music has its own status tool.
                self._live2d.send(kind, payload, future)
                return
            if kind == "reset" or kind == "sing" and payload.get("command") == "stop":
                self._reply_action = None
                self.local_music.stop()
            if self._reply_waiting and (kind == "perform" or kind == "sing" and payload.get("command") == "start"):
                if self._reply_action or self.local_music.has_track:
                    future.set_result({"ok": False, "error": "A reply action or local song is already selected; do not repeat"})
                    return
                self._reply_action = (kind, dict(payload))
                future.set_result({"ok": True, "status": "queued_for_playback", "started": False})
                return
            self._live2d.send(kind, payload, future)

    def begin_reply(self):
        self._reply_action = None
        self._reply_waiting = True
        self.local_music.cancel_pending()

    def cancel_reply(self):
        self._reply_action = None
        self._reply_waiting = False
        self.local_music.cancel_pending()

    def start_reply_playback(self):
        self._reply_waiting = False
        action, self._reply_action = self._reply_action, None
        if action and self._live2d is not None and not self.local_music.has_track:
            kind, payload = action
            if kind == "sing":
                payload = dict(payload, reply_bound=True)
            else:
                payload = dict(payload, expression=self._live2d.emotion)
            self._live2d.send(kind, payload)
        if not getattr(self.parent(), "is_speaking", False):
            self.local_music.start_pending()

    def set_live2d_activity(self, state):
        if self._live2d is not None:
            self._live2d.set_activity(state)

    def set_live2d_audio(self, level, playing):
        if self._live2d is not None:
            self._live2d.send("audio", {"level": level, "playing": playing})

import os
import sys
import json
import random
import time
import threading
import ctypes
from pathlib import Path
from PySide6.QtCore import Qt, QTimer, Signal, QEvent, QPoint, QRect, QPropertyAnimation, QEasingCurve, QObject
from PySide6.QtGui import QMouseEvent, QWheelEvent, QPixmap, QCursor, QGuiApplication, QAction, QActionGroup, QIcon
from PySide6.QtWidgets import QWidget, QVBoxLayout, QMenu, QApplication
from resona_desktop_pet.config import ConfigManager
from resona_desktop_pet.physics import PhysicsBridge
from .character_view import CharacterView
from .io_overlay import IOOverlay

class MainWindow(QWidget):
    request_query = Signal(str)
    replay_requested = Signal()
    pack_changed = Signal(str)
    settings_requested = Signal()
    file_dropped = Signal(dict)
    def __init__(self, config: ConfigManager, parent: QWidget = None):
        super().__init__(parent)
        self.config = config
        
        self.topmost_timer = QTimer(self)
        self.topmost_timer.setInterval(2500)
        self.topmost_timer.timeout.connect(self._reinforce_topmost)
        
        self.stats = {
            "hover_start_time": 0.0,
            "press_start_time": 0.0,
            "drag_start_time": 0.0,
            "last_click_times": [], 
            "total_clicks": 0,
            "is_hovering": False,
            "is_pressing": False,
            "physics_acceleration": 0.0,
            "physics_bounce_count": 0,
            "physics_fall_distance": 0.0,
            "physics_window_collision_count": 0
        }
        self._physics_force_token = 0
        self._physics_force_restore = None
        self.input_hard_locked = False
        self.faded = False
        self.manual_hidden = False
        self.fullscreen_hidden = False
        self.is_processing = False
        self.is_listening = False
        self.is_speaking = False
        self.is_displaying_text = False
        self.fade_hover_recovery_sec = 0.0
        self._pack_change_handler_connected = False
        self._recent_drops = {}
        self.project_root = Path(self.config.config_path).parent
        
        self.setObjectName("MainRoot")
        self.character = CharacterView(self)
        self.io = IOOverlay(self)
        self.io.bind_music(self.character.local_music)
        # Idle fade hides dialogue; keep its reserved space so the character
        # stays anchored instead of jumping when the text reappears.
        dialogue_policy = self.io.sizePolicy()
        dialogue_policy.setRetainSizeWhenHidden(True)
        self.io.setSizePolicy(dialogue_policy)
        self.io.set_names(self.config.username, self.config.character_name)
        self.io.raise_()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.character, 0, Qt.AlignmentFlag.AlignCenter)
        self.setLayout(layout)

        self._apply_window_settings()

        self.character.setup(self.project_root, self.config.default_outfit)
        self.character.set_emotion("<E:smile>", deterministic=True)
        self.character.setMouseTracking(True)
        self.sync_window_to_sprite()

        img_rect = self.character.image_rect()
        if self.character._live2d is not None:
            self.character.set_scale(self._default_live2d_scale())
            self.ui_scale = self.character.get_scale()
        elif img_rect.width() > 0 and img_rect.height() > 0:
            target_w = self.config.sprite_width
            target_h = self.config.sprite_height
            scale_w = target_w / img_rect.width() if target_w > 0 else 999.0
            scale_h = target_h / img_rect.height() if target_h > 0 else 999.0
            initial_scale = min(scale_w, scale_h)
            if initial_scale == 999.0:
                initial_scale = 1.0
            self.character.set_scale(initial_scale)
            self.ui_scale = self.character.get_scale()
        else:
            self.ui_scale = 1.0
        self.character.setCursor(Qt.CursorShape.OpenHandCursor)
        self.installEventFilter(self)
        self.character.installEventFilter(self)
        self.io.installEventFilter(self)
        self.character.set_render_opacity(1.0)
        self.fade_anim = QPropertyAnimation(self.character, b"renderOpacity", self)
        self.fade_anim.setDuration(220)
        self.fade_anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self.idle_timer = QTimer(self)
        self.idle_timer.setSingleShot(True)
        self.idle_timer.setInterval(int(self.config.idle_fade_delay * 1000))
        self.idle_timer.timeout.connect(self.on_idle_timeout)
        self.faded = False
        self.fade_hover_recovery_sec = 0.0
        self.input_hard_locked = False
        self.dragging = False
        self.dragging_started = False
        self.drag_offset = QPoint()
        self.drag_mod = Qt.KeyboardModifier.NoModifier
        self.physics_pause_mod = Qt.KeyboardModifier.AltModifier
        self.physics_pause_until_next_drag = False
        self.physics_pause_after_drag = False
        self.thinking_texts = []
        self.load_thinking_texts()
        self.listening_texts = []
        self.load_listening_texts()
        self.thinking_timer = QTimer(self)
        self.thinking_timer.setSingleShot(True)
        self.thinking_timer.timeout.connect(self.show_thinking_text)
        self.thinking_switch_timer = QTimer(self)
        self.thinking_switch_timer.timeout.connect(self.switch_thinking_text)
        self.text_display_timer = QTimer(self)
        self.text_display_timer.setSingleShot(True)
        self.text_display_timer.timeout.connect(self._finish_text_display)
        self.idle_sprite_timer = QTimer(self)
        self.idle_sprite_timer.setInterval(60000)
        self.idle_sprite_timer.timeout.connect(self._on_idle_sprite_cycle)
        self.idle_sprite_timer.start()
        self.io.submitted.connect(self.on_query_submitted)
        self.io.text_changed.connect(self.on_input_text_changed)
        self.io.file_dropped.connect(self.on_file_dropped)
        self.character.rightClicked.connect(self.show_context_menu)
        
        QTimer.singleShot(0, self.sync_window_to_sprite)
        self.dialogue = self.DialogueAdapter(self)
        self.sprite = self.SpriteAdapter(self)

        # Physics
        self.physics_bridge = None
        if self.config.physics_enabled:
            self.physics_bridge = PhysicsBridge(self, self.config)

        self.setAcceptDrops(True)
        self.character.setAcceptDrops(True)
        self.io.setAcceptDrops(True)

        from resona_desktop_pet.live2d.mouse_gaze import MouseGazeController
        self._mouse_gaze = MouseGazeController(self)

    class DialogueAdapter:
        def __init__(self, window):
            self.window = window
            self.io = window.io
            self.input_field = self.io.edit 
        def set_text(self, text: str, animate: bool = False):
            if text == "Listening...":
                self.io.show_status(text)
            else:
                self.io.show_output(text) 
        def set_enabled(self, enabled: bool):
            if enabled:
                self.io.back_to_input_mode()
        def show_name(self, name: str):
            if "Thinking" in name or "Recording" in name:
                self.io.set_busy_header(name)
            else:
                self.io.set_busy_header(None)
                self.io.char_name = name
                self.io.update_header_text()
            self.io.header.update()
        def clear_text(self):
            self.io.edit.clear()

    class SpriteAdapter:
        def __init__(self, window):
            self.window = window
        def set_emotion(self, emotion: str):
            self.window.set_emotion(emotion)
        def get_thinking_sprite(self):
            self.window.set_emotion("<E:thinking>")

    def load_thinking_texts(self):
        thinking_path = self.config.pack_manager.get_path("logic", "thinking")
        self.thinking_texts = []
        if thinking_path and thinking_path.exists():
            try:
                with open(thinking_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        if data and isinstance(data[0], dict):
                            self.thinking_texts = [item.get("text", "") for item in data if isinstance(item, dict)]
                        else:
                            self.thinking_texts = [str(item) for item in data]
                print(f"[UI] Loaded {len(self.thinking_texts)} thinking texts")
            except Exception as e:
                print(f"Error loading thinking texts: {e}")

    def load_listening_texts(self):
        listening_path = self.config.pack_manager.get_path("logic", "listening")
        self.listening_texts = []
        if listening_path and listening_path.exists():
            try:
                with open(listening_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        if data and isinstance(data[0], dict):
                            self.listening_texts = [item.get("text", "") for item in data if isinstance(item, dict)]
                        else:
                            self.listening_texts = [str(item) for item in data]
                print(f"[UI] Loaded {len(self.listening_texts)} listening texts")
            except Exception as e:
                print(f"Error loading listening texts: {e}")

    def on_input_text_changed(self, text: str):
        if self.is_listening or self.is_processing or self.is_speaking or self.is_displaying_text:
            return
        if text.strip():
            if self.character.current_emotion != "<E:thinking>":
                self.set_emotion("<E:thinking>")
        else:
            if self.character.current_emotion != "<E:smile>":
                self.set_emotion("<E:smile>")

    def start_thinking(self):
        if self.is_listening: return
        self.text_display_timer.stop()
        self.character.begin_reply()
        self.character.set_live2d_activity("thinking")
        self.is_processing = True
        self.idle_sprite_timer.stop()
        self.cancel_idle_fade()
        self.set_emotion("<E:thinking>")
        status_name = f"[{self.config.character_name}] Thinking..."
        self.dialogue.show_name(status_name)
        
        self.set_input_locked(True, "Thinking...")
        
        if self.config.thinking_text_enabled:
            self.show_thinking_text()
            if self.config.thinking_text_switch:
                self.thinking_switch_timer.stop()
                self.thinking_switch_timer.start(int(self.config.thinking_text_switch_time * 1000))
        else:
            self.io.show_status("Thinking...")


    def on_query_submitted(self, text: str):
        if self.is_listening: return
        self.request_query.emit(text)
    
    def show_thinking_text(self):
        if self.is_listening or not self.is_processing: return
        if self.thinking_texts:
            text = random.choice(self.thinking_texts)
            self.io.show_status(text)
            if self.config.thinking_text_switch:
                self.thinking_switch_timer.stop()
                self.thinking_switch_timer.start(int(self.config.thinking_text_switch_time * 1000))
        else:
            self.io.show_status("Thinking...")
                
    def switch_thinking_text(self):
        if self.is_listening or not self.is_processing: return
        if not self.character.live2d_enabled:
            self.character.set_emotion("<E:thinking>")
        if self.thinking_texts:
            text = random.choice(self.thinking_texts)
            self.io.show_status(text)
            if self.config.thinking_text_switch:
                self.thinking_switch_timer.stop()
                self.thinking_switch_timer.start(int(self.config.thinking_text_switch_time * 1000))

    def show_listening_text(self):
        
        self.thinking_timer.stop()
        self.thinking_switch_timer.stop()
        if self.config.listening_text_enabled and self.listening_texts:
            text = random.choice(self.listening_texts)
            self.io.show_status(text)
        else:
            self.io.show_status("Listening...")

    def set_listening(self, listening: bool, username: str = "User"):
        self.is_listening = listening
        self.character.set_live2d_activity("listening" if listening else "idle")
        if listening:

            self.is_processing = False
            self.idle_sprite_timer.stop()
            self.thinking_timer.stop()
            self.thinking_switch_timer.stop()
            self.cancel_idle_fade()
            self.show_listening_text()
            status_name = f"[{username}] Recording..."
            self.dialogue.show_name(status_name)
        else:
            self.schedule_idle_fade()
            self.dialogue.show_name(self.config.character_name)

    def set_speaking(self, speaking: bool):
        self.is_speaking = speaking
        self.character.local_music.duck(speaking)
        if speaking:
            self.text_display_timer.stop()
            self.cancel_idle_fade()
        else:
            self.schedule_idle_fade()

    def set_input_locked(self, locked: bool, placeholder: str = None):
        self.io.edit.setReadOnly(locked)
        if locked:
            self.io.edit.clear()
            self.io.edit.setPlaceholderText(placeholder if placeholder else "Listening...")
        else:
            self.io.edit.setPlaceholderText("Type and press Enter...")

    def set_emotion(self, emotion_tag: str):
        self.character.set_emotion(emotion_tag)
        self.sync_window_to_sprite()

    def prepare_response(self, emotion: str):
        """Keep thinking until decoded audio actually starts playing."""
        self.idle_sprite_timer.stop()
        self.text_display_timer.stop()

    def show_response(self, text: str, emotion: str):
        self.character.set_live2d_activity("responding")
        self.is_processing = False 
        self.is_displaying_text = True
        self.thinking_timer.stop()
        self.thinking_switch_timer.stop()
        self.dialogue.show_name(self.config.character_name)
        self.set_emotion(emotion)
        self.io.show_output(text)
        self.character.start_reply_playback()


    def show_behavior_response_with_timeout(self, text: str, emotion: str):
        self.is_processing = False
        self.is_displaying_text = True
        self.cancel_idle_fade()
        self.show_response(text, emotion)
        reading_time = max(2.0, len(text) * self.config.text_read_speed * self.config.behavior_text_read_multiplier)
        self.text_display_timer.start(int(reading_time * 1000))

    def _finish_text_display(self):
        if not self.is_speaking:
            self.finish_processing()

    def finish_processing(self):
        self.character.cancel_reply()
        self.character.set_live2d_activity("idle")
        self.is_processing = False
        self.is_displaying_text = False
        self.is_speaking = False
        self.set_input_locked(False)
        self.io.back_to_input_mode()
        self.thinking_timer.stop()
        self.thinking_switch_timer.stop()
        self.text_display_timer.stop()
        self.set_emotion("<E:smile>")
        self.idle_sprite_timer.start()
        self.schedule_idle_fade()
        
    def _on_idle_sprite_cycle(self):
        if not self.is_processing and not self.is_listening and not self.is_speaking and not self.is_displaying_text:
            self.character.set_emotion("<E:smile>")

    def on_audio_complete(self):
        self.character.local_music.start_pending()
        self.text_display_timer.start(1500)

    def reset_to_default(self):
        self.finish_processing()
        
    def _default_live2d_scale(self):
        settings = self.config.pack_manager.get_info("character", {}).get("live2d", {})
        try:
            return max(0.5, min(1.0, float(settings.get("scale", 0.75))))
        except (TypeError, ValueError):
            return 0.75

    def _resize_content(self):
        layout = self.layout()
        if self.character._live2d is not None:
            # Reserve actual space for dialogue: a WebEngine child must never
            # share the text/input rectangle, regardless of native stacking.
            available = self.screen().availableGeometry()
            dialogue_w = min(max(320, self.config.dialogue_width or 380), available.width() - 24)
            dialogue_h = min(max(128, self.config.dialogue_height or 144), available.height() // 3)
            fit_scale = min((available.height() - dialogue_h - 32) / 660,
                            (available.width() - 24) / 440)
            self.character.set_scale(min(self.character.get_scale(), fit_scale))
            self.ui_scale = self.character.get_scale()
            size = self.character.sizeHint()
            self.character.setFixedSize(size)
            self.io.setFixedSize(dialogue_w, dialogue_h)
            layout.setSpacing(8)
            if layout.indexOf(self.io) < 0:
                layout.addWidget(self.io, 0, Qt.AlignmentFlag.AlignCenter)
            self.setFixedSize(max(size.width(), dialogue_w), size.height() + 8 + dialogue_h)
        else:
            # Restore the original sprite layout when changing character packs.
            if layout.indexOf(self.io) >= 0:
                layout.removeWidget(self.io)
            layout.setSpacing(0)
            for widget in (self.character, self.io):
                widget.setMinimumSize(0, 0)
                widget.setMaximumSize(16777215, 16777215)
            self.character.adjustSize()
            self.setFixedSize(self.character.sizeHint())
        layout.activate()
        self.io.raise_()

    def sync_window_to_sprite(self):
        self.keep_bottom_right_anchor(self._resize_content)
        self.update_io_geometry()
        self._reinforce_topmost()
        
    def keep_bottom_right_anchor(self, do_resize_func):
        br = self.frameGeometry().bottomRight()
        do_resize_func()
        fr = self.frameGeometry()
        new_tl = br - QPoint(fr.width() - 1, fr.height() - 1)
        if self.character._live2d is not None:
            available = self.screen().availableGeometry()
            new_tl.setX(max(available.left(), min(new_tl.x(), available.right() - fr.width() + 1)))
            new_tl.setY(max(available.top(), min(new_tl.y(), available.bottom() - fr.height() + 1)))
        self.move(new_tl)
        
    def apply_scale(self, s: float):
        self.character.set_scale(s)
        self.ui_scale = self.character.get_scale()
        self.sync_window_to_sprite()

    def _reinforce_topmost(self):
        if self.manual_hidden or self.fullscreen_hidden or not self.isVisible():
            return
        if self.config.always_on_top and sys.platform == "win32":
            try:
                if not (self.windowFlags() & Qt.WindowType.WindowStaysOnTopHint):
                    self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
                    self.show()
                    self.raise_()
                hwnd = self.winId()
                if not isinstance(hwnd, int):
                    hwnd = int(hwnd)
                ctypes.windll.user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010 | 0x0040)
            except:
                pass

    def _apply_window_settings(self):
        flags = Qt.WindowType.FramelessWindowHint
        if self.config.always_on_top:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        
        current_flags = self.windowFlags()
        if flags != current_flags:
            self.setWindowFlags(flags)
            if self.isVisible():
                super().show()
                self._reinforce_topmost()
                self.sync_window_to_sprite()
        
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_DropSiteRegistered, True)
        
        if not hasattr(self, '_drag_drop_initialized'):
            self.setAcceptDrops(True)
            self.character.setAcceptDrops(True)
            self.io.setAcceptDrops(True)
            self._drag_drop_initialized = True
        
        if not self.isVisible() and not self.manual_hidden:
            self.show()
            self.raise_()
            self._reinforce_topmost()
        elif self.isVisible():
            self.raise_()
            self._reinforce_topmost()
            if self.config.always_on_top:
                if not self.topmost_timer.isActive():
                    self.topmost_timer.start()
            else:
                self.topmost_timer.stop()


    def refresh_from_config(self):
        try:
            pack_id = getattr(self.config.pack_manager, "active_pack_id", "")
            print(f"[UI] Starting refresh_from_config... pack={pack_id} outfit={self.config.default_outfit}")
            self.character.setup(self.project_root, self.config.default_outfit)
            self.character.set_emotion("<E:smile>", deterministic=True)
            
            self.io.set_names(self.config.username, self.config.character_name)
            
            self.load_thinking_texts()
            self.load_listening_texts()
            
            self._apply_window_settings()

            if self.physics_bridge:
                self.physics_bridge.set_enabled(False)
                self.physics_bridge = None
            if self.config.physics_enabled:
                self.physics_bridge = PhysicsBridge(self, self.config)
            self.physics_pause_until_next_drag = False
            self.physics_pause_after_drag = False
            
            img_rect = self.character.image_rect()
            if self.character._live2d is not None:
                self.apply_scale(self._default_live2d_scale())
            elif img_rect.width() > 0 and img_rect.height() > 0:
                target_w = self.config.sprite_width
                target_h = self.config.sprite_height
                scale_w = target_w / (img_rect.width() / self.ui_scale)
                scale_h = target_h / (img_rect.height() / self.ui_scale)
                new_scale = min(scale_w, scale_h)
                self.apply_scale(new_scale)
            else:
                self.sync_window_to_sprite()
            
            print(f"[UI] refresh_from_config completed successfully.")
        except Exception as e:
            print(f"[UI] ERROR in refresh_from_config: {e}")
            import traceback
            traceback.print_exc()
        
    def check_idle_fade_allowed(self) -> bool:
        if getattr(self.io, "_music_requested", False):
            return False
        if getattr(self, "_mouse_gaze", None) and self._mouse_gaze.active:
            return False
        if self.config.always_show_ui or self.manual_hidden or self.fullscreen_hidden:
            return False
        if self.is_processing or self.is_listening or self.is_speaking or self.is_displaying_text:
            return False
        if self.io and self.io.edit:
            if self.io.edit.hasFocus():
                return False
            if self.io.edit.isVisible() and self.io.edit.isEnabled():
                if self.io.edit.toPlainText().strip():
                    return False
        if QApplication.activeModalWidget():
            return False
        if QApplication.activePopupWidget():
            return False
        active_window = QApplication.activeWindow()
        if active_window and active_window is not self:
            return False
        return True

    def update_io_geometry(self):
        if self.character._live2d is not None:
            self.io.set_bounds(self.io.geometry())
            self.io.raise_()
            return
        img_rect = self.character.image_rect()
        if img_rect.isEmpty():
            self.io.set_bounds(QRect())
            return
        char_pos = self.character.pos()
        img_x = char_pos.x() + img_rect.x()
        img_y = char_pos.y() + img_rect.y()
        img_w = img_rect.width()
        img_h = img_rect.height()
        conf_w = self.config.dialogue_width
        conf_h = self.config.dialogue_height
        w = conf_w if conf_w > 0 else int(img_w * 0.6)
        h = conf_h if conf_h > 0 else int(img_h * 0.25)
        h = max(60, h)
        x = img_x + (img_w - w) // 2
        y = img_y + img_h - h + 5
        box = QRect(x, y, w, h)
        box.adjust(0, 4, 0, -4)
        self.io.set_bounds(box)

    def get_sprite_collision_rect(self):
        img_rect = self.character.image_rect()
        if img_rect.isEmpty():
            return self.frameGeometry()
        char_pos = self.character.pos()
        top_left = self.mapToGlobal(char_pos + img_rect.topLeft())
        return QRect(top_left, img_rect.size())

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        event_type = event.type()
        
        if event_type in (QEvent.DragEnter, QEvent.DragMove, QEvent.DragLeave, QEvent.Drop):
            return super().eventFilter(obj, event)
        
        now = time.time()
        

        is_input_event = event.type() in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease, 
                                          QEvent.MouseMove, QEvent.Wheel, QEvent.KeyPress, QEvent.KeyRelease)
        if self.input_hard_locked and is_input_event:
            return True

        if obj == self.character:
            if event.type() == QEvent.Enter:
                self.stats["is_hovering"] = True
                self.stats["hover_start_time"] = now
            elif event.type() == QEvent.Leave:
                self.stats["is_hovering"] = False
                self.stats["hover_leave_time"] = now
            
            
            if self.faded and self.fade_hover_recovery_sec > 0 and self.stats["is_hovering"]:
                if (now - self.stats["hover_start_time"]) >= self.fade_hover_recovery_sec:
                    self.cancel_idle_fade()
                    self.fade_hover_recovery_sec = 0.0

            if event.type() == QEvent.MouseButtonPress:
                if event.button() == Qt.MouseButton.LeftButton:
                    self.stats["is_pressing"] = True
                    self.stats["press_start_time"] = now
                    self.stats["last_click_times"].append(now)
                    self.stats["last_click_times"] = self.stats["last_click_times"][-20:] 
                    self.stats["total_clicks"] += 1
                    if hasattr(self, "controller") and self.controller:
                        self.controller.state["total_clicks"] = self.stats["total_clicks"]
                        self.controller._save_state()
            elif event.type() == QEvent.MouseButtonRelease:
                if event.button() == Qt.MouseButton.LeftButton:
                    self.stats["is_pressing"] = False
        w = obj if isinstance(obj, QWidget) else None
        on_self = (obj == self)
        on_character = (obj == self.character)
        on_overlay = (w == self.io or self.io.isAncestorOf(w)) if w else False
        is_relevant_widget = on_self or on_character or on_overlay
        if on_self and event.type() == QEvent.MouseMove:
            me = event 
            last_pos = getattr(self, "_last_mouse_pos", QPoint(-999, -999))
            curr_pos = me.pos()
            self._last_mouse_pos = curr_pos
            if (curr_pos - last_pos).manhattanLength() > 2:
                if self.faded and self.io.geometry().contains(curr_pos):
                    self.cancel_idle_fade()
                elif is_relevant_widget:
                    self.cancel_idle_fade()
        if is_relevant_widget:
            if event.type() == QEvent.MouseButtonPress:
                self.cancel_idle_fade()
            elif event.type() == QEvent.Enter:
                self.cancel_idle_fade()
            elif event.type() == QEvent.Leave:
                QTimer.singleShot(100, self.schedule_idle_fade)
            elif event.type() in (QEvent.KeyPress, QEvent.KeyRelease, QEvent.InputMethod):
                self.cancel_idle_fade()
                self.schedule_idle_fade()
        if event.type() == QEvent.Wheel and (on_character or on_overlay):
            we = event 
            mods = we.modifiers()
            if mods & Qt.KeyboardModifier.AltModifier and not mods & Qt.KeyboardModifier.ControlModifier:
                delta = we.angleDelta().y() or we.angleDelta().x()
                direction = 1 if delta > 0 else -1 if delta < 0 else 0
                if direction != 0:
                    s = self.character.get_scale() + direction * 0.05
                    s = max(0.5, min(s, 1.0))
                    self.apply_scale(s)
                return True
        if (on_self or on_character) and self.character.live2d_enabled:
            from resona_desktop_pet.live2d.mouse_gaze import gaze_chord_down
            if event.type() in (QEvent.MouseButtonPress, QEvent.MouseButtonDblClick, QEvent.MouseMove) and gaze_chord_down():
                self.dragging = self.dragging_started = False
                return True
        if on_self or on_character:
            if event.type() == QEvent.MouseButtonPress:
                me = event 
                if me.button() == Qt.MouseButton.LeftButton:
                    if self.physics_pause_until_next_drag and self.physics_bridge:
                        self.physics_bridge.set_enabled(True)
                        self.physics_pause_until_next_drag = False
                    want_drag = (self.drag_mod == Qt.KeyboardModifier.NoModifier) or (me.modifiers() & self.drag_mod)
                    if want_drag:
                        self.dragging = True
                        self.dragging_started = False
                        self.drag_offset = me.globalPosition().toPoint() - self.frameGeometry().topLeft()
                        self.physics_pause_after_drag = self._should_pause_physics_for_drag(me.modifiers())
                        self.character.setCursor(Qt.CursorShape.ClosedHandCursor)
                        return True
            elif event.type() == QEvent.MouseMove:
                if self.dragging:
                    me = event 
                    cur = me.globalPosition().toPoint()
                    thresh = QApplication.startDragDistance()
                    if not self.dragging_started:
                        delta = cur - (self.drag_offset + self.frameGeometry().topLeft())
                        if delta.manhattanLength() < thresh:
                            return True
                        self.dragging_started = True
                    self.move(cur - self.drag_offset)
                    return True
                if on_character and event.buttons() == Qt.MouseButton.NoButton:
                    cursor = (Qt.CursorShape.PointingHandCursor
                              if self.character.is_head_point(event.position().toPoint())
                              else Qt.CursorShape.OpenHandCursor)
                    self.character.setCursor(cursor)
            elif event.type() == QEvent.MouseButtonRelease:
                if self.dragging:
                    self.dragging = False
                    self.dragging_started = False
                    self.character.setCursor(Qt.CursorShape.OpenHandCursor)
                    if self.physics_pause_after_drag and self.physics_bridge:
                        self.physics_bridge.set_enabled(False)
                        self.physics_pause_until_next_drag = True
                    self.physics_pause_after_drag = False
                    return True
        if on_character and event.type() == QEvent.Resize:
            self.update_io_geometry()
        return super().eventFilter(obj, event)

    def on_idle_timeout(self):
        if not self.check_idle_fade_allowed():
            self.idle_timer.start()
            return
        self.faded = True
        self.io.setVisible(False)
        self.fade_to(self.config.idle_opacity)
        
    def set_hard_lock(self, locked: bool, highlight: bool = False):
        self.input_hard_locked = locked
        if locked:
            self.io.setVisible(False)
            if highlight:
                self.fade_to(1.0)
                self.character.set_render_opacity(1.0)
            self.character.setCursor(Qt.CursorShape.ForbiddenCursor)
        else:
            self.io.setVisible(True)
            self.character.setCursor(Qt.CursorShape.OpenHandCursor)

    def set_fade_recovery(self, sec: float):
        if sec > 0:
            self.faded = True
            self.fade_hover_recovery_sec = sec
        else:
            self.fade_hover_recovery_sec = 0.0

    def cancel_idle_fade(self):
        self.idle_timer.stop()
        self.fade_hover_recovery_sec = 0.0
        if self.faded:
            self.faded = False
            if not self.input_hard_locked:
                self.io.setVisible(True)
            self.fade_to(1.0)
            
    def schedule_idle_fade(self):
        if not self.check_idle_fade_allowed():
            return
        if not self.idle_timer.isActive():
            self.idle_timer.start()
            
    def fade_to(self, target: float):
        self.fade_anim.stop()
        self.fade_anim.setStartValue(self.character.render_opacity())
        self.fade_anim.setEndValue(target)
        self.fade_anim.start()
        
    def set_fullscreen_hidden(self, hidden: bool):
        self.fullscreen_hidden = hidden
        self._update_visibility()
        
    def manual_hide(self):
        self.manual_hidden = True
        self._update_visibility()
        
    def manual_show(self):
        controller = getattr(self, "controller", None)
        if controller and getattr(controller, "_pack_switch_pending", False):
            print("[UI] manual_show blocked during pack switch")
            return
        self.manual_hidden = False
        self.cancel_idle_fade()
        self._apply_window_settings()


    def _update_visibility(self):
        controller = getattr(self, "controller", None)
        pack_switch_pending = bool(controller and getattr(controller, "_pack_switch_pending", False))
        should_hide = self.manual_hidden or self.fullscreen_hidden or pack_switch_pending
        if should_hide:
            if self.isVisible():
                super().hide()
        else:
            if not self.isVisible():
                super().show()
                self._reinforce_topmost()

    def safe_set_outfit(self, outfit: str):
        try:
            self.character.set_outfit(outfit)
        except Exception as e:
            print(f"Error switching outfit: {e}")
            
    def show_context_menu(self):
        menu = QMenu(self)
        menu.addAction("Replay Last Response", self.replay_requested.emit)
        self.populate_interaction_menu(menu.addMenu("互动"))
        menu.addSeparator()
        settings_action = menu.addAction("Settings", self.settings_requested.emit)
        menu.setStyleSheet("""
            QMenu {
                background-color: rgba(40, 40, 40, 230);
                border: 1px solid 
                border-radius: 5px;
                padding: 5px;
            }
            QMenu::item {
                color: white;
                padding: 8px 20px;
                border-radius: 3px;
            }
            QMenu::item:selected {
                background-color: rgba(100, 100, 100, 200);
            }
            QMenu::separator {
                height: 1px;
                background: 
                margin: 5px 10px;
            }
        """ )
        if self.character.live2d_enabled:
            menu.addAction("歌曲播放器", self.show_music_player)
            menu.addAction("Live2D 功能测试", self.show_live2d_controls)
            from resona_desktop_pet.live2d.mouse_gaze import HINT
            menu.addAction(HINT).setEnabled(False)
        outfit_menu = menu.addMenu("Change Outfit")
        outfit_menu.setEnabled(not self.character.live2d_enabled)
        self.populate_outfit_menu(outfit_menu)
        pack_menu = menu.addMenu("Change Character Pack")
        self.populate_pack_menu(pack_menu)
        menu.addSeparator()
        drag_menu = menu.addMenu("Drag Binding")
        self.populate_drag_menu(drag_menu)
        pause_menu = menu.addMenu("Physics Drag Pause Binding")
        self.populate_physics_pause_menu(pause_menu)
        menu.addSeparator()
        hide_action = menu.addAction("Hide (Background)")
        hide_action.triggered.connect(self.manual_hide)
        menu.addAction("Close", self.close)
        menu.exec(QCursor.pos())

    def populate_interaction_menu(self, menu: QMenu):
        sing = menu.addAction("唱歌动作")
        sing.setEnabled(self.character.live2d_enabled)
        sing.triggered.connect(lambda: self.character.request_live2d("sing", {"command": "start", "duration_seconds": 16}))
        stop = menu.addAction("停止唱歌")
        stop.setEnabled(self.character.live2d_enabled)
        stop.triggered.connect(lambda: self.character.request_live2d("sing", {"command": "stop"}))
        
    def populate_outfit_menu(self, menu: QMenu):
        outfits = self.character.get_available_outfits()
        grp = QActionGroup(menu)
        grp.setExclusive(True)
        for outfit in outfits:
            action = menu.addAction(outfit)
            action.setCheckable(True)
            action.setChecked(outfit == self.character.current_outfit)
            action.triggered.connect(lambda checked, o=outfit: self.safe_set_outfit(o))
            grp.addAction(action)

    def _on_pack_selected(self, pack_id: str):
        print(f"[UI] Pack menu selected: {pack_id}")
        self.pack_changed.emit(pack_id)
        if self._pack_change_handler_connected:
            return
        controller = getattr(self, "controller", None)
        if controller and hasattr(controller, "_handle_pack_change"):
            print("[UI] Pack handler not connected, invoking controller directly.")
            controller._handle_pack_change(pack_id)
        print(f"[UI] Fallback refresh scheduled for pack: {pack_id}")
        QTimer.singleShot(2000, lambda pid=pack_id: self._fallback_refresh_after_pack_change(pid))

    def _fallback_refresh_after_pack_change(self, pack_id: str):
        try:
            controller = getattr(self, "controller", None)
            if controller and getattr(controller, "_pack_switch_pending", False):
                print(f"[UI] Fallback skipped: pack switch pending for {pack_id}")
                return
            current_id = getattr(self.config.pack_manager, "active_pack_id", "")
            if current_id != pack_id:
                print(f"[UI] Fallback syncing pack_id: {current_id} -> {pack_id}")
                self.config.pack_manager.set_active_pack(pack_id)
                self.config.set("General", "active_pack", pack_id)
                self.config.save()
            self.config.load()
            print(f"[UI] Fallback refresh_from_config... pack={pack_id} outfit={self.config.default_outfit}")
            self.refresh_from_config()
            self.manual_show()
        except Exception as e:
            print(f"[UI] Fallback refresh error: {e}")

    def populate_pack_menu(self, menu: QMenu):
        packs = self.config.pack_manager.get_available_packs()
        active_id = self.config.pack_manager.active_pack_id
        grp = QActionGroup(menu)
        grp.setExclusive(True)
        for p_id in packs:
            action = menu.addAction(p_id)
            action.setCheckable(True)
            action.setChecked(p_id == active_id)
            action.triggered.connect(lambda checked, pid=p_id: self._on_pack_selected(pid))
            grp.addAction(action)

    def populate_drag_menu(self, menu: QMenu):
        group = QActionGroup(menu)
        group.setExclusive(True)
        opts = [("Alt", Qt.KeyboardModifier.AltModifier), 
                ("Ctrl", Qt.KeyboardModifier.ControlModifier),
                ("Shift", Qt.KeyboardModifier.ShiftModifier),
                ("None", Qt.KeyboardModifier.NoModifier)]
        for label, mod in opts:
            action = QAction(label, menu)
            action.setCheckable(True)
            action.setChecked(self.drag_mod == mod)
            action.triggered.connect(lambda checked, m=mod: self.set_drag_mod(m))
            group.addAction(action)
            menu.addAction(action)
            
    def set_drag_mod(self, mod):
        self.drag_mod = mod

    def populate_physics_pause_menu(self, menu: QMenu):
        group = QActionGroup(menu)
        group.setExclusive(True)
        opts = [("Alt", Qt.KeyboardModifier.AltModifier),
                ("Ctrl", Qt.KeyboardModifier.ControlModifier),
                ("Shift", Qt.KeyboardModifier.ShiftModifier),
                ("None", Qt.KeyboardModifier.NoModifier)]
        for label, mod in opts:
            action = QAction(label, menu)
            action.setCheckable(True)
            action.setChecked(self.physics_pause_mod == mod)
            action.triggered.connect(lambda checked, m=mod: self.set_physics_pause_mod(m))
            group.addAction(action)
            menu.addAction(action)

    def set_physics_pause_mod(self, mod):
        self.physics_pause_mod = mod

    def _should_pause_physics_for_drag(self, mods):
        if self.physics_pause_mod == Qt.KeyboardModifier.NoModifier:
            return mods == Qt.KeyboardModifier.NoModifier
        return bool(mods & self.physics_pause_mod)

    @property
    def is_busy(self) -> bool:
        return self.is_processing or self.is_speaking or self.is_listening
        
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            print(f"[UI] dragEnterEvent received URLs: {[u.toLocalFile() for u in event.mimeData().urls()]}")
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            print(f"[UI] dropEvent received URLs")
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
                        self.on_file_dropped(file_info)
                        print(f"[UI] File dropped: {file_info}")
            event.acceptProposedAction()

    def on_file_dropped(self, file_info: dict):
        # Qt child widgets and WM_DROPFILES may report the same native gesture.
        path = Path(file_info.get("path", "")).resolve()
        if not path.is_file():
            return
        key = os.path.normcase(str(path))
        now = time.monotonic()
        self._recent_drops = {k: t for k, t in self._recent_drops.items() if now - t < 0.3}
        if key in self._recent_drops:
            return
        self._recent_drops[key] = now
        self.file_dropped.emit({"path": str(path), "name": path.name,
                                "stem": path.stem, "ext": path.suffix.lower()})

    def showEvent(self, event):
        super().showEvent(event)
        if sys.platform == "win32":
            try:
                hwnd = int(self.winId())
                ctypes.windll.shell32.DragAcceptFiles(hwnd, True)
                
                GWL_EXSTYLE = -20
                WS_EX_ACCEPT_FILES = 0x00000010
                current_style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, current_style | WS_EX_ACCEPT_FILES)
            except Exception as e:
                pass
        if not hasattr(self, '_initial_position_set'):
            screen = QGuiApplication.primaryScreen().availableGeometry()
            self.move(screen.bottomRight() - QPoint(self.width() + 24, self.height() + 24))
            self._initial_position_set = True
        self.sync_window_to_sprite()
        self._reinforce_topmost()

    def closeEvent(self, event):
        controller = getattr(self, "controller", None)
        if controller and hasattr(controller, "force_exit"):
            threading.Thread(target=controller.force_exit, daemon=True).start()
            event.accept()
            return
        QApplication.instance().quit()
        super().closeEvent(event)

    def nativeEvent(self, event_type, message):
        if event_type == "windows_dispatcher_MSG":
            msg = ctypes.wintypes.MSG.from_address(message.__int__())
            if msg.message == 0x0233:
                hdrop = msg.wParam
                file_count = ctypes.windll.shell32.DragQueryFileW(hdrop, 0xFFFFFFFF, None, 0)
                for i in range(file_count):
                    buf_len = 260
                    buf = ctypes.create_unicode_buffer(buf_len)
                    ctypes.windll.shell32.DragQueryFileW(hdrop, i, buf, buf_len)
                    file_path = buf.value
                    if os.path.isfile(file_path):
                        path = Path(file_path)
                        file_info = {
                            "path": str(path),
                            "name": path.name,
                            "stem": path.stem,
                            "ext": path.suffix.lower() if path.suffix else ""
                        }
                        print(f"[UI] Windows native drop: {file_info}")
                        self.on_file_dropped(file_info)
                ctypes.windll.shell32.DragFinish(hdrop)
                return True, 0
        return super().nativeEvent(event_type, message)

    def show_music_player(self):
        self.io.show_music()

    def show_live2d_controls(self):
        from resona_desktop_pet.live2d.controls import Live2DControls
        if not hasattr(self, "_live2d_controls"):
            self._live2d_controls = Live2DControls(self.character, self)
        self._live2d_controls.show()
        self._live2d_controls.raise_()

# 🖼️ User Interface Components

UI modules are located in `resona_desktop_pet/ui/` and built using PySide6.

## 1. MainWindow (`luna/main_window.py`)
The central UI controller of the application.
- **Frameless Transparent Window**: Achieves the transparent floating effect for the desktop pet.
- **State Management**: Orchestrates states like "Idle", "Thinking", "Speaking", and "Recording".
- **Interaction Handling**: Manages dragging, scaling (Alt+Scroll), and context menu interactions.
- **Auto Hide/Fade**: Supports automatic hiding in full-screen mode and idle fading after periods of inactivity.

## 2. CharacterView (`luna/character_view.py`)
Responsible for rendering character sprites.
- **Outfit Support**: Indexes different outfit directories based on `sum.json`.
- **Emotion Switching**: Maps emotion tags to specific image files via random or deterministic selection.
- **High-Performance Rendering**: Optimized scaling for smooth display on transparent backgrounds.

## 3. IOOverlay (`luna/io_overlay.py`)
The dialogue box component.
- **Unified Input/Output**: Supports both user text input and LLM response display.
- **Auto Positioning**: Automatically adjusts the dialogue box position relative to the character sprite.
- **Animations**: Features smooth fading effects for a better visual experience.

## 4. Tray Icon (`tray_icon.py`)
- Enables background operation.
- Provides a quick-access menu for settings, pack switching, and exiting.

## 5. Settings Dialog (`settings_dialog.py` / `simple_settings.py`)
- **Advanced Settings**: Provides detailed configuration for API keys, TTS parameters, and UI behavior.
- **Simple Mode**: A streamlined configuration interface designed for beginners.

---
Parts of this document were generated with the assistance of large language models, and translations were also completed by large language models. Any deviations do not represent the author's true intent.

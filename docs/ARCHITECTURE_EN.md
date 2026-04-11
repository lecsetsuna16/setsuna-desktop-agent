# 🛠️ Technical Architecture

The project adopts a modular design, divided into the UI Layer, Logic Control Layer, and Backend Service Layer.

## 1. Core Technology Stack
- **UI Framework**: PySide6 (Python + Qt)
- **LLM**: OpenAI API compatible / Gemini API / Claude API
- **TTS**: GPT-SoVITS (Local inference server)
- **STT**: SenseVoice (Offline engine based on sherpa-onnx)
- **Image Processing**: Pillow (PIL)

## 2. Directory Structure
```text
D:\GitHub\Resona-Desktop-Pet\
├── main.py                     # Entry point
├── resona_desktop_pet/         # Core source code
│   ├── backend/                # Backend services (LLM/TTS/STT)
│   ├── config/                 # Configuration and Pack management
│   ├── ui/                     # User interface components
│   └── behavior_monitor.py      # System monitoring and trigger logic
├── packs/                      # Resource pack storage
├── tools/                      # Dev and debug tools
└── docs/                       # Documentation
```

## 3. Workflow
1. **Initialization**:
   - Loads `config.cfg` and the selected `pack.json`.
   - Initializes UI (MainWindow) and Backend Services (LLM/TTS/STT).
   - Starts `BehaviorMonitor` to listen for system events and user interactions.
2. **Active Interaction**:
   - User clicks the sprite or uses a hotkey to start STT.
   - STT converts voice to text and sends it to the LLM.
   - LLM generates a JSON response with emotion tags based on the prompt.
   - TTS Backend synthesizes voice based on emotion tags; UI displays text and updates sprite emotions.
3. **Passive Interaction (Triggers)**:
   - `BehaviorMonitor` polls sensor data (CPU/GPU, etc.) or listens to system hooks (window switching).
   - Matches conditions defined in the pack's `triggers.json`.
   - Executes feedback sequences as defined in `actions` (speak, move, fade, etc.).

## 4. Decoupled Backend Services
- **LLMBackend**: Wraps API calls from different providers into a unified `LLMResponse` object.
- **TTSBackend**: Communicates with GPT-SoVITS via HTTP API, dynamically fetching reference audio from the active pack.
- **STTBackend**: Runs in a separate thread/async task, capturing audio via `pyaudio` and performing local recognition using `sherpa-onnx`.

---
Parts of this document were generated with the assistance of large language models, and translations were also completed by large language models. Any deviations do not represent the author's true intent.

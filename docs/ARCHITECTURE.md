# 🛠️ 技术架构 (Technical Architecture) 

本项目采用模块化设计，主要分为 UI 层、逻辑控制层与后端服务层。

## 1. 核心技术栈
- **UI 框架**：PySide6 (Python + Qt)
- **大语言模型 (LLM)**：OpenAI API 兼容接口 / Gemini API / Claude API
- **语音合成 (TTS)**：GPT-SoVITS (本地推理服务器)
- **语音识别 (STT)**：SenseVoice (基于 sherpa-onnx 的本地离线引擎)
- **图像处理**：Pillow (PIL)

## 2. 目录结构说明
```text
D:\GitHub\Resona-Desktop-Pet\
├── main.py                     # 程序入口
├── resona_desktop_pet/         # 核心源代码
│   ├── backend/                # 后端服务模块 (LLM/TTS/STT)
│   ├── config/                 # 配置与资源包管理
│   ├── ui/                     # 用户界面组件
│   └── behavior_monitor.py      # 系统监控与触发逻辑核心
├── packs/                      # 资源包存储目录
├── tools/                      # 开发与调试辅助工具
└── docs/                       # 项目文档
```

## 3. 工作流程
1. **启动阶段**：
   - 加载 `config.cfg` 及选定的 `pack.json`。
   - 初始化 UI (MainWindow) 及后端服务 (LLM/TTS/STT)。
   - 启动 `BehaviorMonitor` 监听系统事件与用户交互。
2. **交互阶段 (主动)**：
   - 用户点击立绘或使用快捷键启动 STT。
   - STT 将语音转为文本发送给 LLM。
   - LLM 根据提示词 (Prompt) 生成包含情感标签的 JSON 响应。
   - TTS 后端根据情感标签合成语音，UI 显示文本并切换立绘情感。
3. **交互阶段 (被动/触发)**：
   - `BehaviorMonitor` 轮询传感器数据（CPU/GPU 等）或监听系统钩子（窗口切换）。
   - 匹配资源包中 `triggers.json` 定义的条件。
   - 按照定义的 `actions` 序列执行反馈（说话、移动、渐变等）。

## 4. 后端服务解耦
- **LLMBackend**：封装了不同供应商的 API 调用，统一输出为结构化的 `LLMResponse` 对象。
- **TTSBackend**：通过 HTTP API 与 GPT-SoVITS 交互，动态从当前资源包读取参考音频。
- **STTBackend**：运行在独立的线程或异步任务中，通过 `pyaudio` 采集音频并使用 `sherpa-onnx` 本地识别。

---
本文档部分使用大语言模型辅助生成，翻译亦由大语言模型完成，如出现任何偏差不代表作者的真实意愿。

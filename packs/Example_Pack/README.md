# Resona 角色包制作指南 (示例)

欢迎使用 Resona 角色包示例！这个文件夹展示了一个标准的角色包结构，你可以基于此创建你自己的角色。

## 目录结构说明

- **`pack.json`**: 核心配置文件，定义了角色的名称、版本、模型路径以及逻辑文件路径。
- **`assets/`**: 资源文件夹。
    - **`audio/`**: 存放角色的语音文件（如 `.wav` 格式）。
    - **`sprites/`**: 存放角色的立绘图片（`.png` 格式）。
        - **`sum.json`**: **重要**。定义了 9 种表情对应的图片文件名。
- **`logic/`**: 逻辑配置文件。
    - **`emotions.json`**: **重要**。定义 9 种表情对应的语音参考（TTS 使用）。
    - **`triggers.json`**: 定义各种自动触发事件。
- **`prompts/`**: 存放角色的系统提示词（System Prompt）。

---

## 核心规范

### 1. 九种支持的情绪 (Emotions)
本程序目前支持以下 9 种固定情绪标签。在 `sum.json`、`emotions.json` 以及 AI 的 Prompt 中必须使用这些标签：

- `<E:smile>`：微笑、得意、开心
- `<E:serious>`：普通状态、认真、冷淡
- `<E:angry>`：生气、吐槽、大声
- `<E:sad>`：消沉、叹气、示弱
- `<E:thinking>`：思考、疑惑
- `<E:surprised>`：惊讶、惊吓
- `<E:dislike>`：嫌弃、恶心、讨厌
- `<E:smirk>`：嘲笑、坏笑、阴险
- `<E:embarrassed>`：害羞、傲娇、脸红

### 2. Prompt (提示词) 编写规范
为了让 AI 能够正确驱动桌宠，Prompt 必须包含以下要素：
- **JSON 格式强制约束**：AI 必须只输出包含 `emotion`, `text_display`, `text_tts` 的 JSON。
- **双语言规则**：`text_display` 遵循用户语言，`text_tts` 必须强制转换为**日语（或者任何SoVITS支持的语言）**。
- **情绪白名单**：在 Prompt 中列出上述 9 种情绪，要求 AI 根据语境选择。
- **短句限制**：为了用户体验，建议限制在 4 句话以内。

你可以在 `prompts/character_prompt.txt` 中找到已经写好的**模范模板**，只需修改其中的 `[角色名]`、`[背景设定]` 等括起来的部分即可直接工作。

---

## 如何制作
1. 修改 `pack.json` 中的基本信息。
2. 在 `prompts/character_prompt.txt` 中填入你的角色设定。
3. 准备 9 种表情的立绘，放入 `assets/sprites/` 并对应修改 `sum.json`。
4. 在 `logic/emotions.json` 中配置你的 TTS 参考音频。
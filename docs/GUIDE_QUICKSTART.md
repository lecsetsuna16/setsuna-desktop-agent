# Resona Desktop Pet — 新手使用指南

> 从解压到第一次对话，全流程说明。  
> 面向对象：能解压文件、会编辑文本、大概知道 API Key 是什么的用户。

---

## 目录

1. [前置要求](#一前置要求)
2. [解压与安装](#二解压与安装)
3. [配置 API Key](#三配置-api-key)
4. [设置用户档案与记忆文件](#四设置用户档案与记忆文件)
5. [安装雪菜语音模型（可选）](#五安装雪菜语音模型可选)
6. [首次启动](#六首次启动)
7. [日常使用](#七日常使用)
8. [常见问题](#八常见问题)

---

## 一、前置要求

| 项目 | 要求 |
|------|------|
| 操作系统 | Windows 10 / 11（仅支持 Windows） |
| Python | 3.10 ~ 3.13（**3.14 及以上不支持**，没有 Python 见下方） |
| C++ 运行库 | Microsoft Visual C++ Redistributable 2015-2022 |
| 安装路径 | 必须是**纯英文路径**，不能含中文、空格、括号 |
| 网络 | 需要能访问所选 LLM 服务商的 API |

**C++ 运行库下载**（装过可跳过）：  
https://aka.ms/vs/17/release/vc_redist.x64.exe

**路径示例**：  
- ✅ `C:\Resona\`、`D:\Games\Resona\`  
- ❌ `C:\用户\下载\`、`D:\我的 项目\`、`C:\新建文件夹(1)\`

---

## 二、解压与安装

### 2.1 解压

将下载的压缩包解压到纯英文路径，例如 `C:\Resona\`。

### 2.2 运行安装脚本

找到文件夹中的 **`setup.ps1`**，右键 → **使用 PowerShell 运行**。

> 如果弹出"此系统不允许运行脚本"，请以管理员身份打开 PowerShell，输入：
> ```
> Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
> ```
> 然后再右键运行脚本。

脚本会依次询问以下选项：

**① 是否启用镜像加速**
- 国内网络推荐输入 `Y`（使用 hf-mirror.com 和清华 PyPI 镜像）
- 海外网络输入 `N`

**② 是否使用代理**
- 按实际情况填写

**③ 安装模式**

| 选项 | 说明 | 建议 |
|------|------|------|
| `1` | 直接安装到系统 Python | 不推荐，容易和其他项目冲突 |
| `2` | 在项目目录创建虚拟环境 | ✅ 推荐，最干净 |
| `3` | 下载 Python 3.10 独立运行时 | 没有 Python 或版本不对时选这个 |
| `4` | 仅下载资源，跳过 Python 环境 | 特殊情况 |

**④ 下载组件**

| 组件 | 大小 | 说明 |
|------|------|------|
| SoVITS 推理引擎 | ~7.7 GB | 需要雪菜**语音合成**则选 Y |
| 默认资源包 Resona_Default | ~300 MB | 推荐下载 |
| STT 语音识别模型 | ~3 GB | 需要**语音输入**（对着麦克风说话）则选 Y |
| FFmpeg | ~100 MB | 推荐下载 |

**⑤ 输入 DeepSeek API Key**（可以回车跳过，后面手动填）

安装完成后提示 `Setup Complete!` 即可继续。

---

## 三、配置 API Key

> ⚠️ **必须用 VS Code 或 Notepad++ 打开 `config.cfg`**  
> Windows 自带记事本保存会损坏文件编码，导致启动直接崩溃。

`config.cfg` 在 setup.ps1 运行后会自动生成（从 `config.example.cfg` 复制）。

打开 `config.cfg`，找到 `[General]` 区块，`model_select` 决定用哪个服务商：

| `model_select` | 服务商 | 获取 API Key |
|:-:|---|---|
| 1 | OpenAI (ChatGPT) | https://platform.openai.com |
| **2** | **DeepSeek（推荐，便宜好用）** | https://platform.deepseek.com/api_keys |
| 3 | Claude (Anthropic) | https://console.anthropic.com |
| 4 | Kimi | https://platform.moonshot.cn |
| 5 | Gemini | https://aistudio.google.com |
| 6 | Grok | https://console.x.ai |
| 7 | Qwen（阿里云） | https://dashscope.aliyun.com |
| 9 | 任意 OpenAI 兼容接口 | 填写 base_url 即可 |

选好之后，找到对应区块填入 Key，以 DeepSeek 为例：

```ini
[Model_2_DeepSeek]
api_key = sk-你的key粘贴在这里
```

其余区块的 Key 留空不填也没关系，程序只使用 `model_select` 指定的那个。

---

## 四、设置用户档案与记忆文件

这两个文件告诉雪菜"你是谁"，以及帮她保存跨对话的记忆。

打开 `packs\setsuna\memory\`，里面有两个模板文件：

### USER.txt（用户档案）

1. 将 `USER.sample.txt` 复制一份，重命名为 **`USER.txt`**
2. 用文本编辑器打开，按提示填写你的基本信息（名字、所在城市、兴趣爱好等）
3. 不需要填满，留空的部分雪菜会在聊天中自己记

### MEMORY.txt（长期记忆）

1. 将 `MEMORY.sample.txt` 复制一份，重命名为 **`MEMORY.txt`**
2. 打开后**保留顶部三行注释，删除其余内容**：
   ```
   # 长期记忆
   # 格式：[YYYY-MM-DD] 事件或事实描述
   # 由雪菜在对话中自动维护，请勿手动修改格式
   ```
3. 之后雪菜会自动往里写，你也可以对她说"记住这个：……"让她主动记录

---

## 五、安装雪菜语音模型（可选）

> 只想文字聊天？跳过此步，在 `config.cfg` 中设置 `[SoVITS] enabled = false` 即可。

语音模型文件约 300MB，需单独下载（从群文件或提供的链接获取 `setsuna_voice_models.zip`）。

解压后得到两个文件：

```
setsuna-e15.ckpt        ← GPT 模型
setsuna_e8_s712.pth     ← SoVITS 模型
```

将这两个文件放入以下目录（目录不存在则手动创建）：

```
你的安装目录\
└── packs\
    └── setsuna\
        └── models\
            └── sovits\          ← 放在这里
                ├── setsuna-e15.ckpt
                └── setsuna_e8_s712.pth
```

两个文件缺一不可。

---

## 六、首次启动

启动前检查清单：

- [ ] `config.cfg` 中已填写 API Key
- [ ] `packs\setsuna\memory\` 下已有 `USER.txt` 和 `MEMORY.txt`（不只是 `.sample` 文件）
- [ ] 如需语音，已放好 `.ckpt` 和 `.pth` 两个模型文件

确认后，**双击 `run.bat`**。

命令行窗口会滚动日志。如果启用了 SoVITS，**首次启动需要加载 1～3 分钟**，期间界面可能空白，属正常现象，耐心等待即可。

看到以下内容说明启动成功：
```
[Main] MCP SERVERS METADATA loaded
```

然后点击立绘就可以开始对话了。

---

## 七、日常使用

### 基本操作

| 操作 | 效果 |
|------|------|
| 点击立绘 | 弹出对话框，输入文字发送 |
| `Ctrl+Shift+I` | 开始/停止语音输入（需启用 STT） |
| 右键立绘 | 切换服装、切换角色包、设置 |
| `Ctrl+Alt+0` | 将窗口提到最前端 |

### 记忆系统

| 你说 | 效果 |
|------|------|
| "记住这个：……" | 雪菜主动将信息写入 MEMORY.txt |
| 聊天中提到偏好、习惯 | 雪菜自动更新 USER.txt |
| 让她帮你打开某个软件 | 成功后路径自动写入记忆，下次不用再找 |

### 工具调用（MCP，默认开启）

| 你说 | 雪菜会做 |
|------|---------|
| 帮我打开 QQ | 用 PowerShell 启动 QQ |
| 20 分钟后提醒我喝水 | 设置定时器，到时播报 |
| 帮我查一下今天的 F1 新闻 | 抓取网页后回答 |
| 帮我读一下这个文件 | 读取文件内容并回应 |

> MCP 每次对话会额外消耗 Token。如不需要，在 `config.cfg` 中设置 `[MCP] enabled = false`。

### 启用语音输入（STT）

运行 setup.ps1 时下载了 STT 模型后，在 `config.cfg` 中启用：

```ini
[STT]
enabled = true
hotkey = ctrl+shift+i
```

---

## 八、常见问题

**Q：提示缺少 Visual C++ 运行库**  
→ 下载安装：https://aka.ms/vs/17/release/vc_redist.x64.exe

**Q：PowerShell 提示无法运行脚本**  
→ 以管理员身份打开 PowerShell，输入 `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`，再重新运行

**Q：config.cfg 打开是乱码**  
→ 用 VS Code 或 Notepad++ 打开，不要用系统记事本

**Q：config.cfg 不存在**  
→ 先运行 setup.ps1，脚本会自动从 `config.example.cfg` 生成；或者手动复制一份改名

**Q：启动后界面空白很久**  
→ SoVITS 加载中，等待 1～3 分钟是正常的，不要关闭

**Q：雪菜不说话（有文字但没有声音）**  
→ 检查 `packs\setsuna\models\sovits\` 下是否有 `.ckpt` 和 `.pth` 两个文件

**Q：语音报错"无法启动 GPT-SoVITS"**  
→ 检查 SoVITS 推理引擎是否已通过 setup.ps1 下载，目录 `GPT-SoVITS\` 是否存在

**Q：雪菜记忆没有生效**  
→ 检查 `packs\setsuna\memory\` 下是否存在 `USER.txt` 和 `MEMORY.txt`（而不只是 `.sample` 文件）

**Q：想换成只使用文字，不要语音**  
→ `config.cfg` 中设置 `[SoVITS] enabled = false`

**Q：想换成自己的角色/自制资源包**  
→ 参考 `packs\Example_Pack\` 的目录结构和 `docs\CUSTOM_PACK_GUIDE_FOR_BEGINNERS.md`

**Q：想关闭工具调用（省 Token）**  
→ `config.cfg` 中设置 `[MCP] enabled = false`

---

本文档由 [Claude Code](https://claude.ai/code) 全程协助维护。

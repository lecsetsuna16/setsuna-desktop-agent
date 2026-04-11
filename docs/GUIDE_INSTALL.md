# 下载后安装指南

> 适用于从网盘下载 `Resona_Desktop_Pet_*.zip` 的用户。

---

## 第一步：解压

将压缩包解压到**纯英文路径**，例如：

```
C:\Resona\
D:\Games\Resona\
```

**禁止解压到含中文、空格、括号的路径**，例如 `C:\用户\下载\` 会导致程序崩溃，无法运行。

---

## 第二步：运行安装脚本

找到文件夹里的 `setup.ps1`，**右键 → 使用 PowerShell 运行**。

安装过程中会询问以下选项，按需选择：

| 问题 | 推荐选择 |
|------|---------|
| 是否启用镜像加速（国内网络） | 输入 `Y` |
| 是否需要代理 | 按实际情况 |
| 安装模式选择 | 推荐选 `2`（创建虚拟环境） |
| 是否下载 SoVITS 推理引擎（~7.7GB） | 按需，需要语音功能则 `Y` |
| 是否下载默认资源包 Resona_Default | `Y` |
| 是否下载 STT 语音识别模型（~3GB） | 按需，需要语音输入则 `Y` |
| 是否下载 FFmpeg | `Y` |
| 输入 DeepSeek API Key | 粘贴你的 Key，或回车跳过后手动填 |

安装完成后会提示"Setup Complete!"。

---

## 第三步：配置 API Key

用 **VS Code 或 Notepad++** 打开 `config.cfg`（**不要用系统自带记事本**，会损坏编码导致崩溃）。

找到对应模型区块，填入你的 API Key，例如 DeepSeek：

```ini
[Model_2_DeepSeek]
api_key = sk-你的key填这里
```

`model_select` 字段决定使用哪个服务商：

| 值 | 服务商 |
|---|--------|
| 1 | OpenAI |
| **2** | **DeepSeek（推荐）** |
| 3 | Claude (Anthropic) |
| 4 | Kimi |
| 5 | Gemini |
| 6 | Grok |
| 7 | Qwen（阿里云） |
| 9 | 任意 OpenAI 兼容接口 |

---

## 第四步：启动

双击 `run.bat`，等待约 **50-90 秒**加载完成（启用 SoVITS 时窗口会先空白，属正常现象）。

---

## 常见问题

**Q：提示缺少 Visual C++ 运行库？**  
下载安装：https://aka.ms/vs/17/release/vc_redist.x64.exe

**Q：Python 版本不对？**  
本项目支持 Python 3.10–3.13，3.14 及以上不支持。如无 Python 或版本不对，setup.ps1 选模式 `3` 会自动下载内置运行时（Python 3.10）。

**Q：config.cfg 在哪里？**  
第一次运行 setup.ps1 后会自动从 `config.example.cfg` 复制生成。如果没有，手动复制一份改名即可。

**Q：想用雪菜（Setsuna）角色？**  
还需要额外下载语音模型，请参阅《**雪菜语音模型安装指南**》（`GUIDE_VOICE_MODEL.md`）。

---

本文档由 [Claude Code](https://claude.ai/code) 全程协助维护。

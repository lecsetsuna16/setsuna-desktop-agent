# 雪菜语音模型安装指南

> 适用于想使用**小木曾雪菜（Setsuna）** 角色语音的用户。
> 语音模型文件较大（约 300MB），需单独下载后手动放置。

---

## 你需要下载的文件

从群文件或网盘获取 `setsuna_voice_models.zip`，解压后包含两个文件：

```
setsuna-e15.ckpt          ← GPT 模型权重
setsuna_e8_s712.pth       ← SoVITS 模型权重
```

这两个文件**必须同时存在**，缺一不可。

---

## 放置位置

将两个文件放入以下目录（如目录不存在，请手动创建）：

```
你的Resona安装目录\
└── packs\
    └── setsuna\
        └── models\
            └── sovits\          ← 放在这里
                ├── setsuna-e15.ckpt
                └── setsuna_e8_s712.pth
```

**完整示例路径：**
```
C:\Resona\packs\setsuna\models\sovits\setsuna-e15.ckpt
C:\Resona\packs\setsuna\models\sovits\setsuna_e8_s712.pth
```

---

## 切换到雪菜角色

打开 `config.cfg`，找到 `[General]` 区块，修改以下三行：

```ini
[General]
active_pack    = setsuna
charactername  = Ogiso Setsuna
default_outfit = setsuna_outfit_00
```

确保 SoVITS 已启用（`[SoVITS]` 区块中 `enabled = true`）。

---

## 验证是否成功

启动 `run.bat` 后，查看日志窗口（命令行黑框）。

- 看到类似 `[SoVITS] Model loaded` 或 SoVITS 服务正常启动 → 成功
- 看到 `model file not found` 或语音合成报错 → 检查文件路径是否正确

---

## 注意事项

- 文件夹名称和文件名**区分大小写**，请勿重命名
- 语音模型仅供个人学习与技术交流使用，请勿二次分发或用于商业用途
- 如需使用 GPT-SoVITS 自行训练模型，替换这两个文件即可，其他配置无需改动

---

本文档由 [Claude Code](https://claude.ai/code) 全程协助维护。

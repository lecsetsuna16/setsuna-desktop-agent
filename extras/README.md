# 可选扩展

默认不加载的 MCP 工具，需要时解压启用。

## optional_mcp.zip

| 文件 | 用途 | 额外要求 |
|---|---|---|
| `slay_the_spire_mcp.mcp.py` | 杀戮尖塔游戏联动（读局面、出牌、subagent 自动打牌） | 游戏 Mod + `[ExternalAPI] enabled = true` |
| `minecraft_mcp.mcp.py` | Minecraft 游戏联动 | 游戏 Mod + `[ExternalAPI] enabled = true` |
| `ocr_tools.mcp.py` | 截屏 OCR（百度 / 腾讯云） | `config.cfg` 的 `[OCR]` 填好密钥；目前启动会失败，需排查 |

### 启用

把 zip **解压到项目根目录**（压缩包内已带 `mcpserver/` 路径），重启桌宠即可。只想要其中一个就只解压那一个文件。

### 停用

删除 `mcpserver/` 下对应的 `.mcp.py` 文件，重启。

### 注意

- 游戏 MCP 的路由关键词较宽泛（「服务器」「玩家」「地图」「战斗」等），启用后普通聊天也可能被路由到 reasoner 模型。
- `llm_backend.py` 中的 subagent 逻辑与 `config.cfg` 的 `hide_public_prefixes = sts_` 是为杀戮尖塔保留的，未启用时不生效。

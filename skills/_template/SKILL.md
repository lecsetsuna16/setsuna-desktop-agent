---
name: skill-name
description: >
  [必填] 清晰描述这个 Skill 的功能和触发场景。
  这是 Resona 和 OpenClaw 两套系统共同依赖的核心字段。
  写清楚"什么情况下应该用这个 Skill"，例如：
  "当用户要求生成每日新闻摘要、问今天有什么大事、或请求日报时使用。"
x-resona-triggers:
  - "触发词示例"
  - "另一个触发词"
# x-resona-triggers 是 Resona 专有扩展字段，供快速 regex 路由使用。
# OpenClaw 会忽略此字段，不影响跨平台兼容性。
# 如果不填，Resona 将回退到让 LLM 根据 description 进行语义匹配。
---

# Skill Name（技能名称）

## Overview

[1-2 句话说明这个 Skill 能做什么]

## Workflow

[分步骤描述执行流程，例如：]

1. 步骤一：...
2. 步骤二：...
3. 步骤三：...

## Notes

- [注意事项]
- [已知限制]

---

<!-- Resona 扩展说明（可删除）
scripts/   → 放 Python 脚本（Windows 原生支持）；Bash 脚本需要 WSL，建议用 Python 替代
references/ → 放补充文档，Resona 在需要时按需注入到 context
assets/    → 放模板文件、图片等，LLM 通过路径引用
-->

"""
SkillManager — Resona Desktop Pet Skill 系统

兼容 OpenClaw AgentSkills 生态（https://github.com/openclawai/openclaw）。

Skill 格式规范：
  skill-name/
  ├── SKILL.md          必需。YAML frontmatter(name, description) + Markdown 指令体
  ├── scripts/          可选。Python 脚本（Windows 直接运行；Bash 需 WSL）
  ├── references/       可选。补充文档，按需注入 context
  └── assets/           可选。模板/图片等，LLM 通过路径引用

Resona 扩展字段（不影响 OpenClaw 兼容性，OpenClaw 会忽略）：
  x-resona-triggers: ["触发词1", "触发词2"]   # 快速 regex 路由，可选

激活逻辑：
  1. 快速路由：用户消息命中 x-resona-triggers → 直接激活
  2. 语义路由（TODO）：把所有 description 传给 LLM，由 LLM 判断 → 适合复杂意图

当前状态：接口预留，TODO 标注的方法尚未实现，不影响桌宠现有功能。
"""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# ── 路径常量 ──────────────────────────────────────────────────────────────────
SKILLS_DIR = Path(__file__).resolve().parents[2] / "skills"


# ── 数据结构 ──────────────────────────────────────────────────────────────────
@dataclass
class SkillManifest:
    """解析后的单个 Skill 元数据。"""
    name: str
    description: str
    triggers: list[str]          # x-resona-triggers，空列表表示未设置
    model_hint: str              # x-resona-model: "reasoner" | "chat" | ""（空=跟随路由默认）
    instructions: str            # SKILL.md body（frontmatter 以下部分）
    skill_dir: Path

    # 懒加载缓存
    _references_cache: dict[str, str] = field(default_factory=dict, repr=False)

    def load_reference(self, filename: str) -> Optional[str]:
        """
        按需加载 references/ 下的文档，注入 context 时使用。
        TODO: 实现文件读取与缓存
        """
        if filename in self._references_cache:
            return self._references_cache[filename]
        ref_path = self.skill_dir / "references" / filename
        if ref_path.exists():
            content = ref_path.read_text(encoding="utf-8")
            self._references_cache[filename] = content
            return content
        return None

    def list_scripts(self) -> list[Path]:
        """列出 scripts/ 目录下所有可执行文件。"""
        scripts_dir = self.skill_dir / "scripts"
        if scripts_dir.exists():
            return list(scripts_dir.iterdir())
        return []

    def list_assets(self) -> list[Path]:
        """列出 assets/ 目录下所有资产文件。"""
        assets_dir = self.skill_dir / "assets"
        if assets_dir.exists():
            return list(assets_dir.iterdir())
        return []


# ── 解析工具 ──────────────────────────────────────────────────────────────────
def _parse_skill_md(skill_dir: Path) -> Optional[SkillManifest]:
    """
    解析 SKILL.md，提取 frontmatter 和 body。
    兼容 OpenClaw 规范：只要求 name + description 字段。
    """
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return None

    try:
        raw = skill_md.read_text(encoding="utf-8")
    except Exception:
        return None

    # 提取 YAML frontmatter（--- 之间的部分）
    fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)", raw, re.DOTALL)
    if not fm_match:
        return None

    fm_text, body = fm_match.group(1), fm_match.group(2).strip()

    # 简单 key-value 解析（避免引入 pyyaml 依赖）
    name = _extract_yaml_scalar(fm_text, "name")
    description = _extract_yaml_scalar(fm_text, "description")
    triggers = _extract_yaml_list(fm_text, "x-resona-triggers")
    model_hint = _extract_yaml_scalar(fm_text, "x-resona-model").lower()  # "reasoner" | "chat" | ""

    if not name or not description:
        return None

    return SkillManifest(
        name=name,
        description=description,
        triggers=triggers,
        model_hint=model_hint,
        instructions=body,
        skill_dir=skill_dir,
    )


def _extract_yaml_scalar(fm_text: str, key: str) -> str:
    """从 frontmatter 文本中提取单值字段（支持 > 折叠块）。"""
    # 普通单行: key: value
    m = re.search(rf"^{re.escape(key)}:\s*(.+)$", fm_text, re.MULTILINE)
    if m:
        return m.group(1).strip().strip('"').strip("'")
    # 折叠块: key: >\n  line1\n  line2
    m = re.search(rf"^{re.escape(key)}:\s*>\s*\n((?:[ \t]+.+\n?)+)", fm_text, re.MULTILINE)
    if m:
        lines = [l.strip() for l in m.group(1).splitlines()]
        return " ".join(lines).strip()
    return ""


def _extract_yaml_list(fm_text: str, key: str) -> list[str]:
    """从 frontmatter 文本中提取列表字段（- item 格式）。"""
    m = re.search(rf"^{re.escape(key)}:\s*\n((?:[ \t]+-[ \t]+.+\n?)+)", fm_text, re.MULTILINE)
    if not m:
        return []
    items = []
    for line in m.group(1).splitlines():
        item_match = re.match(r"[ \t]+-[ \t]+(.+)", line)
        if item_match:
            items.append(item_match.group(1).strip().strip('"').strip("'"))
    return items


# ── 核心管理器 ────────────────────────────────────────────────────────────────
class SkillManager:
    """
    Skill 生命周期管理：加载、匹配、上下文生成。

    用法（在 llm_backend.py 中）：
        from .skill_manager import skill_manager

        # 启动时（config skills_enabled = true）：
        skill_manager.load_all()

        # 每次对话前：
        matched = skill_manager.match(user_message)
        system_prompt += skill_manager.build_context_patch(matched)
    """

    def __init__(self) -> None:
        self._skills: list[SkillManifest] = []
        self._loaded: bool = False

    # ── 初始化 ────────────────────────────────────────────────────────────────
    def load_all(self, skills_dir: Path = SKILLS_DIR) -> int:
        """
        扫描 skills/ 目录，加载所有合法 Skill。
        跳过以 _ 开头的目录（模板/私有）。
        返回成功加载的数量。
        """
        self._skills.clear()
        if not skills_dir.exists():
            self._loaded = True
            return 0

        loaded = 0
        for skill_dir in sorted(skills_dir.iterdir()):
            if not skill_dir.is_dir():
                continue
            if skill_dir.name.startswith("_"):
                continue  # 跳过 _template 等保留目录
            manifest = _parse_skill_md(skill_dir)
            if manifest:
                self._skills.append(manifest)
                loaded += 1

        self._loaded = True
        return loaded

    # ── 安装 .skill 包 ────────────────────────────────────────────────────────
    def install(self, skill_file: Path, skills_dir: Path = SKILLS_DIR) -> bool:
        """
        安装 .skill 文件（OpenClaw 打包格式，本质是 zip）。
        包含 Zip Slip 防护：拒绝任何试图写到 skills_dir 外部的路径。
        TODO: 实现内容校验（检查 SKILL.md 存在、frontmatter 合法）
        """
        if not skill_file.exists() or skill_file.suffix != ".skill":
            return False
        try:
            resolved_target = skills_dir.resolve()
            with zipfile.ZipFile(skill_file, "r") as zf:
                for member in zf.namelist():
                    member_path = (skills_dir / member).resolve()
                    if not str(member_path).startswith(str(resolved_target)):
                        # Zip Slip 攻击：路径逃逸出 skills/ 目录，拒绝安装
                        return False
                zf.extractall(skills_dir)
            return True
        except Exception:
            return False

    # ── 匹配 ──────────────────────────────────────────────────────────────────
    def match(self, user_message: str) -> list[SkillManifest]:
        """
        根据用户消息返回命中的 Skill 列表。

        策略：
          1. 快速路由：检查 x-resona-triggers（regex 包含匹配）
          2. 语义路由：TODO，当前直接返回触发词命中结果
        """
        if not self._loaded or not self._skills:
            return []

        matched = []
        for skill in self._skills:
            if self._match_triggers(user_message, skill):
                matched.append(skill)

        # TODO: 如果 matched 为空，调用轻量 LLM 做语义匹配
        # matched = await self._semantic_match(user_message)

        return matched

    def _match_triggers(self, message: str, skill: SkillManifest) -> bool:
        """检查消息是否命中 x-resona-triggers 中的任意触发词。"""
        if not skill.triggers:
            return False  # 没有触发词时，不走快速路由（等待语义路由实现）
        return any(trigger in message for trigger in skill.triggers)

    # ── 上下文生成 ────────────────────────────────────────────────────────────
    def build_context_patch(self, skills: list[SkillManifest]) -> str:
        """
        将命中的 Skill instructions 拼合为 system prompt 追加段。
        TODO: 实现 references/ 按需懒加载逻辑
        """
        if not skills:
            return ""

        parts = ["\n\n## 当前已激活的 Skills\n"]
        for skill in skills:
            parts.append(f"\n### [{skill.name}]\n")
            parts.append(skill.instructions)
            parts.append("\n")

        return "".join(parts)

    def requires_reasoner(self, skills: list[SkillManifest]) -> bool:
        """任意命中的 skill 声明 x-resona-model: reasoner 时返回 True。
        路由决策：只要有一个 skill 要求 reasoner，整个请求走 reasoner。"""
        return any(s.model_hint == "reasoner" for s in skills)

    def get_required_tools(self, skills: list[SkillManifest]) -> list[str]:
        """
        TODO: 返回这批 Skill 依赖的 MCP tool 名称列表，用于启动前校验。
        当前 OpenClaw SKILL.md 不声明 tool 依赖，需通过 Resona 扩展字段实现。
        """
        return []

    # ── 查询 ──────────────────────────────────────────────────────────────────
    @property
    def all_skills(self) -> list[SkillManifest]:
        return list(self._skills)

    @property
    def skill_count(self) -> int:
        return len(self._skills)

    def get_descriptions_for_llm(self) -> str:
        """
        返回所有 Skill 的 name + description 摘要，供语义路由时传给 LLM。
        TODO: 在语义匹配流程中调用
        """
        if not self._skills:
            return ""
        lines = ["可用 Skills："]
        for skill in self._skills:
            lines.append(f"- {skill.name}: {skill.description[:120]}")
        return "\n".join(lines)


# ── 全局单例 ──────────────────────────────────────────────────────────────────
skill_manager = SkillManager()

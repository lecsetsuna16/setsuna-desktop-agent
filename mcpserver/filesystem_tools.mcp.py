import os
import glob
from pathlib import Path
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("FilesystemTools")

# ── 路由关键词（动态注入路由正则，新增MCP时照此格式填写）──────────────────────
ROUTING_KEYWORDS = [
    "读取文件", "写入文件", "查看文件", "列出目录", "列出文件",
    "保存文件", "新建文件", "删除文件", "复制文件", "移动文件",
    "查看目录", "读取", "写入", "保存",
    "记住", "记住这个", "帮我记", "记下来", "记录一下",
]

# === 安全配置区 ===
# 1. 沙箱根目录 (严格限制所有读写必须在此范围内)
SANDBOX_ROOT = Path(__file__).resolve().parents[1]

# 2. 允许写入/修改的文件后缀名白名单
ALLOWED_EXTENSIONS = {".txt", ".py", ".json", ".md", ".csv", ".log", ".cfg"}

# 3. 最大文件读取大小 (MB)
MAX_FILE_SIZE_MB = 10

def _safe_path(path: str) -> Path:
    """解析路径并校验是否在沙箱范围内 (防路径穿越)
    相对路径以 SANDBOX_ROOT（项目根目录）为基准解析，而非 MCP 进程的 CWD。
    """
    p = Path(path)
    if not p.is_absolute():
        p = SANDBOX_ROOT / p
    resolved = p.resolve()
    if not resolved.is_relative_to(SANDBOX_ROOT):
        raise ValueError(f"Access denied: {path} is outside the secure sandbox.")
    return resolved

def _check_extension(path: Path):
    """校验文件后缀是否在白名单内"""
    if path.suffix.lower() not in ALLOWED_EXTENSIONS:
        raise ValueError(f"File type modification not allowed: {path.suffix}")

# 4. 写保护文件集合 (绝对禁止通过 filesystem_tools 写入或修改)
WRITE_PROTECTED = {
    "SOUL.txt",           # 角色核心人格，禁止 LLM 工具写入
    "auto_keywords.json", # 由后端自动维护，禁止 LLM 工具写入
    "triggers.json",      # 触发词配置，禁止 LLM 工具写入
    "emotions.json",      # 情绪映射配置，禁止 LLM 工具写入
}

# 5. 读保护文件集合 (包含敏感凭据，禁止模型读取)
READ_PROTECTED = {"config.cfg", "config.ini", ".env", "secrets.json"}

# 6. 读保护目录集合 (目录下所有文件均禁止通过工具读取，防 prompt injection 外泄记忆/用户数据)
READ_PROTECTED_DIRS = {"memory"}

def _check_writable(path: Path):
    """校验文件是否受写保护 (防 prompt 注入篡改核心文件)"""
    if path.name in WRITE_PROTECTED:
        raise ValueError(
            f"Write protected: '{path.name}' is a read-only core file and cannot be modified."
        )

def _check_readable(path: Path):
    """校验文件是否受读保护 (防止 API Key 等敏感凭据通过 LLM 泄露)"""
    if path.name in READ_PROTECTED:
        raise ValueError(
            f"Read protected: '{path.name}' contains sensitive credentials and cannot be read via tools."
        )
    # 检查是否位于受保护目录内（如 memory/）
    if any(part in READ_PROTECTED_DIRS for part in path.parts):
        raise ValueError(
            f"无需读取：'{path.name}' 的内容已在对话开始时由系统自动注入到你的上下文中。"
            f"请直接使用你已有的记忆信息，不要尝试通过工具重复读取。"
        )
# ==================

@mcp.tool()
def list_directory(path: str) -> list[str]:
    """List all files and subdirectories in the specified path."""
    try:
        target = _safe_path(path)
        if not target.exists(): return [f"Error: Path not found: {path}"]
        if not target.is_dir(): return [f"Error: Path is not a directory: {path}"]
        return [p.name for p in target.iterdir()]
    except Exception as e:
        return [f"Error: {e}"]

@mcp.tool()
def read_file(path: str, start_line: int = 1, end_line: int = -1) -> str:
    """Read the content of a file. Supports reading specific line ranges."""
    try:
        target = _safe_path(path)
        _check_readable(target)  # 安全拦截：读保护敏感配置文件
        if not target.exists(): return f"Error: File not found: {path}"
        if not target.is_file(): return f"Error: Path is not a file: {path}"

        # 安全拦截：防止读取超大文件撑爆内存
        if target.stat().st_size > MAX_FILE_SIZE_MB * 1024 * 1024:
            return f"Error: File too large (> {MAX_FILE_SIZE_MB}MB)"
            
        with target.open("r", encoding="utf-8") as f:
            lines = f.readlines()
        total = len(lines)
        if start_line < 1: start_line = 1
        if end_line == -1 or end_line > total: end_line = total
        if start_line > total: return ""
        return "".join(lines[start_line - 1:end_line])
    except Exception as e:
        return f"Error: {e}"

@mcp.tool()
def count_lines(path: str) -> int:
    """Get the total number of lines in a file."""
    try:
        target = _safe_path(path)
        _check_readable(target)
        if not target.exists() or not target.is_file(): return -1
        with target.open("r", encoding="utf-8") as f:
            return sum(1 for _ in f)
    except Exception:
        return -1

@mcp.tool()
def search_files(directory: str, pattern: str) -> list[str]:
    """Search for files in a directory using a glob pattern (e.g., '*.txt')."""
    try:
        base = _safe_path(directory)
        if not base.exists() or not base.is_dir():
            return [f"Error: Directory not found: {directory}"]
        search_path = str(base / pattern)
        return glob.glob(search_path, recursive=True)
    except Exception as e:
        return [f"Error: {e}"]

@mcp.tool()
def edit_lines(path: str, start_line: int, end_line: int, new_content: str) -> str:
    """Replace a range of lines in a file with new content."""
    try:
        target = _safe_path(path)
        _check_extension(target) # 安全拦截：校验后缀
        _check_writable(target)  # 安全拦截：写保护核心文件

        if not target.exists(): return f"Error: File not found: {path}"
        if not target.is_file(): return f"Error: Path is not a file: {path}"
        with target.open("r", encoding="utf-8") as f:
            lines = f.readlines()
        total = len(lines)
        if start_line < 1 or end_line < start_line: return "Error: Invalid line range."
        if start_line > total: return f"Error: Start line out of range: {start_line}"
        if end_line > total: end_line = total
        
        replacement = new_content.splitlines(keepends=True)
        if new_content and not new_content.endswith("\n"): replacement.append("\n")
        lines[start_line - 1:end_line] = replacement
        with target.open("w", encoding="utf-8") as f:
            f.writelines(lines)
        return f"OK: Edited lines {start_line}-{end_line} in {path}"
    except Exception as e:
        return f"Error: {e}"

@mcp.tool()
def write_file(path: str, content: str) -> str:
    """Write content to a file. Overwrites if exists, creates if not."""
    try:
        target = _safe_path(path)
        _check_extension(target) # 安全拦截：校验后缀
        _check_writable(target)  # 安全拦截：写保护核心文件

        if target.parent and not target.parent.exists():
            return f"Error: Parent directory does not exist: {target.parent}"
        with target.open("w", encoding="utf-8") as f:
            f.write(content)
        return f"OK: Wrote file {path}"
    except Exception as e:
        return f"Error: {e}"

if __name__ == "__main__":
    mcp.run()
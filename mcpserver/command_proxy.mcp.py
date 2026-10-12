import configparser
import subprocess
import sys
from pathlib import Path
from mcp.server.fastmcp import FastMCP

_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config.cfg"

def _shell_confirm_enabled() -> bool:
    """Read shell_confirm from config.cfg each call for hot-reload support."""
    try:
        cfg = configparser.RawConfigParser()
        cfg.read(str(_CONFIG_PATH), encoding="utf-8")
        return cfg.getboolean("MCP", "shell_confirm", fallback=True)
    except Exception:
        return True  # fail-safe: default to requiring confirmation

mcp = FastMCP("CommandProxy")

# ── 路由关键词（动态注入路由正则，新增MCP时照此格式填写）──────────────────────
ROUTING_KEYWORDS = [
    "打开软件", "启动程序", "运行", "执行命令",
    "打开浏览器", "打开文件", "打开文件夹",
]

# === 安全配置区 ===
# 1. 危险命令黑名单 (防破坏与恶意下载)
BLOCKED_KEYWORDS = [
    "rm ", "del ", "format", "shutdown", "taskkill",
    "reg delete", "net user", "mklink", "cipher",
    "curl", "wget", "invoke-webrequest", "iex",
    "remove-item", "rd ", "rmdir", "erase ",
    # PowerShell 内置别名（防别名绕过黑名单）
    " ri ", " ri\t", "'ri ", "\"ri ",   # ri = Remove-Item
    " del\t",                            # del 无空格变体
    "copy-item", " copy ", " cp ",       # 防文件复制外泄
    "move-item", " move ", " mv ",       # 防文件移动外泄
    "set-content", "add-content",        # 防写入任意路径
    "out-file",                          # 重定向写文件
    # 防绕过：Base64 编码执行 & Invoke-Expression 全称
    "invoke-expression", "-encodedcommand", "-enc ",
    "frombase64string", "::frombase64",
    # .NET 文件写入方法（绕过 filesystem_tools 保护）
    "[system.io.file]",          # System.IO.File 静态类
    "::writealltext",            # File::WriteAllText
    "::appendalltext",           # File::AppendAllText
    "::writeallines",            # File::WriteAllLines
    "::writeallbytes",           # File::WriteAllBytes
    "streamwriter",              # new StreamWriter(path)
    # LOL 二进制下载手法
    "start-bitstransfer",       # BITS 后台下载
    "bitsadmin",                # BITS 命令行工具
    "certutil",                 # 证书工具，常被滥用下载文件
    "net.webclient",            # .NET 下载对象
    "downloadfile", "downloadstring",  # WebClient 方法
    "mshta",                    # 执行 HTA 脚本
    "wscript", "cscript",       # 执行 VBS/JS 脚本
    "regsvr32",                 # 注册/执行 DLL
    "rundll32",                 # 调用 DLL 函数（可执行任意代码）
    "appsync",                  # AppLocker 绕过
]

# 2. 允许的工作目录白名单 (限制执行范围)
# 这里动态获取桌宠项目的根目录作为唯一的合法执行目录
PROJECT_ROOT = Path(__file__).resolve().parents[1]
ALLOWED_CWD_ROOTS = [PROJECT_ROOT]

def _is_command_safe(command: str) -> bool:
    """检查命令是否包含高危关键字"""
    cmd_lower = command.lower()
    return not any(kw in cmd_lower for kw in BLOCKED_KEYWORDS)

def _is_cwd_allowed(cwd: str) -> bool:
    """检查工作目录是否在白名单内"""
    if not cwd:
        return True # 允许不指定 cwd（将使用默认当前路径）
    target = Path(cwd).resolve()
    return any(target == root or root in target.parents for root in ALLOWED_CWD_ROOTS)

def _require_user_confirmation(command: str) -> bool:
    """Keep explicit confirmation available in Python's Windows embeddable build."""
    try:
        msg = f"雪菜 (MCP) 请求执行系统命令：\n\n【 {command} 】\n\n是否允许？"
        if sys.platform == "win32":
            import ctypes
            # Yes/No, question icon, default No, foreground and topmost.
            flags = 0x00000004 | 0x00000020 | 0x00000100 | 0x00010000 | 0x00040000
            return ctypes.windll.user32.MessageBoxW(None, msg, "雪菜 · 命令执行确认", flags) == 6
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        try:
            root.withdraw()
            root.attributes("-topmost", True)
            return messagebox.askyesno("安全确认", msg, parent=root, default="no")
        finally:
            root.destroy()
    except Exception:
        return False
# ==================

def _run_cmd(command: str, timeout: int, cwd: str) -> str:
    completed = subprocess.run(
        ["cmd", "/c", f"chcp 65001 >nul & {command}"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, cwd=cwd or None
    )
    return _format_result(completed.returncode, completed.stdout, completed.stderr)

def _run_powershell(command: str, timeout: int, cwd: str) -> str:
    utf8_init = "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; $OutputEncoding = [System.Text.Encoding]::UTF8; "
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-Command", utf8_init + command],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, cwd=cwd or None
    )
    return _format_result(completed.returncode, completed.stdout, completed.stderr)

def _format_result(code: int, stdout: str, stderr: str) -> str:
    parts = [f"exit_code={code}"]
    if stdout: parts.extend(["stdout:", stdout])
    if stderr: parts.extend(["stderr:", stderr])
    return "\n".join(parts).strip()

@mcp.tool()
def exec_shell(raw: str, timeout: int = 30, cwd: str = "") -> str:
    """Execute a shell command. Usage: 'cmd <command>' or 'powershell <command>'."""
    try:
        if not raw: return "Error: Empty command"
        parts = raw.strip().split(" ", 1)
        if len(parts) < 2: return "Error: Use format 'cmd <command>' or 'powershell <command>'"
        mode, command = parts[0].lower(), parts[1]
        
        # 1. 校验命令黑名单
        if not _is_command_safe(command):
            return "Error: Security Block. 命令包含被禁止的高危关键字。"
            
        # 2. 校验 cwd 工作目录白名单
        if cwd and not _is_cwd_allowed(cwd):
            return "Error: Security Block. 不允许在指定的 cwd 路径下执行命令。"
            
        # 3. 人工确认（可通过 config.cfg [MCP] shell_confirm = false 关闭，热加载生效）
        if _shell_confirm_enabled():
            if not _require_user_confirmation(command):
                return "Error: Permission Denied by User. The user has explicitly rejected this action. You MUST stop immediately — do NOT retry, rephrase, or attempt any alternative method to accomplish the same goal. Inform the user that the action was cancelled."

        if mode == "cmd": return _run_cmd(command, timeout, cwd)
        if mode == "powershell": return _run_powershell(command, timeout, cwd)
        return "Error: Mode must be 'cmd' or 'powershell'"
    except subprocess.TimeoutExpired:
        return f"Error: Command timed out after {timeout}s"
    except Exception as e:
        return f"Error: {e}"

if __name__ == "__main__":
    mcp.run()
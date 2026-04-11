import json
import random
import sys
import time as time_module
from pathlib import Path
from mcp.server.fastmcp import FastMCP

root_dir = Path(__file__).resolve().parents[1]
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

# ── 路由关键词（动态注入路由正则，新增MCP时照此格式填写）──────────────────────
ROUTING_KEYWORDS = [
    "提醒我", "定时", "闹钟", "倒计时",
    "分钟后提醒", "小时后提醒", "秒后提醒",
]

from resona_desktop_pet.config.config_manager import ConfigManager

mcp = FastMCP("TimerInbox")

def _resolve_inbox_path() -> Path:
    root = root_dir
    config_path = root / "config.cfg"
    inbox_path = root / "TEMP" / "timer_inbox.json"
    try:
        cfg = ConfigManager(str(config_path))
        cfg_path = Path(cfg.timer_inbox_file)
        if not cfg_path.is_absolute():
            cfg_path = root / cfg_path
        inbox_path = cfg_path
    except Exception:
        pass
    return inbox_path

def _load_items(path: Path) -> list:
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
    except Exception:
        return []
    return []

def _write_items(path: Path, items: list) -> bool:
    try:
        if path.parent and not path.parent.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False

@mcp.tool()
def schedule_timer_event(emotion: str = "<E:smile>", text_display: str = "", text_tts: str = "", time: float = 0.0) -> dict:
    """LLM Instruction: Use this tool ONLY when you need to schedule a future event or reminder.
    
    This tool writes a task to the inbox, which the main program polls and triggers after the specified delay.
    
    Args:
        emotion: The emotion tag. MUST be chosen from the allowed list in your system prompt (e.g., <E:smile>, <E:serious>, etc.).
        text_display: The text to display on the UI when triggered. MUST be in the user's current language.
        text_tts: The text for speech synthesis. MUST be in the character's spoken language (e.g., Japanese) and consistent with the persona.
        time: The delay in seconds from now (relative time) before the event triggers.
    """
    now = time_module.time()
    try:
        delay = float(time)
    except (TypeError, ValueError):
        return {"ok": False, "error": "Invalid time value. 'time' must be a positive number (seconds from now)."}
    if delay <= 0:
        return {"ok": False, "error": f"Invalid time value: {delay}. Timer delay must be at least 1 second. Please ask the user for a valid future time."}
    entry = {
        "id": f"timer_{int(now * 1000)}_{random.randint(1000, 9999)}",
        "created_at": now,
        "time": delay,
        "due_at": now + delay,
        "emotion": emotion,
        "text_display": text_display,
        "text_tts": text_tts
    }
    path = _resolve_inbox_path()
    items = _load_items(path)
    items.append(entry)
    ok = _write_items(path, items)
    return {
        "ok": ok,
        "task_id": entry["id"],
        "due_at": entry["due_at"],
        "inbox_path": str(path)
    }

if __name__ == "__main__":
    mcp.run()

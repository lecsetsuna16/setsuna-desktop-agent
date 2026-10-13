"""
music_sense.mcp.py — Windows 音乐感知 MCP
读取/控制 Windows 系统媒体会话（Spotify / 网易云 / QQ音乐 / 浏览器等均适用）
依赖: pip install winrt-runtime winrt-Windows.Foundation winrt-Windows.Media.Control
     （旧环境里的 winsdk 仍可作为回退，但它只支持到 Python 3.12）
"""
import asyncio
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("MusicSense")

# ── 路由关键词（动态注入路由正则，新增MCP时照此格式填写）──────────────────────
ROUTING_KEYWORDS = [
    "在听什么", "听什么歌", "播放什么", "现在听", "放什么歌",
    "暂停音乐", "继续播放", "下一首", "上一首", "换首歌", "切歌", "停止播放",
    "换一首", "换歌", "切一首", "切换歌曲", "跳过", "悲伤的歌", "开心的歌",
    "音乐控制", "歌曲信息", "播放音乐", "放歌",
]

# ── 安全白名单：仅允许媒体控制操作 ──────────────────────────────────────────
_ALLOWED_ACTIONS = {"pause", "play", "toggle", "next", "previous"}


def _media_control():
    """winrt supports Python 3.9-3.14; winsdk is abandoned after 3.12 but kept as a fallback."""
    try:
        import winrt.windows.foundation  # noqa: F401  (makes WinRT async operations awaitable)
        import winrt.windows.media.control as control
    except ImportError:
        import winsdk.windows.media.control as control
    return control


async def _get_session():
    """获取当前活跃媒体会话，失败返回 None。"""
    try:
        Manager = _media_control().GlobalSystemMediaTransportControlsSessionManager
        manager = await Manager.request_async()
        return manager.get_current_session()
    except Exception:
        return None


@mcp.tool()
async def get_now_playing() -> dict:
    """
    Get information about the currently playing music on this Windows PC.
    Works with Spotify, 网易云音乐, QQ音乐, and browser-based players (YouTube, Bilibili, etc.).
    Returns track title, artist, album, source app, and play state.
    Use this when the user or conversation context suggests music/audio awareness.
    """
    session = await _get_session()
    if session is None:
        return {"is_playing": False, "reason": "No active media session found"}

    try:
        PlaybackStatus = _media_control().GlobalSystemMediaTransportControlsSessionPlaybackStatus

        media_props = await session.try_get_media_properties_async()
        playback_info = session.get_playback_info()

        is_playing = (
            playback_info.playback_status == PlaybackStatus.PLAYING
        )

        # 清理 app 标识符（去掉路径、包名后缀等）
        raw_app = session.source_app_user_model_id or ""
        app_name = raw_app.split("!")[-1].replace(".exe", "")

        if not is_playing:
            return {
                "is_playing": False,
                "app": app_name,
                "last_title": media_props.title or "",
                "last_artist": media_props.artist or "",
            }

        return {
            "is_playing": True,
            "title": media_props.title or "",
            "artist": media_props.artist or "",
            "album": media_props.album_title or "",
            "app": app_name,
        }

    except Exception as e:
        return {"is_playing": False, "reason": f"Read error: {e}"}


@mcp.tool()
async def control_playback(action: str) -> dict:
    """
    Control music playback on the user's PC.
    Allowed actions: "pause", "play", "toggle" (pause/resume), "next" (next track), "previous" (previous track).
    Only use when the user explicitly requests a playback change.
    """
    action = action.strip().lower()

    if action not in _ALLOWED_ACTIONS:
        return {
            "success": False,
            "error": f"Unknown action '{action}'. Allowed: {sorted(_ALLOWED_ACTIONS)}",
        }

    session = await _get_session()
    if session is None:
        return {"success": False, "error": "No active media session found"}

    try:
        if action == "pause":
            await session.try_pause_async()
        elif action == "play":
            await session.try_play_async()
        elif action == "toggle":
            await session.try_toggle_play_pause_async()
        elif action == "next":
            await session.try_skip_next_async()
        elif action == "previous":
            await session.try_skip_previous_async()

        return {"success": True, "action": action}

    except Exception as e:
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    mcp.run(transport="stdio")

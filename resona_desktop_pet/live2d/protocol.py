"""Small, versioned command contract. No raw Cubism parameter writes from tools."""
import math

EXPRESSIONS = ("neutral", "smile", "serious", "angry", "sad", "thinking",
               "surprised", "dislike", "smirk", "embarrassed", "shy", "worry", "smile_closed", "cry")
MOTIONS = ("none", "nod", "shake", "blink")
LOOKS = ("center", "left", "right", "up", "down")


def validate_perform(arguments):
    if not isinstance(arguments, dict):
        raise ValueError("arguments must be an object")
    allowed = {"expression", "motion", "look", "intensity", "hold_ms", "pack_id"}
    extra = set(arguments) - allowed
    if extra:
        raise ValueError("Unknown arguments: " + ", ".join(sorted(extra)))
    result = {}
    for name, choices, default in (("expression", EXPRESSIONS, "neutral"),
                                    ("motion", MOTIONS, "none"),
                                    ("look", LOOKS, "center")):
        value = arguments.get(name, default)
        if value not in choices:
            raise ValueError(f"{name} must be one of {choices}")
        result[name] = value
    intensity = arguments.get("intensity", 0.6)
    if isinstance(intensity, bool) or not isinstance(intensity, (float, int)) or not math.isfinite(intensity) or not 0 <= intensity <= 1:
        raise ValueError("intensity must be a finite number in [0, 1]")
    duration = arguments.get("hold_ms", 1800)
    if isinstance(duration, bool) or not isinstance(duration, int) or not 300 <= duration <= 8000:
        raise ValueError("hold_ms must be an integer in [300, 8000]")
    result.update(intensity=float(intensity), hold_ms=duration)
    return result


def validate_sing(arguments):
    if not isinstance(arguments, dict) or set(arguments) - {"command", "duration_seconds", "pack_id"}:
        raise ValueError("Invalid singing arguments")
    command = arguments.get("command", "start")
    if command not in ("start", "stop"):
        raise ValueError("command must be start or stop")
    duration = arguments.get("duration_seconds", 16)
    if isinstance(duration, bool) or not isinstance(duration, (int, float)) or not math.isfinite(duration) or not 1 <= duration <= 300:
        raise ValueError("duration_seconds must be finite and within 1..300")
    return {"command": command, "duration_seconds": float(duration)}


def tool_definitions():
    return [
        {"type": "function", "function": {
            "name": "setsuna_local_music",
            "description": "雪菜本地歌曲播放与唱歌联动。用户说唱首歌/唱某首/想听你唱，等价于从本地曲库选歌播放：先list（可query歌名）取真实路径，再play。曲库为程序目录内的「雪菜歌」，按实际文件动态扫描，可随安装位置移动；只能播放此目录内的音频，不去旧目录或其他文件夹找歌。实际开始播放才进入唱歌动作，暂停/停止/结束退场；不需要另外setsuna_sing。聊天内play返回queued_after_reply表示已安排在本轮开场白语音后播放，并非已开播，不要重复调用。status可查询实际进度或错误。next/previous切换下一首/上一首；set_mode设置sequence顺序播放、list_loop列表循环、single_loop单曲循环、shuffle随机播放。list支持query筛选和offset翻页，使用返回的路径，不臆造曲目；空曲库应提示用户放入成品歌曲。QQ音乐/网易云/浏览器等外部应用使用原exec_shell或control_playback，本工具不控制它们，也不为它们触发唱歌。",
            "parameters": {"type": "object", "properties": {
                "command": {"type": "string", "enum": ["list", "play", "pause", "resume", "stop", "status", "next", "previous", "set_mode"]},
                "query": {"type": "string", "description": "list时按歌名筛选，空为全部"},
                "path": {"type": "string", "description": "play时填当前曲库list返回的路径；省略则播放当前/首曲"},
                "mode": {"type": "string", "enum": ["sequence", "list_loop", "single_loop", "shuffle"], "description": "set_mode必填"},
                "offset": {"type": "integer", "minimum": 0, "description": "list分页起点，默认0，每页80首"}
            }, "required": ["command"], "additionalProperties": False}}},
        {"type": "function", "function": {
            "name": "setsuna_sing",
            "description": "播放雪菜原生唱歌动作（入场、持麦循环、退场）。仅用户明确要唱歌姿势/动作或手动测试时start；想听歌/让你唱歌应使用setsuna_local_music选歌播放，自动联动此动作。停止动作时stop。仅动作，自带节奏口型但不提供歌曲音频，不声称已播放歌曲。聊天中start先排队，语音实际开始才执行，到本轮回复/语音结束再退场，最多300秒；手动测试循环默认16秒，入退场各4.2秒；正在唱歌时重复start和其他perform会被拒绝，不排队。本轮调用start或stop后直接输出最终JSON，不再perform；stop返回stopping表示退场尚未完成。",
            "parameters": {"type": "object", "properties": {
                "command": {"type": "string", "enum": ["start", "stop"]},
                "duration_seconds": {"type": "number", "minimum": 1, "maximum": 300, "description": "循环时长，默认16秒；stop时忽略"}
            }, "required": ["command"], "additionalProperties": False}}},
        {"type": "function", "function": {
            "name": "setsuna_perform",
            "description": "雪菜的身体表达接口：普通聊天也应主动配合情绪调用，不必等待用户要求动作。问候/欢迎/赞同用 smile+nod，温柔否认用 worry或smile+shake，被夸用 shy+nod或blink，疑惑用 thinking+none+up。每次回复通常最多一次，强度建议0.65到0.85；用户要求安静不动时不调用。聊天中返回queued_for_playback表示已选定待播放动作，不是已执行；合成语音时保持思考，实际播放时执行一次。非聊天started表示动作已开始。14种表情直接使用模型预设，新增smile_closed开心笑眼和cry哭泣。angry/cry固定正面，不能强行转头。唱歌请用setsuna_sing。没有摸头、戳脸、拥抱、拍肩互动。",
            "parameters": {"type": "object", "properties": {
                "expression": {"type": "string", "enum": list(EXPRESSIONS)},
                "motion": {"type": "string", "enum": list(MOTIONS)},
                "look": {"type": "string", "enum": list(LOOKS)},
                "intensity": {"type": "number", "minimum": 0, "maximum": 1},
                "hold_ms": {"type": "integer", "minimum": 300, "maximum": 8000, "description": "仅限制点头/摇头/视线动作，表情保持至本轮回复或语音结束，不必续调"},
            }, "required": ["expression", "motion", "look", "intensity", "hold_ms"], "additionalProperties": False}}},
        {"type": "function", "function": {"name": "setsuna_status",
            "description": "查询雪菜 Live2D 的真实渲染状态、可用动作和最近动作状态。未加载时会返回错误。",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False}}},
        {"type": "function", "function": {"name": "setsuna_reset",
            "description": "取消当前 Live2D 动作并平滑恢复中性待机；自动眨眼、呼吸和正在播放的语音口型继续工作。",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False}}},
    ]


def live2d_settings(config, pack_id=None):
    pm = config.pack_manager
    target = pack_id or pm.active_pack_id
    target = getattr(pm, "id_map", {}).get(target, target)
    data = pm.pack_data if target == pm.active_pack_id else pm._get_pack_data(target)
    settings = data.get("character", {}).get("live2d", {})
    return target, settings if isinstance(settings, dict) else {}


def live2d_prompt_path(config, pack_id=None):
    target, settings = live2d_settings(config, pack_id)
    if not settings.get("enabled") or not settings.get("prompt"):
        return None
    root = (config.pack_manager.packs_dir / target).resolve()
    path = (root / settings["prompt"]).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError("Live2D prompt is missing or outside its character pack")
    return path

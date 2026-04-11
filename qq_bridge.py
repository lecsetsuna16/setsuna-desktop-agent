#!/usr/bin/env python3
"""
Resona QQ Bridge
将主人的 QQ 私信转发给桌宠，并把回复发回 QQ。

依赖:
  - NapCat 运行在 Bot 小号上，开启 OneBot 11 正向 WebSocket 服务
  - Resona 的 HTML 服务器已启用 (config.cfg: [HTML] enabled=true, host=127.0.0.1)

使用方法:
  1. 在下方填入 OWNER_QQ（你的主号）
  2. 确认 NAPCAT_WS_URL 端口与 NapCat 设置一致
  3. 运行: python qq_bridge.py  或双击 start_qq_bridge.bat
"""

import asyncio
import json
import logging
import re
import time
import websockets

# ── 配置区（修改这里）─────────────────────────────────────────────────────────
OWNER_QQ       = "在这里填你的主QQ号"   # 只有这个 QQ 号的消息会被处理
NAPCAT_WS_URL  = "ws://127.0.0.1:3001"  # NapCat OneBot 11 正向 WS 地址
RESONA_WS_URL  = "ws://127.0.0.1:8000/ws"  # Resona HTML WebSocket 地址
RESONA_PACK    = "setsuna"              # 当前使用的 pack 名称
RECONNECT_SEC  = 5                      # 断线后重连等待秒数
RESPONSE_TIMEOUT = 60                   # 等待桌宠回复的最大秒数
# ──────────────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger(__name__)


def clean_response(text: str) -> str:
    """去掉回复里的动作描写括号，保留纯对话内容发给 QQ。"""
    # 去掉中文括号内的动作描写，例如（下意识抓着长发）
    text = re.sub(r'（[^）]{1,50}）', '', text)
    # 去掉英文括号内的内心独白
    text = re.sub(r'\([^)]{1,80}\)', '', text)
    return text.strip()


async def query_resona(question: str) -> str:
    """向 Resona HTML WebSocket 发送问题，等待并返回回复文本。"""
    try:
        async with websockets.connect(RESONA_WS_URL, open_timeout=5) as ws:
            # 握手
            await ws.send(json.dumps({
                "pack_id": RESONA_PACK,
                "client_type": "qq_bridge"
            }))
            ack_raw = await asyncio.wait_for(ws.recv(), timeout=5)
            ack = json.loads(ack_raw)
            if ack.get("type") != "handshake_ack":
                log.warning(f"[Resona] 握手异常: {ack.get('type')}")

            # 发送问题
            await ws.send(json.dumps({"type": "text_input", "text": question}))
            log.info(f"[Pet←QQ] 已发送: {question}")

            # 等待 speak 消息
            deadline = time.time() + RESPONSE_TIMEOUT
            while time.time() < deadline:
                remaining = deadline - time.time()
                if remaining <= 0:
                    break
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
                    msg = json.loads(raw)
                    msg_type = msg.get("type")
                    if msg_type == "speak":
                        return msg.get("text", "")
                    elif msg_type == "error":
                        log.error(f"[Resona] 返回错误: {msg.get('message')}")
                        return ""
                    # status/thinking 消息忽略，继续等
                except asyncio.TimeoutError:
                    break

    except ConnectionRefusedError:
        log.error("[Resona] 连接被拒绝——桌宠是否已启动且 HTML 服务器已开启？")
    except Exception as e:
        log.error(f"[Resona] 连接异常: {e}")
    return ""


def extract_text(segments: list) -> str:
    """从 OneBot 11 消息段中提取纯文本。"""
    return "".join(
        seg["data"].get("text", "")
        for seg in segments
        if seg.get("type") == "text"
    ).strip()


async def send_private_msg(ws, target_qq: str, text: str):
    """通过 NapCat WebSocket API 发送私信。"""
    await ws.send(json.dumps({
        "action": "send_private_msg",
        "params": {
            "user_id": int(target_qq),
            "message": [{"type": "text", "data": {"text": text}}]
        },
        "echo": f"reply-{int(time.time() * 1000)}"
    }))


async def run_bridge():
    while True:
        try:
            log.info(f"[Bridge] 正在连接 NapCat: {NAPCAT_WS_URL}")
            async with websockets.connect(NAPCAT_WS_URL, open_timeout=10) as ws:
                log.info(f"[Bridge] 已连接，监听来自 {OWNER_QQ} 的私信...")

                async for raw in ws:
                    try:
                        event = json.loads(raw)
                    except json.JSONDecodeError:
                        continue

                    # 只处理私信消息事件
                    if event.get("post_type") != "message":
                        continue
                    if event.get("message_type") != "private":
                        continue

                    sender = str(event.get("user_id", ""))
                    if sender != OWNER_QQ:
                        continue  # 白名单过滤

                    text = extract_text(event.get("message", []))
                    if not text:
                        continue

                    log.info(f"[QQ→Pet] {text}")
                    response = await query_resona(text)

                    if response:
                        cleaned = clean_response(response)
                        log.info(f"[Pet→QQ] {cleaned}")
                        await send_private_msg(ws, OWNER_QQ, cleaned)
                    else:
                        log.warning("[Bridge] 桌宠无回应，未发送回复")

        except (websockets.exceptions.ConnectionClosed, OSError) as e:
            log.warning(f"[Bridge] 连接断开: {e}，{RECONNECT_SEC}s 后重连...")
            await asyncio.sleep(RECONNECT_SEC)
        except Exception as e:
            log.error(f"[Bridge] 未知错误: {e}，{RECONNECT_SEC}s 后重连...")
            await asyncio.sleep(RECONNECT_SEC)


if __name__ == "__main__":
    log.info("=" * 40)
    log.info("  Resona QQ Bridge")
    log.info(f"  主人QQ  : {OWNER_QQ}")
    log.info(f"  NapCat  : {NAPCAT_WS_URL}")
    log.info(f"  Resona  : {RESONA_WS_URL}")
    log.info("=" * 40)

    if OWNER_QQ == "在这里填你的主QQ号":
        log.error("请先在 qq_bridge.py 顶部填入你的主QQ号，然后再运行！")
        exit(1)

    asyncio.run(run_bridge())

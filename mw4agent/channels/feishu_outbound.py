"""Feishu outbound adapter for MW4Agent.

Phase 1: minimal text-only implementation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..feishu.client import FeishuClient
from ..log import get_logger

logger = get_logger(__name__)

# 思考/正在输入 指示器使用的 emoji（与 feishu-openclaw-plugin 一致：Typing=铅笔动效，THINKING=思考）
TYPING_EMOJI = "Typing"


@dataclass
class TypingIndicatorState:
    """添加思考表情后返回的状态，用于后续删除。"""
    message_id: str
    reaction_id: Optional[str] = None


async def add_typing_indicator(message_id: str, emoji_type: str = TYPING_EMOJI) -> TypingIndicatorState:
    """在用户消息上添加「正在输入/思考」表情。失败静默，返回 state 供 remove 使用。"""
    state = TypingIndicatorState(message_id=message_id, reaction_id=None)
    if not (message_id or "").strip():
        return state
    try:
        client = FeishuClient()
        rid = await client.add_reaction(message_id=message_id, emoji_type=emoji_type)
        state.reaction_id = rid
        if rid:
            logger.debug("[feishu] typing indicator added message_id=%s", message_id)
    except Exception as e:
        logger.debug("[feishu] add typing indicator failed: %s", e)
    return state


async def remove_typing_indicator(state: TypingIndicatorState) -> None:
    """移除之前添加的思考表情。静默忽略错误。"""
    if not state.reaction_id:
        return
    try:
        client = FeishuClient()
        await client.remove_reaction(message_id=state.message_id, reaction_id=state.reaction_id)
        logger.debug("[feishu] typing indicator removed message_id=%s", state.message_id)
    except Exception as e:
        logger.debug("[feishu] remove typing indicator failed: %s", e)


async def send_text(
    *,
    cfg: object | None,
    to: str,
    text: str,
    account_id: Optional[str] = None,
    reply_to_id: Optional[str] = None,
    thread_id: Optional[str] = None,
    mentions: Optional[list[str]] = None,
) -> None:
    """Send a text message to Feishu.

    - `to` 目前视为 chat_id
    - Phase 1 中忽略 cfg/account_id 等多账号细节，由环境变量控制凭证
    """
    message_text = text
    # 简单 mention 拼接（后续可对齐 OpenClaw 的 @ 语法）
    if mentions:
        prefix = " ".join(mentions)
        if prefix:
            message_text = f"{prefix} {message_text}"

    client = FeishuClient()
    await client.send_text(
        chat_id=to,
        text=message_text,
        reply_to_message_id=reply_to_id,
        reply_in_thread=bool(thread_id),
    )


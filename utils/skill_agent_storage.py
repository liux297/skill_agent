from __future__ import annotations

import json
import time
from typing import Any

from utils.skill_agent_constants import HISTORY_KEY_PREFIX, RESUME_KEY_PREFIX, SESSION_DIR_KEY_PREFIX
from utils.skill_agent_exec import DEFAULT_SKILL_SPACE, _normalize_skill_space
from utils.tools import _safe_get


def _get_session_storage_id(session: Any, skill_space: object | None = None) -> str:
    """确定存储隔离锚点：优先 Dify 会话 (conversation_id)，缺失时退回单次请求 id。

    以往这里会把取不到的候选一路回退到 "global"，导致不同会话共享同一个
    storage key 与 temp 目录，造成跨会话文件互通。现改为：
    - conversation_id：Dify 会话语义，同会话多轮可续跑，不同会话严格隔离
    - session_id：SDK 每次请求唯一，用于 conversation 缺失时的安全兜底（绝不跨会话泄漏）
    - 仅二者皆为空才回退 "global"
    """
    conversation_id = _safe_get(session, "conversation_id")
    if isinstance(conversation_id, str) and conversation_id.strip():
        session_id = conversation_id.strip()
    else:
        request_id = _safe_get(session, "session_id")
        session_id = request_id.strip() if isinstance(request_id, str) and request_id.strip() else "global"
    space = _normalize_skill_space(skill_space)
    if space == DEFAULT_SKILL_SPACE:
        return session_id
    return f"space:{space}:{session_id}"


def _get_resume_storage_key(session: Any, skill_space: object | None = None) -> str:
    return RESUME_KEY_PREFIX + _get_session_storage_id(session, skill_space)


def _get_history_storage_key(session: Any, skill_space: object | None = None) -> str:
    return HISTORY_KEY_PREFIX + _get_session_storage_id(session, skill_space)


def _get_session_dir_storage_key(session: Any, skill_space: object | None = None) -> str:
    return SESSION_DIR_KEY_PREFIX + _get_session_storage_id(session, skill_space)


def _storage_get_text(storage: Any, key: str) -> str:
    try:
        val = storage.get(key)
        if not val:
            return ""
        if isinstance(val, bytes):
            return val.decode("utf-8", errors="ignore")
        if isinstance(val, str):
            return val
        return ""
    except Exception:
        return ""


def _storage_set_text(storage: Any, key: str, text: str) -> None:
    try:
        storage.set(key, (text or "").encode("utf-8"))
    except Exception:
        return


def _storage_get_json(storage: Any, key: str) -> dict[str, Any]:
    raw = _storage_get_text(storage, key).strip()
    if not raw:
        return {}
    try:
        val = json.loads(raw)
        return val if isinstance(val, dict) else {}
    except Exception:
        return {}


def _storage_set_json(storage: Any, key: str, value: dict[str, Any] | None) -> None:
    if not value:
        _storage_set_text(storage, key, "")
        return
    try:
        _storage_set_text(storage, key, json.dumps(value, ensure_ascii=False))
    except Exception:
        _storage_set_text(storage, key, "")
        return


def _append_history_turn(
    storage: Any,
    *,
    history_key: str,
    user_text: str,
    assistant_text: str,
    max_turns: int = 50,
) -> None:
    state = _storage_get_json(storage, history_key)
    turns = state.get("turns")
    if not isinstance(turns, list):
        turns = []
    turns.append(
        {
            "user": str(user_text or ""),
            "assistant": str(assistant_text or ""),
            "created_at": int(time.time()),
        }
    )
    if max_turns < 1:
        max_turns = 1
    if len(turns) > max_turns:
        turns = turns[-max_turns:]
    _storage_set_json(storage, history_key, {"turns": turns})

"""Streamlit ↔ PG chat schema 어댑터.

api/main.py 의 _persist_turn / _load_history 와 같은 로직이지만 UI 가 직접 호출.
session_state 기반 thread_id 관리.
"""

from __future__ import annotations

import json
import uuid
from typing import Any


def get_or_create_thread_id() -> str:
    """Streamlit session 단위 thread_id. 새 대화 시 reset 호출."""
    import streamlit as st
    if "thread_id" not in st.session_state:
        st.session_state.thread_id = f"web-{uuid.uuid4().hex[:12]}"
    return st.session_state.thread_id


def reset_thread() -> None:
    import streamlit as st
    st.session_state.thread_id = f"web-{uuid.uuid4().hex[:12]}"
    st.session_state.messages = []
    st.session_state.cumulative_cost_usd = 0.0


def load_history(thread_id: str, limit: int = 20) -> list[dict]:
    """이전 user/assistant turn (PG chat.messages 직접 조회)."""
    from ..db.postgres import get_pool

    sql = """
    WITH conv AS (
      SELECT id FROM chat.conversations WHERE thread_id = %s
    )
    SELECT role, content, citations, agent_trace, created_at
      FROM chat.messages m
      JOIN conv c ON m.conversation_id = c.id
     WHERE m.role IN ('user', 'assistant')
     ORDER BY turn_idx DESC
     LIMIT %s
    """
    out: list[dict] = []
    try:
        with get_pool().connection() as conn, conn.cursor() as cur:
            cur.execute(sql, (thread_id, limit))
            for role, content, citations, trace, created in cur.fetchall():
                out.append({
                    "role": role,
                    "content": content,
                    "citations": citations or [],
                    "agent_trace": trace or {},
                    "created_at": created.isoformat() if created else None,
                })
    except Exception:
        return []
    return list(reversed(out))


def persist_turn(
    thread_id: str,
    role: str,
    content: str,
    *,
    citations: list[dict] | None = None,
    agent_trace: dict[str, Any] | None = None,
) -> None:
    """PG chat.conversations + chat.messages 멱등 적재."""
    from ..db.postgres import get_pool

    sql_conv = """
    INSERT INTO chat.conversations (thread_id)
    VALUES (%s)
    ON CONFLICT (thread_id) DO UPDATE SET updated_at = now()
    RETURNING id
    """
    sql_max_turn = "SELECT coalesce(max(turn_idx), -1) + 1 FROM chat.messages WHERE conversation_id = %s"
    sql_insert = """
    INSERT INTO chat.messages
      (conversation_id, turn_idx, role, content, citations, agent_trace)
    VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb)
    ON CONFLICT (conversation_id, turn_idx, role) DO NOTHING
    """
    try:
        with get_pool().connection() as conn, conn.cursor() as cur:
            cur.execute(sql_conv, (thread_id,))
            conv_id = cur.fetchone()[0]
            cur.execute(sql_max_turn, (conv_id,))
            next_turn = cur.fetchone()[0]
            cur.execute(sql_insert, (
                conv_id, next_turn, role, content,
                json.dumps(citations or [], ensure_ascii=False),
                json.dumps(agent_trace or {}, ensure_ascii=False),
            ))
    except Exception:
        # UI 는 DB 적재 실패해도 화면은 보여야 함
        pass


def list_recent_threads(limit: int = 10) -> list[dict]:
    """사이드바용 — 최근 대화 목록."""
    from ..db.postgres import get_pool
    sql = """
    SELECT c.thread_id, c.title, c.updated_at, count(m.id) AS n_messages
      FROM chat.conversations c
      LEFT JOIN chat.messages m ON m.conversation_id = c.id
     GROUP BY c.thread_id, c.title, c.updated_at
     ORDER BY c.updated_at DESC
     LIMIT %s
    """
    try:
        with get_pool().connection() as conn, conn.cursor() as cur:
            cur.execute(sql, (limit,))
            return [
                {"thread_id": tid, "title": title,
                 "updated_at": ts.isoformat() if ts else None, "n_messages": n}
                for tid, title, ts, n in cur.fetchall()
            ]
    except Exception:
        return []

"""FastAPI 진입점 — 에이전트 채팅 API.

엔드포인트:
- POST /chat                : 단일 turn 실행 → 답변 + 인용 + 비용
- GET  /threads/{id}        : 대화 히스토리 조회 (PG chat.messages)
- POST /threads/{id}/message: 멀티턴 — history 자동 주입

응답 메타에 cost_usd / tokens 포함 (사용자 명시 — 모든 호출 비용 가시화).

기동:
    uvicorn fingraph.api.main:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from ..agents import run_agent
from ..db.postgres import get_pool


log = logging.getLogger(__name__)


app = FastAPI(title="FinGraph Agent API", version="0.1")


# ── Request/Response 모델 ───────────────────────────────────
class ChatRequest(BaseModel):
    thread_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    message: str
    use_history: bool = True


class ChatResponse(BaseModel):
    thread_id: str
    answer: str
    citations: list[dict]
    question_kind: str | None = None
    target_companies: list[str] = []
    cost_usd: float = 0.0
    aborted_reason: str | None = None
    n_tool_results: int = 0


# ── chat endpoint ───────────────────────────────────────────
@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    """단일 대화 turn — agent 실행 + history 적재."""
    history = _load_history(req.thread_id) if req.use_history else []
    try:
        state = run_agent(req.message, thread_id=req.thread_id, history=history)
    except Exception as e:
        log.exception("[chat] agent failed")
        raise HTTPException(500, f"agent failed: {e}")

    # PG chat.messages 에 user + assistant 두 turn 적재
    _persist_turn(req.thread_id, "user", req.message, citations=None, trace=None)
    _persist_turn(req.thread_id, "assistant", state.get("answer", ""),
                   citations=state.get("citations"),
                   trace={"question_kind": state.get("question_kind"),
                          "target_companies": state.get("target_companies"),
                          "n_tool_results": len(state.get("tool_results") or []),
                          "cost_usd": state.get("llm_usage_usd"),
                          "aborted_reason": state.get("aborted_reason")})

    return ChatResponse(
        thread_id=req.thread_id,
        answer=state.get("answer", ""),
        citations=state.get("citations") or [],
        question_kind=state.get("question_kind"),
        target_companies=state.get("target_companies") or [],
        cost_usd=float(state.get("llm_usage_usd") or 0.0),
        aborted_reason=state.get("aborted_reason"),
        n_tool_results=len(state.get("tool_results") or []),
    )


# ── threads endpoints ───────────────────────────────────────
@app.get("/threads/{thread_id}")
def get_thread(thread_id: str) -> dict:
    """대화 히스토리 조회."""
    messages = _load_history(thread_id, limit=200)
    return {"thread_id": thread_id, "messages": messages}


@app.get("/health")
def health() -> dict:
    """간단 헬스 — PG/Neo4j ping."""
    out: dict = {"api": "ok"}
    try:
        with get_pool().connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1")
        out["postgres"] = "ok"
    except Exception as e:
        out["postgres"] = f"error: {e}"
    try:
        from ..db.neo4j import get_driver
        with get_driver().session() as s:
            s.run("RETURN 1").consume()
        out["neo4j"] = "ok"
    except Exception as e:
        out["neo4j"] = f"error: {e}"
    return out


# ── persistence ─────────────────────────────────────────────
def _load_history(thread_id: str, limit: int = 20) -> list[dict]:
    """이전 메시지 N 개. user/assistant 만 (system 제외)."""
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
    with get_pool().connection() as conn, conn.cursor() as cur:
        cur.execute(sql, (thread_id, limit))
        for role, content, citations, trace, created in cur.fetchall():
            out.append({"role": role, "content": content,
                         "citations": citations or [], "agent_trace": trace or {},
                         "created_at": created.isoformat() if created else None})
    return list(reversed(out))


def _persist_turn(thread_id: str, role: str, content: str,
                  citations: list | None,
                  trace: dict | None) -> None:
    """conversations + messages 적재 (없으면 conversation 생성). 멱등 + turn_idx 자동."""
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
    with get_pool().connection() as conn, conn.cursor() as cur:
        cur.execute(sql_conv, (thread_id,))
        conv_id = cur.fetchone()[0]
        cur.execute(sql_max_turn, (conv_id,))
        next_turn = cur.fetchone()[0]
        cur.execute(sql_insert, (
            conv_id, next_turn, role, content,
            json.dumps(citations or [], ensure_ascii=False),
            json.dumps(trace or {}, ensure_ascii=False),
        ))


__all__ = ["app"]

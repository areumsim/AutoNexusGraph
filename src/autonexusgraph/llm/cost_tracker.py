"""런타임 LLM 비용 트래커 + circuit breaker — ContextVar 격리.

설계 (v2 — 근본 재정비):
- ContextVar 기반 격리. FastAPI threadpool / asyncio task 단위로 자동 분리되어
  multi-turn 동시 실행 시 turn boundary 가 깨지지 않는다.
- 기존 process singleton (_singleton + _singleton_lock) 제거.
- get_tracker / get_session_tracker 이원화 → get_session_tracker 단일 진입점.
- ops.llm_usage 의 ``meta JSONB`` 컬럼에 turn 식별자 (thread_id, turn_id, n_replans,
  domain) 적재 — 별도 ALTER 불필요.

수명 주기 (turn 단위):
    from autonexusgraph.agents.tracing import start_turn_context

    with start_turn_context(thread_id="t1", state={"domain": "auto"}) as turn:
        resp = client.chat(...)         # budget_aware wrapper 가 tracker 자동 사용
        turn.state["n_replans"] = 2     # final state 갱신
    # __exit__ 시 tracker.finalize() + meta JSONB 영구 적재.

배치 (extractor) 단위:
    with CostTracker(caller='p3_extract', model='gpt-4o-mini') as tracker:
        tracker.guard()
        ...
"""

from __future__ import annotations

import logging
import os
import threading
import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

from .cost import (
    cost_of_call,
    get_cost_window_hours,
    get_hard_limit_usd,
    get_report_every,
    get_session_limit_usd,
)


log = logging.getLogger(__name__)


def _read_session_base() -> float:
    """cost_log.jsonl 에서 영속 누적 비용 baseline 읽기 (tracker 생성 시 1회).

    llm_cost_window_hours 시간창 안의 합. 파일/파싱 실패는 0.0 (fail-soft).
    이 값 + 현재 tracker 누적 = 실제 영속 누계 → 세션 한도 가드의 기준.
    """
    try:
        from datetime import datetime, timedelta, timezone
        from .cost_log import total_cost
        hrs = get_cost_window_hours()
        since = None
        if hrs and hrs > 0:
            since = datetime.now(timezone.utc) - timedelta(hours=hrs)
        return float(total_cost(since=since))
    except Exception as e:   # noqa: BLE001
        log.debug("[COST] session base read failed: %s", e)
        return 0.0


class BudgetExceeded(Exception):
    """누적 비용이 한도 도달 — turn/batch abort 신호."""


@dataclass
class TrackerState:
    run_id: str
    caller: str
    model: str
    hard_limit_usd: float
    n_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    aborted: bool = False
    finalized: bool = False
    # turn 식별자 — ops.llm_usage.meta JSONB 에 적재
    thread_id: str | None = None
    turn_id: str | None = None
    domain: str | None = None
    n_replans: int = 0
    extra_meta: dict = field(default_factory=dict)


class CostTracker:
    """프로세스 단위 LLM 비용 누적 + 한도 가드.

    ContextVar 로 격리되어 동시 실행 turn 끼리 공유되지 않는다.
    """

    def __init__(self, caller: str, model: str,
                 hard_limit: float | None = None,
                 *,
                 thread_id: str | None = None,
                 turn_id: str | None = None,
                 domain: str | None = None) -> None:
        limit = hard_limit if hard_limit is not None else get_hard_limit_usd()
        self.state = TrackerState(
            run_id=str(uuid.uuid4()),
            caller=caller,
            model=model,
            hard_limit_usd=limit,
            thread_id=thread_id,
            turn_id=turn_id or str(uuid.uuid4()),
            domain=domain,
        )
        self._lock = threading.Lock()
        self._report_every = get_report_every()
        # 영속(세션/일) 누적 가드 — cost_log.jsonl 기반. turn/process 리셋과 무관.
        # base 는 생성 시점 1회 스냅샷 (호출마다 파일 재독 안 함). guard 는
        # base + 현재 tracker 누적 vs session_limit 비교.
        self._session_limit_usd = get_session_limit_usd()
        self._session_base_usd = _read_session_base()
        self._persist_initial()

    # ── 누적 ───────────────────────────────────────────────────
    def record(self, input_tokens: int, output_tokens: int,
               model: str | None = None, *, purpose: str | None = None,
               latency_ms: int | None = None) -> None:
        """단일 호출 사용량 기록 + 한도 체크 (post-record)."""
        m = model or self.state.model
        c = cost_of_call(m, input_tokens, output_tokens)
        with self._lock:
            self.state.n_calls += 1
            self.state.input_tokens += input_tokens
            self.state.output_tokens += output_tokens
            self.state.cost_usd += c
            n = self.state.n_calls
            cum = self.state.cost_usd
            limit = self.state.hard_limit_usd

        # call detail 비동기 적재는 옵션. 기본은 끔 (대량 호출 시 부하).
        if os.environ.get("LLM_COST_LOG_CALLS") == "1":
            self._persist_call(m, input_tokens, output_tokens, c,
                               purpose=purpose, latency_ms=latency_ms)

        # warn 임계 — 세션 한도의 settings.llm_session_warn_at_usd 또는 90%.
        warn_at = limit * 0.9
        try:
            from ..config import get_settings
            warn_at = max(0.0, float(get_settings().llm_session_warn_at_usd))
        except Exception:   # noqa: BLE001
            pass
        if n % self._report_every == 0 or cum >= warn_at:
            log.info(f"[COST] {self.state.caller} n_calls={n} cum=${cum:.4f} "
                     f"(limit ${limit:.4f}, {100*cum/max(limit,1e-9):.1f}%)")

    def guard(self) -> None:
        """다음 호출 전에 한도 확인. 둘 중 하나라도 초과면 BudgetExceeded.

        1. per-turn/batch: 이 tracker 자체 누적 ≥ hard_limit_usd
        2. 영속(세션/일): session_base + 이 tracker 누적 ≥ session_limit_usd
           (cost_log.jsonl 기반 — turn/process 리셋과 무관하게 누적 차단)
        """
        with self._lock:
            cum = self.state.cost_usd
            if cum >= self.state.hard_limit_usd:
                self.state.aborted = True
                raise BudgetExceeded(
                    f"turn 누적 ${cum:.4f} ≥ hard_limit "
                    f"${self.state.hard_limit_usd:.4f} (caller={self.state.caller})"
                )
            session_total = self._session_base_usd + cum
            if session_total >= self._session_limit_usd:
                self.state.aborted = True
                raise BudgetExceeded(
                    f"세션 누적 ${session_total:.4f} ≥ session_limit "
                    f"${self._session_limit_usd:.4f} "
                    f"(base ${self._session_base_usd:.4f} + turn ${cum:.4f}, "
                    f"caller={self.state.caller})"
                )

    def session_spent_usd(self) -> float:
        """현재 영속 누계 추정 (base 스냅샷 + 이 tracker 누적) — 진단용."""
        with self._lock:
            return self._session_base_usd + self.state.cost_usd

    # ── 종료 ──────────────────────────────────────────────────
    def finalize(self, status: str = "ok", *,
                 n_replans: int | None = None,
                 extra_meta: dict | None = None) -> None:
        """run 종료 — ops.llm_usage 의 ended_at/총합/status + meta JSONB 갱신.

        n_replans: turn 단위 lifecycle 에서 final state.n_replans 전달.
        extra_meta: 추가 메타 (예: ``{"question_kind": "factual"}``) — meta JSONB 머지.
        """
        with self._lock:
            if self.state.finalized:
                return
            if self.state.aborted and status == "ok":
                status = "aborted_budget"
            if n_replans is not None:
                self.state.n_replans = int(n_replans)
            if extra_meta:
                self.state.extra_meta.update(extra_meta)
            self.state.finalized = True
        self._persist_final(status)
        log.info(f"[COST] FINAL caller={self.state.caller} status={status} "
                 f"n_calls={self.state.n_calls} cost=${self.state.cost_usd:.4f} "
                 f"n_replans={self.state.n_replans}")

    # ── meta JSONB 직렬화 (PG 적재 공통) ─────────────────────────
    def _build_meta(self) -> dict:
        """ops.llm_usage.meta 에 적재할 dict — turn 식별자 + extra_meta 통합."""
        meta: dict = {}
        if self.state.thread_id is not None:
            meta["thread_id"] = self.state.thread_id
        if self.state.turn_id is not None:
            meta["turn_id"] = self.state.turn_id
        if self.state.domain is not None:
            meta["domain"] = self.state.domain
        meta["n_replans"] = self.state.n_replans
        if self.state.extra_meta:
            meta.update(self.state.extra_meta)
        return meta

    # ── DB 적재 (모두 best-effort — DB 다운 시 추적은 메모리에만) ─────
    def _persist_initial(self) -> None:
        try:
            import json
            from ..db.postgres import get_pool
            with get_pool().connection() as conn, conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO ops.llm_usage (run_id, caller, model, status, meta)
                    VALUES (%s, %s, %s, 'running', %s::jsonb)
                    """,
                    (self.state.run_id, self.state.caller, self.state.model,
                     json.dumps(self._build_meta())),
                )
        except Exception as e:
            log.warning(f"[COST] llm_usage init persist failed: {e}")

    def _persist_final(self, status: str) -> None:
        try:
            import json
            from ..db.postgres import get_pool
            with get_pool().connection() as conn, conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE ops.llm_usage
                       SET ended_at      = now(),
                           n_calls       = %s,
                           input_tokens  = %s,
                           output_tokens = %s,
                           cost_usd      = %s,
                           status        = %s,
                           meta          = meta || %s::jsonb
                     WHERE run_id = %s
                    """,
                    (self.state.n_calls, self.state.input_tokens,
                     self.state.output_tokens, self.state.cost_usd,
                     status, json.dumps(self._build_meta()),
                     self.state.run_id),
                )
        except Exception as e:
            log.warning(f"[COST] llm_usage final persist failed: {e}")

    def _persist_call(self, model: str, input_tokens: int, output_tokens: int,
                       cost: float, *, purpose: str | None,
                       latency_ms: int | None) -> None:
        try:
            from ..db.postgres import get_pool
            with get_pool().connection() as conn, conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO ops.llm_calls
                      (run_id, model, purpose, input_tokens, output_tokens,
                       cost_usd, latency_ms)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (self.state.run_id, model, purpose, input_tokens,
                     output_tokens, cost, latency_ms),
                )
        except Exception as e:
            log.debug(f"[COST] llm_calls persist failed: {e}")

    # ── 컨텍스트 매니저 ────────────────────────────────────────
    def __enter__(self) -> "CostTracker":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if exc_type is BudgetExceeded:
            self.finalize("aborted_budget")
        elif exc_type is not None:
            self.finalize("error")
        else:
            self.finalize("ok")


# ─── ContextVar 격리 ─────────────────────────────────────────────
# FastAPI threadpool / asyncio task 단위로 자동 분리.
# 동시 turn A/B 가 서로의 tracker 를 덮어쓰지 않는다.
_tracker_ctx: ContextVar["CostTracker | None"] = ContextVar(
    "autonexus_cost_tracker", default=None,
)


def get_session_tracker(caller: str | None = None,
                        model: str | None = None,
                        *,
                        thread_id: str | None = None,
                        turn_id: str | None = None,
                        domain: str | None = None,
                        hard_limit: float | None = None) -> CostTracker:
    """현재 context 의 session tracker 반환. 없으면 새로 생성 후 ctx set.

    ``start_turn_context`` 가 이미 새 tracker 를 ctx 에 박아둔 경우 그것을 그대로
    반환. 일반 batch 코드는 ``with CostTracker(...) as tracker`` 직접 사용 가능.
    """
    tracker = _tracker_ctx.get()
    if tracker is not None and not tracker.state.finalized:
        # 기존 tracker 재사용. 더 빡빡한 한도가 들어오면 하향 반영(절대 느슨하게
        # 만들지 않음). 과거 버그: 여기서 hard_limit 을 통째로 무시해 노드가 넘긴
        # turn budget(0.20)이 버려지고 5.00 이 적용됐음.
        if hard_limit is not None and hard_limit < tracker.state.hard_limit_usd:
            with tracker._lock:
                tracker.state.hard_limit_usd = hard_limit
        return tracker

    # ctx 에 없거나 이전 tracker 가 이미 finalized 인 경우 — 새로 생성.
    # hard_limit=None 이면 CostTracker 가 get_hard_limit_usd() 로 기본값 적용.
    tracker = CostTracker(
        caller=caller or "session",
        model=model or "mixed",
        hard_limit=hard_limit,
        thread_id=thread_id,
        turn_id=turn_id,
        domain=domain,
    )
    _tracker_ctx.set(tracker)
    return tracker


def reset_tracker() -> None:
    """현재 context 의 tracker 를 finalize 한 뒤 ctx 비움. 다음 호출은 새 tracker."""
    tracker = _tracker_ctx.get()
    if tracker is not None and not tracker.state.finalized:
        tracker.finalize("ok")
    _tracker_ctx.set(None)


def set_current_tracker(tracker: "CostTracker | None") -> None:
    """ctx 변수에 tracker 박기 — start_turn_context 가 사용."""
    _tracker_ctx.set(tracker)


def current_tracker() -> "CostTracker | None":
    """현재 context 의 tracker (없으면 None) — 진단·테스트용."""
    return _tracker_ctx.get()


# ── 하위 호환 alias — 기존 호출자 (extract_business_report_relations.py 등) ──
def get_tracker(caller: str, model: str,
                hard_limit: float | None = None) -> CostTracker:
    """[deprecated] ContextVar 격리 도입 전 호출자 호환. 새 코드는 get_session_tracker
    또는 ``with CostTracker(...)`` 사용."""
    return get_session_tracker(caller=caller, model=model, hard_limit=hard_limit)


__all__ = [
    "CostTracker", "BudgetExceeded",
    "get_tracker", "reset_tracker", "get_session_tracker",
    "set_current_tracker", "current_tracker",
]

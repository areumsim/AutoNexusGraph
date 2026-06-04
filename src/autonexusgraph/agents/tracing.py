"""Langfuse 4.x (OTEL native) + LangSmith 통합 — PRD §7.5.11 + §10 DoD #17 (b).

v2 — 근본 재정비:
- Langfuse 4.x OTEL native: ``Langfuse().start_as_current_observation(...)`` context
  manager 로 turn 단위 span. CallbackHandler 경로 폐기 (langchain 의존 제거).
- ContextVar 기반 ``CostTracker`` 와 결합: turn lifecycle = (tracker reset + span
  enter) → (tracker finalize + span update + flush).
- ``describe_backend()`` 가 ``auth_check()`` 실측 진단 — 거짓 양성 제거.
- ``get_trace_callbacks()`` 는 하위 호환 alias (빈 리스트 반환).

호출 패턴 (run_agent / run_agent_stream 진입):
    from autonexusgraph.agents.tracing import start_turn_context

    with start_turn_context(thread_id="t1", state=init_state) as turn:
        result = app.invoke(init_state, config=...)
        turn.state = result        # final state 동기화 — n_replans/answer push 용
    # __exit__ 시:
    #   1. CostTracker.finalize(n_replans=result["n_replans"]) → PG ops.llm_usage 갱신
    #   2. Langfuse span.update(metadata={cost,tokens,n_replans,status}) + flush
"""

from __future__ import annotations

import contextlib
import logging
import os
import uuid
from dataclasses import dataclass, field
from typing import Any, Iterator

from ..llm.cost_tracker import (
    BudgetExceeded,
    CostTracker,
    current_tracker,
    set_current_tracker,
)
from .hop_metrics import trace_hop_summary

logger = logging.getLogger(__name__)

# ─── 백엔드 결정 ────────────────────────────────────────────────
# backend 자체는 매번 env/config 재해석 (저렴) — client/auth 만 캐시.
_LANGFUSE_CLIENT_CACHE: Any | None = None
_AUTH_CACHE: bool | None = None


def _resolve_backend() -> str:
    """env > config > 빈값. 결과: 'langfuse' | 'langsmith' | ''."""
    raw = os.getenv("TRACE_BACKEND")
    if raw is None or raw == "":
        try:
            from ..config import get_settings
            raw = get_settings().trace_backend or ""
        except Exception:   # noqa: BLE001
            raw = ""
    raw = (raw or "").strip().lower()
    if raw in ("none", "off"):
        return ""
    return raw


def reset_cache() -> None:
    """테스트에서 backend env 바꾼 뒤 캐시 무효화."""
    global _LANGFUSE_CLIENT_CACHE, _AUTH_CACHE
    _LANGFUSE_CLIENT_CACHE = None
    _AUTH_CACHE = None


# ─── Langfuse 4.x 클라이언트 (OTEL native) ───────────────────────
def _get_langfuse_client() -> Any | None:
    """Langfuse 4.x client — backend=langfuse + 키 + SDK 모두 충족 시 활성.

    실패 (SDK 없음 / 키 없음 / auth 실패) 시 None — fail-soft.
    캐시. ``reset_cache()`` 로 무효화.
    """
    global _LANGFUSE_CLIENT_CACHE, _AUTH_CACHE
    backend = _resolve_backend()
    if backend != "langfuse":
        return None
    if _LANGFUSE_CLIENT_CACHE is not None:
        return _LANGFUSE_CLIENT_CACHE if _AUTH_CACHE else None

    pub = os.getenv("LANGFUSE_PUBLIC_KEY")
    sec = os.getenv("LANGFUSE_SECRET_KEY")
    if not (pub and sec):
        logger.debug("LANGFUSE_PUBLIC_KEY/SECRET_KEY 미설정 — langfuse 비활성")
        return None
    try:
        from langfuse import Langfuse   # type: ignore[import-not-found]
    except ImportError:
        logger.debug("langfuse SDK 미설치 — 비활성")
        return None

    host = os.getenv("LANGFUSE_HOST") or None
    try:
        kwargs: dict = {"public_key": pub, "secret_key": sec}
        if host:
            kwargs["host"] = host
        client = Langfuse(**kwargs)
    except Exception as exc:   # noqa: BLE001
        logger.warning("Langfuse 클라이언트 초기화 실패 (skip): %s", exc)
        return None

    # 실측 진단 — auth_check 실패 시 비활성 처리.
    try:
        auth_ok = bool(client.auth_check())
    except Exception as exc:   # noqa: BLE001
        logger.warning("Langfuse auth_check 실패 (skip): %s", exc)
        auth_ok = False

    _LANGFUSE_CLIENT_CACHE = client
    _AUTH_CACHE = auth_ok
    return client if auth_ok else None


def describe_backend() -> str:
    """헬스체크용 — 현 환경의 tracing 활성 여부 + 백엔드 + 실측 auth 결과."""
    backend = _resolve_backend()
    if not backend:
        return "tracing: OFF (TRACE_BACKEND 비어 있음)"
    if backend == "langfuse":
        host = os.getenv("LANGFUSE_HOST") or "cloud.langfuse.com"
        if not (os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY")):
            return f"tracing: langfuse host={host} keys=MISSING (비활성)"
        client = _get_langfuse_client()
        if client is None:
            # SDK 미설치 또는 auth 실패. _get_langfuse_client 내부 로그 참조.
            return f"tracing: langfuse host={host} keys=set auth=FAIL (비활성)"
        return f"tracing: langfuse host={host} keys=set auth=OK (활성)"
    if backend == "langsmith":
        key = "set" if os.getenv("LANGSMITH_API_KEY") else "MISSING"
        proj = os.getenv("LANGSMITH_PROJECT") or "autonexusgraph"
        # langchain 미설치 환경에서는 LangSmith 자동 송신도 작동 안 함.
        try:
            import langchain   # noqa: F401
            extra = ""
        except ImportError:
            extra = " langchain=MISSING (자동 송신 비활성)"
        return f"tracing: langsmith project={proj} key={key}{extra}"
    return f"tracing: unknown backend '{backend}'"


# ─── 도메인 trace 태그 / metadata ─────────────────────────────────
def tags_for_domain(domain: str | None) -> list[str]:
    """Langfuse/LangSmith UI 필터링용 태그."""
    d = (domain or "").strip().lower() or "finance"
    base = ["autonexusgraph", f"domain:{d}"]
    if d in ("auto", "cross_domain"):
        base.append("autograph")
    if d in ("ip", "cross_domain"):
        base.append("ipgraph")
    return base


def metadata_for_state(state: dict) -> dict:
    """turn START 시점 metadata — 비-PII 식별자 / 카운트."""
    if not isinstance(state, dict):
        return {"domain": "finance"}
    domain = str(state.get("domain") or "finance").lower()
    md: dict = {
        "domain": domain,
        "n_target_companies": len(state.get("target_companies") or []),
        "n_target_vehicles":  len(state.get("target_vehicles") or []),
        "n_target_models":    len(state.get("target_models") or []),
        "n_history":          len(state.get("history") or []),
    }
    if state.get("question_kind"):
        md["question_kind"] = state["question_kind"]
    return md


# ─── Turn lifecycle (핵심 진입점) ─────────────────────────────────
@dataclass
class TurnContext:
    """start_turn_context 가 yield 하는 객체.

    호출자는 ``turn.state = final_state`` 로 마무리 state 를 동기화한다 — finalize
    시 ``n_replans`` 와 ``answer`` 가 PG meta + Langfuse span 으로 흐른다.
    """
    tracker: CostTracker
    turn_id: str
    thread_id: str
    state: dict = field(default_factory=dict)


@contextlib.contextmanager
def start_turn_context(thread_id: str, state: dict, *,
                       caller: str = "agent_chat") -> Iterator[TurnContext]:
    """Turn 단위 lifecycle context manager — PRD §10 DoD #17 (b) 핵심.

    enter:
      1. ContextVar 격리된 새 CostTracker (thread_id, turn_id, domain 식별자 보유)
      2. Langfuse 활성 시 ``start_as_current_observation`` span enter +
         trace tags/metadata 부착
    exit:
      1. tracker.finalize(status, n_replans=turn.state["n_replans"]) →
         ops.llm_usage row 의 meta JSONB 갱신
      2. Langfuse span.update(metadata={cost,tokens,n_replans,status}) + flush

    BudgetExceeded 는 'aborted_budget', 그 외 예외는 'error', 정상은 'ok' 로 finalize.
    Langfuse 측 모든 호출은 fail-soft — SDK/auth/네트워크 실패가 turn 자체를 깨지 않음.
    """
    turn_id = str(uuid.uuid4())
    domain = state.get("domain") if isinstance(state, dict) else None

    # 1. CostTracker (ContextVar 격리)
    # per-turn 한도 = 도메인별 turn budget(agent_turn_budget_*_usd, 기본 0.20).
    # 명시 전달해야 노드의 budget_aware_client(hard_limit=...) 와 일치한다.
    # (과거: hard_limit 미전달 → 5.00 기본값 적용 → turn budget 무력화 버그)
    from ..config import turn_budget_for_domain
    tracker = CostTracker(
        caller=caller, model="mixed",
        hard_limit=turn_budget_for_domain(domain),
        thread_id=thread_id, turn_id=turn_id, domain=domain,
    )
    set_current_tracker(tracker)

    # 2. Langfuse span (활성 시) — context manager
    client = _get_langfuse_client()
    span_cm: Any = None
    if client is not None:
        try:
            # turn START metadata — domain/n_target_* + turn_id/thread_id 모두 포함.
            # A3 (P0+ #1 결함 fix): turn_id 가 metadata 에 들어가야 PG/Langfuse 식별자 연결.
            start_meta = {**metadata_for_state(state),
                          "turn_id": turn_id, "thread_id": thread_id}
            span_cm = client.start_as_current_observation(
                as_type="span",
                name="agent.turn",
                input={
                    "question": (state.get("question") or "")[:500] if isinstance(state, dict) else "",
                    "thread_id": thread_id,
                    "turn_id": turn_id,
                },
                metadata=start_meta,
            )
            span_cm.__enter__()
            # trace 레벨 태그 — Langfuse UI 검색 필터용
            try:
                client.update_current_trace(
                    tags=tags_for_domain(domain),
                    metadata={"thread_id": thread_id, "turn_id": turn_id,
                              "domain": domain or "finance"},
                )
            except AttributeError as exc:
                # 4.x 일부 마이너 버전이 update_current_trace 미노출 — fail-soft.
                logger.debug("Langfuse update_current_trace 미노출 (skip): %s", exc)
        except Exception as exc:   # noqa: BLE001
            logger.warning("Langfuse span 시작 실패 (fail-soft): %s", exc)
            span_cm = None

    turn = TurnContext(tracker=tracker, turn_id=turn_id, thread_id=thread_id,
                       state=state if isinstance(state, dict) else {})
    status = "ok"
    try:
        yield turn
    except BudgetExceeded:
        status = "aborted_budget"
        raise
    except Exception:
        status = "error"
        raise
    finally:
        # 1. tracker finalize — PG ops.llm_usage 의 meta JSONB 에 thread_id/turn_id/
        #    n_replans/domain + 총합 영구 적재.
        try:
            n_replans = int(turn.state.get("n_replans") or 0)
        except Exception:   # noqa: BLE001
            n_replans = 0
        question_kind = turn.state.get("question_kind") if isinstance(turn.state, dict) else None
        extra: dict = {}
        if question_kind:
            extra["question_kind"] = question_kind
        # E-3 (DoD §10.13): per-turn cypher hop 수 + tool 호출 sequence 기록.
        try:
            hop = trace_hop_summary(turn.state)
            extra["hop_count"] = hop["hop_count"]
            extra["max_hop_depth"] = hop["max_hop_depth"]
            extra["tool_sequence"] = hop["tool_sequence"]
        except Exception as exc:   # noqa: BLE001
            logger.debug("hop_metrics 계산 실패 (skip): %s", exc)
            hop = None
        try:
            tracker.finalize(status, n_replans=n_replans,
                             extra_meta=extra or None)
        except Exception as exc:   # noqa: BLE001
            logger.warning("tracker.finalize 실패 (fail-soft): %s", exc)

        # 2. Langfuse span update + flush
        # A2 (P0+ #1 결함 fix): turn END 시점에 turn 의 최종 question_kind 도 포함
        # (triage_node 이후 채워짐 — START 시점에는 없음).
        if client is not None and span_cm is not None:
            end_meta: dict = {
                "n_replans":     n_replans,
                "n_calls":       tracker.state.n_calls,
                "input_tokens":  tracker.state.input_tokens,
                "output_tokens": tracker.state.output_tokens,
                "cost_usd":      float(tracker.state.cost_usd),
                "status":        status,
                "turn_id":       tracker.state.turn_id,
                "thread_id":     tracker.state.thread_id,
            }
            if question_kind:
                end_meta["question_kind"] = question_kind
            if hop is not None:
                end_meta["hop_count"] = hop["hop_count"]
                end_meta["max_hop_depth"] = hop["max_hop_depth"]
                end_meta["tool_sequence"] = hop["tool_sequence"]
            try:
                client.update_current_span(
                    metadata=end_meta,
                    output={"answer": (turn.state.get("answer") or "")[:1000]
                                       if isinstance(turn.state, dict) else None},
                )
            except Exception as exc:   # noqa: BLE001
                logger.warning("Langfuse span update 실패 (fail-soft): %s", exc)
            try:
                span_cm.__exit__(None, None, None)
            except Exception as exc:   # noqa: BLE001
                logger.debug("Langfuse span exit 실패: %s", exc)
            try:
                client.flush()
            except Exception as exc:   # noqa: BLE001
                logger.debug("Langfuse flush 실패: %s", exc)

        # 3. ctx 정리 — 다음 turn 이 새 tracker 받게.
        set_current_tracker(None)


# ─── 하위 호환 — get_trace_callbacks (deprecated) ─────────────────
def get_trace_callbacks() -> list[Any]:
    """[DEPRECATED] Langfuse 4.x 는 OTEL native — callback 불필요. 빈 리스트 반환.

    LangSmith 는 ``LANGCHAIN_TRACING_V2=true`` env 로 langchain 이 자동 송신 →
    callback 불필요. backend=langsmith 일 때만 env 보강.
    """
    backend = _resolve_backend()
    if backend == "langsmith":
        _enable_langsmith_env()
    return []


def _enable_langsmith_env() -> None:
    """LangSmith 자동 트레이스 — 환경변수 보강. langchain 미설치 시 효과 없음."""
    if not os.getenv("LANGSMITH_API_KEY"):
        logger.debug("LANGSMITH_API_KEY 미설정 — tracing 신호 안 보내질 수 있음")
        return
    os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
    os.environ.setdefault("LANGCHAIN_API_KEY", os.getenv("LANGSMITH_API_KEY", ""))
    proj = os.getenv("LANGSMITH_PROJECT")
    if proj:
        os.environ.setdefault("LANGCHAIN_PROJECT", proj)


# ─── 진단 ─────────────────────────────────────────────────────────
def current_turn_summary() -> dict:
    """진단·테스트용 — 현재 ctx 의 tracker 요약. tracker 없으면 빈 dict."""
    t = current_tracker()
    if t is None:
        return {}
    return {
        "thread_id":     t.state.thread_id,
        "turn_id":       t.state.turn_id,
        "n_calls":       t.state.n_calls,
        "input_tokens":  t.state.input_tokens,
        "output_tokens": t.state.output_tokens,
        "cost_usd":      float(t.state.cost_usd),
        "n_replans":     t.state.n_replans,
        "finalized":     t.state.finalized,
    }


__all__ = [
    # 핵심
    "start_turn_context",
    "TurnContext",
    "describe_backend",
    "reset_cache",
    # 메타
    "tags_for_domain",
    "metadata_for_state",
    # 진단
    "current_turn_summary",
    # 하위 호환
    "get_trace_callbacks",
]

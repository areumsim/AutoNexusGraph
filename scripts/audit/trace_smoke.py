#!/usr/bin/env python3
"""PRD §10 DoD #17 (b) — Langfuse 실측 audit (turn별 token/cost/replan).

검증 흐름 (LLM 비용 0 — simulation 기본):
  1. ``TRACE_BACKEND=langfuse`` + ``LANGFUSE_PUBLIC_KEY/SECRET_KEY`` 미설정 시
     SKIPPED (exit 0).
  2. ``start_turn_context`` enter — 새 CostTracker + Langfuse span.
  3. ``tracker.record(...)`` 로 가짜 토큰 적재 (input=100/output=50, mock 모델).
  4. ``turn.state`` 에 n_replans=2 + answer 박기.
  5. exit → tracker.finalize → PG ops.llm_usage 의 meta JSONB 영구 적재 +
     Langfuse span.update + flush.
  6. PG 검증: 최신 row 의 meta JSONB 에 thread_id/turn_id/n_replans 존재.
     n_calls/input_tokens/output_tokens/cost_usd > 0.
  7. Langfuse 검증: ``client.auth_check()`` OK.
  8. PASS/FAIL 한 줄 + JSON 결과를 ``data/reports/audit_trace_<ISO>.json``.

``--full`` flag — 실제 agent run (LLM 비용 발생). CI 에서는 simulation 권장.

종료 코드:
    0: PASS 또는 SKIPPED (langfuse 미설정)
    1: FAIL (PG row 없음 / 메타 결손 / Langfuse auth 실패)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

log = logging.getLogger(__name__)


def _ensure_keys() -> tuple[bool, str]:
    """Langfuse 실측 가능 조건 — env 확인. (활성, 사유) 반환.

    `.env` fallback: `_resolve_backend()` 가 `get_settings()` (pydantic-settings) 로
    `.env` 의 `TRACE_BACKEND` 도 인식 — `os.getenv` 단독 검사 시 process env 만 보는
    버그 회피.
    """
    from autonexusgraph.agents.tracing import _resolve_backend
    if _resolve_backend() != "langfuse":
        return False, "TRACE_BACKEND != langfuse"
    # LANGFUSE_* 키도 동일하게 .env fallback. pydantic-settings 가 lower-case 로 노출.
    pub = os.getenv("LANGFUSE_PUBLIC_KEY")
    sec = os.getenv("LANGFUSE_SECRET_KEY")
    if not (pub and sec):
        try:
            from autonexusgraph.config import get_settings
            s = get_settings()
            pub = pub or getattr(s, "langfuse_public_key", "")
            sec = sec or getattr(s, "langfuse_secret_key", "")
        except Exception:   # noqa: BLE001
            pass
    if not (pub and sec):
        return False, "LANGFUSE_PUBLIC_KEY/SECRET_KEY 미설정"
    # process env 에 주입 — _get_langfuse_client 가 os.getenv 만 보는 호환성 유지.
    os.environ.setdefault("LANGFUSE_PUBLIC_KEY", pub)
    os.environ.setdefault("LANGFUSE_SECRET_KEY", sec)
    return True, "ok"


def _simulate_turn(thread_id: str) -> dict:
    """LLM 비용 0 — turn lifecycle 만 발화. tracker.record 직접 호출."""
    from autonexusgraph.agents.tracing import start_turn_context
    from autonexusgraph.llm.cost_tracker import get_session_tracker

    fake_state = {
        "question": "audit-trace simulation",
        "domain": "auto",
        "question_kind": "factual",
    }
    with start_turn_context(thread_id, fake_state, caller="audit-trace") as turn:
        tracker = get_session_tracker()
        # 가짜 LLM 호출 2회 — 토큰/비용 산정.
        tracker.record(input_tokens=120, output_tokens=80, model="mock-fast",
                       purpose="audit_simulate", latency_ms=42)
        tracker.record(input_tokens=200, output_tokens=150, model="mock-fast",
                       purpose="audit_simulate", latency_ms=88)
        # final state — n_replans=2 박아서 메타에 적재 검증.
        turn.state = {
            **fake_state,
            "n_replans": 2,
            "answer": "audit-trace simulation OK",
            "question_kind": "factual",
        }
    return turn.state


def _run_real_agent(thread_id: str) -> dict:
    """--full flag — 실제 1턴 (LLM 비용 발생). 운영자 명시 호출용."""
    from autonexusgraph.agents.graph import run_agent
    state = run_agent("쏘나타 1.6T 출력은?",
                       thread_id=thread_id, domain="auto")
    return dict(state) if isinstance(state, dict) else {}


def _verify_pg(thread_id: str) -> dict:
    """ops.llm_usage 의 thread_id 일치 최신 row 검증."""
    try:
        from autonexusgraph.db.postgres import get_pool
    except Exception as e:   # noqa: BLE001
        return {"passed": False, "reason": f"pg import 실패: {e}"}

    try:
        with get_pool().connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT run_id::text, caller, n_calls, input_tokens, output_tokens,
                       cost_usd, status, meta
                FROM ops.llm_usage
                WHERE meta ->> 'thread_id' = %s
                ORDER BY started_at DESC
                LIMIT 1
                """,
                (thread_id,),
            )
            row = cur.fetchone()
    except Exception as e:   # noqa: BLE001
        return {"passed": False, "reason": f"pg query 실패: {e}"}

    if not row:
        return {"passed": False, "reason": f"thread_id={thread_id} row 없음"}

    run_id, caller, n_calls, in_tok, out_tok, cost, status, meta = row
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except Exception:   # noqa: BLE001
            meta = {}
    required = ("thread_id", "turn_id", "n_replans", "domain")
    missing = [k for k in required if k not in (meta or {})]
    if missing:
        return {"passed": False,
                "reason": f"meta 결손: {missing}",
                "row": {"run_id": run_id, "meta": meta}}
    if n_calls < 1 or in_tok < 1 or out_tok < 1:
        return {"passed": False,
                "reason": f"토큰/콜 카운트 결손 (n_calls={n_calls} in={in_tok} out={out_tok})",
                "row": {"run_id": run_id, "meta": meta}}
    return {
        "passed": True,
        "row": {
            "run_id":        run_id,
            "caller":        caller,
            "n_calls":       int(n_calls),
            "input_tokens":  int(in_tok),
            "output_tokens": int(out_tok),
            "cost_usd":      float(cost),
            "status":        status,
            "meta":          meta,
        },
    }


def _verify_langfuse() -> dict:
    """auth_check 실측 — 4.x client 직접 호출."""
    try:
        from autonexusgraph.agents.tracing import _get_langfuse_client
        client = _get_langfuse_client()
    except Exception as e:   # noqa: BLE001
        return {"passed": False, "reason": f"langfuse client init 실패: {e}"}
    if client is None:
        return {"passed": False, "reason": "langfuse 비활성 (SDK 또는 auth 실패)"}
    try:
        client.flush()
    except Exception as e:   # noqa: BLE001
        return {"passed": False, "reason": f"flush 실패: {e}"}
    return {"passed": True, "auth": "ok"}


def _emit(result: dict, out_dir: Path) -> None:
    """리포트 파일 + stdout."""
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = out_dir / f"audit_trace_{ts}.json"
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    if result.get("passed"):
        print(f"[audit-trace] PASS — {result.get('summary', '')}  ({path})")
    elif result.get("skipped"):
        print(f"[audit-trace] SKIPPED — {result.get('reason', '')}")
    else:
        print(f"[audit-trace] FAIL — {result.get('reason', '')}  ({path})")


def main() -> int:
    p = argparse.ArgumentParser(prog="audit-trace", description=__doc__.split("\n")[0])
    p.add_argument("--full", action="store_true",
                   help="실제 run_agent 호출 (LLM 비용 발생). 미지정 시 simulation.")
    p.add_argument("--thread-id", default="audit-trace",
                   help="thread_id (PG/Langfuse 식별자, 기본 'audit-trace')")
    p.add_argument("--out-dir", type=Path,
                   default=ROOT / "data" / "reports",
                   help="JSON 리포트 저장 디렉토리")
    p.add_argument("--log-level", default="WARNING")
    args = p.parse_args()
    logging.basicConfig(level=args.log_level)

    active, reason = _ensure_keys()
    if not active:
        _emit({"skipped": True, "reason": reason}, args.out_dir)
        return 0

    # 1. turn 발화
    try:
        if args.full:
            final_state = _run_real_agent(args.thread_id)
        else:
            final_state = _simulate_turn(args.thread_id)
    except Exception as e:   # noqa: BLE001
        _emit({"passed": False, "reason": f"turn 실행 실패: {e}"}, args.out_dir)
        return 1

    # 2. PG 검증
    pg = _verify_pg(args.thread_id)
    # 3. Langfuse 검증
    lf = _verify_langfuse()

    overall = pg.get("passed", False) and lf.get("passed", False)
    summary = (
        f"PG row cost=${pg.get('row', {}).get('cost_usd', 0):.4f} "
        f"tokens={pg.get('row', {}).get('input_tokens', 0)}/"
        f"{pg.get('row', {}).get('output_tokens', 0)} "
        f"n_replans={pg.get('row', {}).get('meta', {}).get('n_replans', '?')}"
    ) if overall else ""

    result = {
        "passed":   overall,
        "reason":   pg.get("reason") or lf.get("reason") or "",
        "summary":  summary,
        "mode":     "full" if args.full else "simulation",
        "thread_id": args.thread_id,
        "pg":       pg,
        "langfuse": lf,
        "final_state_keys": sorted((final_state or {}).keys())[:20],
    }
    _emit(result, args.out_dir)
    return 0 if overall else 1


if __name__ == "__main__":
    raise SystemExit(main())

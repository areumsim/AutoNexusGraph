"""모든 LLM 호출의 영속 JSONL 로그 — 누계 추적의 SSOT.

설계 원칙 (사용자 명시: "누락되는 부분 없게"):
- **append-only**: 동시 호출에도 안전. 파일은 덮어쓰지 않음.
- **best-effort**: 파일 쓰기 실패가 LLM 호출 자체를 절대 막지 않음.
- **세션 무관**: 프로세스 재시작/종료 후에도 누계 보존 → 며칠 단위 추적 가능.
- **DB 의존성 없음**: PG anxg_ops.llm_usage 가 다운돼도 로컬 파일은 항상 기록.

스키마 (각 줄 1 JSON object):
    {
      "ts": "2026-05-29T18:30:00.123456+00:00",  # ISO UTC
      "run_id": "uuid",          # CostTracker.state.run_id
      "caller": "agent_synth",   # 어디서 호출됐는지
      "model": "gpt-4o-mini",
      "provider": "openai",      # 모델명으로 자동 감지
      "input_tokens": 1234,
      "output_tokens": 567,
      "cost_usd": 0.000534,
      "purpose": "synthesize",   # optional — 노드별 의미
      "latency_ms": 1842,        # optional
    }

CostTracker.record() 가 호출당 1회 본 모듈의 append() 를 부른다.

CLI 조회: ``python -m autonexusgraph.llm.cost_history``
"""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


log = logging.getLogger(__name__)

# POSIX O_APPEND 가 64KB 미만 쓰기를 원자 보장하지만, 안전 위해 프로세스 내 Lock 도.
_lock = threading.Lock()


def _detect_provider(model: str) -> str:
    """모델명 → provider (cost_history 집계 보조). llm/base.detect_provider 와 동일."""
    try:
        from .base import detect_provider
        return detect_provider(model)
    except Exception:   # noqa: BLE001 — 호출 실패 흡수 → "?" 반환
        return "?"


def append(entry: dict[str, Any]) -> None:
    """단일 LLM 호출 entry 를 cost_log.jsonl 에 추가.

    Args:
        entry: 최소 ``{caller, model, input_tokens, output_tokens, cost_usd}``.
               나머지 (purpose, latency_ms, run_id) 는 선택. ``ts`` 와 ``provider``
               는 본 함수가 자동 보강.
    """
    try:
        from ..config import get_settings
        path = Path(get_settings().llm_cost_log_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        full = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "provider": _detect_provider(str(entry.get("model", ""))),
            **entry,
        }
        line = json.dumps(full, ensure_ascii=False, default=str)
        with _lock:
            with path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
    except Exception as exc:   # noqa: BLE001 — 예외 흡수 → log + 다음 단계 (silent 아님)
        # LLM 호출 흐름을 막지 않기 위해 silent.
        log.debug("[cost_log] append failed: %s", exc)


def iter_entries(path: Path | None = None) -> Iterator[dict[str, Any]]:
    """JSONL → dict iterator. 잘못된 라인은 silent skip."""
    if path is None:
        from ..config import get_settings
        path = Path(get_settings().llm_cost_log_path)
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def _parse_ts(ts_str: str) -> datetime | None:
    """ISO ts → datetime (tz-aware). 파싱 실패 시 None."""
    if not ts_str:
        return None
    try:
        return datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def total_cost(path: Path | None = None, *, since: datetime | None = None) -> float:
    """누적 비용 USD. ``since`` 지정 시 그 시각 이후 entry 만 합산 (rolling window).

    ts 없는/파싱 실패 entry 는 since 필터 시 보수적으로 제외.
    """
    tot = 0.0
    for e in iter_entries(path):
        if since is not None:
            ts = _parse_ts(str(e.get("ts", "")))
            if ts is None or ts < since:
                continue
        tot += float(e.get("cost_usd", 0.0) or 0.0)
    return tot


class LoggingLLMClient:
    """Auto-log wrapper — 모든 chat/stream/json 호출을 cost_log.jsonl 에 append.

    ``get_llm_client()`` 가 반환하는 모든 client 는 본 wrapper 로 감싸진다.
    이로써:
    - **모든 provider** (OpenAI/Anthropic/Google/Local) 누락 없이 기록
    - **모든 호출 메서드** (chat / chat_stream / chat_json)
    - **budget_aware wrap 여부 무관** — wrap 안 해도 항상 기록
    - **raw client** 사용해도 기록 (budget_aware 미적용 시에도)

    provider 가 usage_metadata 를 노출하면 정확값, 안 하면 char/3 보수적 추정.
    추정 시 entry["estimated"]=True 로 표시.
    """

    def __init__(self, inner, *, caller: str = "anon") -> None:
        self._inner = inner
        # model 은 inner 에서 그대로 — set_caller 후 chat 직전 모델 일치.
        self.model = inner.model
        self._caller = caller

    def __getattr__(self, name: str):
        """알려지지 않은 속성 접근 시 inner 로 위임 (_last_usage 등)."""
        return getattr(self._inner, name)

    def set_caller(self, caller: str) -> None:
        """호출자 (role/노드 이름 등) 갱신 — 동일 client 재사용 시 caller 만 바꿈."""
        self._caller = caller

    # ── chat ──────────────────────────────────────────────────
    def chat(self, messages, *, temperature: float = 0.0,
             max_tokens: int | None = None, purpose: str | None = None,
             **kw):
        import time
        t0 = time.monotonic()
        resp = self._inner.chat(
            messages, temperature=temperature, max_tokens=max_tokens, **kw,
        )
        latency_ms = int((time.monotonic() - t0) * 1000)
        u = resp.usage
        append({
            "caller":         self._caller,
            "model":          u.model or self.model,
            "input_tokens":   int(u.prompt_tokens or 0),
            "output_tokens":  int(u.completion_tokens or 0),
            "cost_usd":       float(u.cost_usd or 0.0),
            "purpose":        purpose,
            "latency_ms":     latency_ms,
            "method":         "chat",
        })
        return resp

    # ── chat_stream ───────────────────────────────────────────
    def chat_stream(self, messages, *, temperature: float = 0.0,
                    max_tokens: int | None = None,
                    purpose: str | None = None, **kw):
        import time
        from .cost import cost_of_call
        t0 = time.monotonic()
        chunks: list[str] = []
        try:
            for c in self._inner.chat_stream(
                messages, temperature=temperature,
                max_tokens=max_tokens, **kw,
            ):
                chunks.append(c)
                yield c
        finally:
            # stream 종료 (또는 중단) 시점에 한 번 기록 — provider 가 usage 를
            # 노출 안 하는 경우가 많아 char/3 보수적 추정 사용.
            latency_ms = int((time.monotonic() - t0) * 1000)
            in_est = sum(len(m.get("content", "") or "") for m in messages) // 3
            out_est = sum(len(c) for c in chunks) // 3
            cost = cost_of_call(self.model, in_est, out_est)
            append({
                "caller":        self._caller,
                "model":         self.model,
                "input_tokens":  in_est,
                "output_tokens": out_est,
                "cost_usd":      cost,
                "purpose":       purpose,
                "latency_ms":    latency_ms,
                "method":        "chat_stream",
                "estimated":     True,
            })

    # ── chat_json ─────────────────────────────────────────────
    def chat_json(self, messages, schema, *, temperature: float = 0.0,
                  purpose: str | None = None, **kw):
        import time
        from .cost import cost_of_call
        t0 = time.monotonic()
        result = self._inner.chat_json(
            messages, schema, temperature=temperature, **kw,
        )
        latency_ms = int((time.monotonic() - t0) * 1000)

        # provider 가 _last_usage 노출하면 정확값.
        usage = getattr(self._inner, "_last_usage", None)
        if usage is not None:
            entry = {
                "caller":        self._caller,
                "model":         usage.model or self.model,
                "input_tokens":  int(usage.prompt_tokens or 0),
                "output_tokens": int(usage.completion_tokens or 0),
                "cost_usd":      float(usage.cost_usd or 0.0),
                "purpose":       purpose,
                "latency_ms":    latency_ms,
                "method":        "chat_json",
            }
        else:
            # 추정 fallback — input 은 messages 합, output 은 결과 json 길이.
            import json as _json
            in_est = sum(len(m.get("content", "") or "") for m in messages) // 3
            out_est = len(_json.dumps(result, ensure_ascii=False)) // 3
            cost = cost_of_call(self.model, in_est, out_est)
            entry = {
                "caller":        self._caller,
                "model":         self.model,
                "input_tokens":  in_est,
                "output_tokens": out_est,
                "cost_usd":      cost,
                "purpose":       purpose,
                "latency_ms":    latency_ms,
                "method":        "chat_json",
                "estimated":     True,
            }
        append(entry)
        return result


__all__ = ["append", "iter_entries", "total_cost", "LoggingLLMClient"]

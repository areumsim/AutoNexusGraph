"""Hybrid 어댑터 — AutoNexusGraph 의 본 agent (Triage/Planner/Executor/Synthesizer).

PRD §2.2 의 목표: vector-only 대비 multi-hop +30%p 우위 입증.
"""

from __future__ import annotations

import time

from .base import AgentAdapter, AgentResponse, Evidence


class HybridAdapter(AgentAdapter):
    name = "hybrid"
    version = "0.1"

    def query(self, question: str, *,
              domain: str | None = None) -> AgentResponse:
        from autonexusgraph.agents import run_agent

        t0 = time.monotonic()
        try:
            state = run_agent(question, domain=domain)
        except Exception as e:
            return AgentResponse(
                refused=True, refusal_reason=f"agent_failed:{e}",
                latency_sec=time.monotonic() - t0,
            )

        evidence = [
            Evidence(
                rank=i + 1, chunk_id=c.get("chunk_id", 0),
                corp_code=c.get("corp_code", "") or "",
                rcept_no=c.get("rcept_no", "") or "",
                section=c.get("section", "") or "",
                fiscal_year=c.get("fiscal_year"),
                source="",
                evidence_text="",
                score=float(c.get("score") or 0.0),
            )
            for i, c in enumerate(state.get("citations") or [])
        ]

        synth_status = state.get("synth_status") or {}
        # synth 가 LLM 호출 0 으로 fallback 되면 refused 가 아니더라도 명시적으로
        # 표시 → eval 리포트가 cost=$0 의 원인을 즉시 알 수 있다.
        diagnostics = {
            "targets": state.get("target_companies") or [],
            "target_vehicles": state.get("target_vehicles") or [],
            "target_models": state.get("target_models") or [],
            "domain": state.get("domain") or "",
            "n_tool_results": len(state.get("tool_results") or []),
            "synth_ok": bool(synth_status.get("ok")),
            "synth_llm_called": bool(synth_status.get("llm_called")),
            "synth_fallback_used": synth_status.get("fallback_used"),
            "synth_error_type": synth_status.get("error_type"),
            "synth_error": (synth_status.get("error") or "")[:200],
            "safety_signals": state.get("safety_signals") or [],
            "fallback_used": bool(state.get("fallback_used")),
        }
        return AgentResponse(
            answer=state.get("answer", ""),
            refused=bool(state.get("aborted_reason")),
            refusal_reason=state.get("aborted_reason") or "",
            evidence=evidence,
            question_kind=state.get("question_kind", ""),
            latency_sec=time.monotonic() - t0,
            cost_usd=float(state.get("llm_usage_usd") or 0.0),
            tokens_used=int(state.get("llm_tokens_used") or 0),
            diagnostics=diagnostics,
        )

"""Hybrid 어댑터 — AutoNexusGraph 의 본 agent (Triage/Planner/Executor/Synthesizer).

PRD §2.2 의 목표: vector-only 대비 multi-hop +30%p 우위 입증.
"""

from __future__ import annotations

import time
import uuid

from .base import AgentAdapter, AgentResponse, Evidence


class HybridAdapter(AgentAdapter):
    name = "hybrid"
    version = "0.1"

    def __init__(self, *, rerank: bool = True, llm_tier: str = "fast",
                 llm_planner: bool = False, source: str | None = None) -> None:
        """Hybrid 어댑터 — 본 프로젝트의 production agent (Triage/Planner/Executor/Synth).

        rerank 토글은 ``run_agent(rerank=...)`` 로 전달되어 research_worker 가
        ``search_documents(rerank=...)`` 까지 전파 (PRD §10 DoD #17 (d) ablation).
        → ``hybrid_fast_rerank0`` 셀이 ``hybrid_fast_rerank1`` 과 실제로 분리됨.

        llm_planner 토글(축2 ablation)은 ``run_agent(llm_planner=...)`` 로 전달 →
        룰 planner vs LLM 자율 planner 셀(``_planner1``)을 실제 분리 측정.

        source 필터는 ``run_agent(source=...)`` 로 전달되어 research_worker 가
        ``search_documents(source=...)`` 까지 전파 → 외부 벤치(Allganize 등)를 메인
        코퍼스 희석 없이 평가. vector 어댑터와 동일하게 생성자 인자 우선, 없으면 env
        ``EVAL_VECTOR_SOURCE`` (같은 eval 명령이 두 어댑터에 동일 source 를 적용).
        """
        super().__init__(rerank=rerank, llm_tier=llm_tier, llm_planner=llm_planner)
        import os
        self.source = source or os.getenv("EVAL_VECTOR_SOURCE") or None

    def query(self, question: str, *,
              domain: str | None = None) -> AgentResponse:
        from autonexusgraph.agents import run_agent

        t0 = time.monotonic()
        try:
            # 질문마다 고유 thread_id — LangGraph PG 체크포인트 공유로 인한 state
            # bleed 방지. (기본 thread_id="default" 면 모든 eval 질문이 한 스레드를
            # 공유 → 이전 질문의 target_companies/history 가 누수돼 엉뚱한 회사로 답함.)
            state = run_agent(question, domain=domain, rerank=self.rerank,
                              llm_planner=self.llm_planner, source=self.source,
                              thread_id=f"eval-{uuid.uuid4().hex}")
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

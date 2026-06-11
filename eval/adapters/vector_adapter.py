"""Vector-only 어댑터 — pgvector 본문 검색 + LLM 단순 합성.

비교 baseline. graph/hybrid 가 vector-only 대비 얼마나 우위인지 측정용.
"""

from __future__ import annotations

import time

from .base import AgentAdapter, AgentResponse, Evidence


class VectorAdapter(AgentAdapter):
    name = "vector"
    version = "0.1"

    def __init__(self, top_k: int = 8, *,
                 rerank: bool = True, llm_tier: str = "fast",
                 source: str | None = None) -> None:
        super().__init__(rerank=rerank, llm_tier=llm_tier)
        self.top_k = top_k
        # source 필터 — 별도 코퍼스(외부 벤치 등)를 메인 코퍼스 희석 없이 평가.
        # 생성자 인자 우선, 없으면 env EVAL_VECTOR_SOURCE.
        import os
        self.source = source or os.getenv("EVAL_VECTOR_SOURCE") or None

    def query(self, question: str, *, domain: str | None = None) -> AgentResponse:  # noqa: ARG002 — vector-only 는 도메인 무관.
        from autonexusgraph.tools.retrieve import search_documents
        from .base import synthesize

        t0 = time.monotonic()
        try:
            hits = search_documents(question, top_k=self.top_k, rerank=self.rerank,
                                    source=self.source)
        except Exception as e:
            return AgentResponse(
                refused=True, refusal_reason=f"retrieve_failed:{e}",
                latency_sec=time.monotonic() - t0,
            )

        if not hits:
            return AgentResponse(
                refused=True, refusal_reason="no_evidence",
                latency_sec=time.monotonic() - t0,
            )

        # 단순 합성 — LLM 한 번. cost_tracker 자동 통합.
        ctx = "\n\n".join(
            f"[corp={h.get('corp_code')} sec={h.get('section','')[:30]} "
            f"score={h.get('score', 0):.3f}]\n{h.get('text','')[:800]}"
            for h in hits[:5]
        )
        answer, cost, tokens, refused = synthesize(
            [
                {"role": "system", "content": "근거 본문만 인용해 한국어로 답하세요."},
                {"role": "user", "content": f"질문: {question}\n\n근거:\n{ctx}"},
            ],
            caller="eval_vector_synth", max_tokens=800,
        )

        return AgentResponse(
            answer=answer,
            refused=refused,
            refusal_reason="budget" if refused else "",
            evidence=[
                Evidence(
                    rank=i + 1, chunk_id=h.get("id", 0),
                    corp_code=h.get("corp_code", ""),
                    rcept_no=h.get("rcept_no", "") or "",
                    section=h.get("section", "") or "",
                    fiscal_year=h.get("fiscal_year"),
                    source=h.get("source", ""),
                    evidence_text=(h.get("text", "") or "")[:600],
                    score=float(h.get("score", 0.0)),
                )
                for i, h in enumerate(hits)
            ],
            latency_sec=time.monotonic() - t0,
            cost_usd=cost,
            tokens_used=tokens,
            question_kind="narrative",
        )

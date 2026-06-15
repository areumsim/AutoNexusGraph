"""Iterative(agentic) vector 어댑터 — multi-round 검색 + LLM 질의 재구성.

**목적**: 단발 vector(`VectorAdapter`, top_k 1회)는 multi-hop 답변 문서를 구조적으로
못 찾는다(외부타당성 V3: 정답 recall 5.8%). 본 어댑터는 **graph/SQL 없이** LLM 이 검색
결과를 보고 후속 sub-query 를 생성해 **여러 라운드 검색**하는 Self-Ask/IRCoT 류 baseline.
"vector RAG 가 할 수 있는 최선(ceiling)" 을 hybrid 와 공정 비교하기 위함 — hybrid 가 이
ceiling 도 이기면, 우위는 "검색량" 이 아니라 **그래프의 명시적 관계 구조**에서 온다.

설계(무결성):
- **vector 검색만** 사용 (`search_documents`). graph traverse / SQL / cypher 전혀 없음.
- LLM 은 (a) 후속 검색어 생성 (b) 종료 판단만 — 답을 지어내지 않게 합성은 마지막 1회.
- max_rounds 회 또는 LLM 이 'ready' 신호 시 종료. 누적 청크 전체로 최종 합성.
"""

from __future__ import annotations

import time

from .base import AgentAdapter, AgentResponse, Evidence

_MAX_ROUNDS = 3
_TOP_K = 8

_REFORMULATE_SCHEMA = {
    "type": "object",
    "properties": {
        "can_answer": {"type": "boolean"},
        "next_query": {"type": "string"},
    },
    "required": ["can_answer", "next_query"],
}
_REFORMULATE_SYS = (
    "당신은 multi-hop 질문을 푸는 검색 보조자다. 지금까지 검색된 근거만 보고, 원 질문에 "
    "**완전히** 답할 수 있으면 can_answer=true. 아직 중간 엔티티(예: 모회사 이름)나 다음 "
    "단서가 더 필요하면 can_answer=false 로 두고, **다음에 벡터 검색할 한국어 검색어** 한 "
    "줄을 next_query 에 적어라(직전과 다른, 더 구체적인 검색어). JSON 만."
)


class IterVectorAdapter(AgentAdapter):
    name = "iter_vector"
    version = "0.1"

    def __init__(self, top_k: int = _TOP_K, *,
                 rerank: bool = True, llm_tier: str = "fast",
                 max_rounds: int = _MAX_ROUNDS, source: str | None = None) -> None:
        super().__init__(rerank=rerank, llm_tier=llm_tier)
        self.top_k = top_k
        self.max_rounds = max_rounds
        import os
        self.source = source or os.getenv("EVAL_VECTOR_SOURCE") or None

    def _reformulate(self, question: str, ctx: str) -> tuple[bool, str, float, int]:
        """누적 근거를 보고 (종료?, 다음 검색어, cost, tokens) 결정 — vector 외 도구 0."""
        from autonexusgraph.llm.base import get_llm_client
        from autonexusgraph.llm.budget_aware import budget_aware_client
        from autonexusgraph.llm.cost_tracker import BudgetExceeded
        try:
            client = budget_aware_client(get_llm_client(role="planner"),
                                         caller="eval_itervec_reformulate")
            res = client.chat_json(
                [{"role": "system", "content": _REFORMULATE_SYS},
                 {"role": "user", "content": f"[원 질문]\n{question}\n\n[지금까지 근거]\n{ctx[:3000]}"}],
                _REFORMULATE_SCHEMA, temperature=0.0, purpose="itervec_reformulate",
            )
            can = bool(res.get("can_answer"))
            nq = str(res.get("next_query") or "").strip()
            # cost/tokens 는 cost_tracker 가 누적 — 여기선 0 으로 두고 합성 cost 만 보고.
            return can, nq, 0.0, 0
        except BudgetExceeded:
            return True, "", 0.0, 0
        except Exception:   # noqa: BLE001 — 재구성 실패 시 종료(누적 근거로 합성)
            return True, "", 0.0, 0

    def query(self, question: str, *, domain: str | None = None) -> AgentResponse:  # noqa: ARG002 — vector-only.
        from autonexusgraph.tools.retrieve import search_documents

        from .base import synthesize

        t0 = time.monotonic()
        all_hits: list[dict] = []
        seen_ids: set = set()
        queries: list[str] = []
        cur_q = question
        n_rounds = 0

        for _ in range(self.max_rounds):
            n_rounds += 1
            queries.append(cur_q)
            try:
                hits = search_documents(cur_q, top_k=self.top_k, rerank=self.rerank,
                                        source=self.source)
            except Exception:   # noqa: BLE001 — 라운드 검색 실패 → 누적분으로 진행
                hits = []
            for h in hits:
                hid = h.get("id")
                if hid not in seen_ids:
                    seen_ids.add(hid)
                    all_hits.append(h)
            # 누적 근거로 종료/재구성 판단 (마지막 라운드면 스킵).
            if n_rounds >= self.max_rounds:
                break
            ctx_so_far = "\n\n".join(f"{h.get('text','')[:500]}" for h in all_hits[:10])
            can, nq, _, _ = self._reformulate(question, ctx_so_far)
            if can or not nq or nq in queries:
                break
            cur_q = nq

        if not all_hits:
            return AgentResponse(
                refused=True, refusal_reason="no_evidence",
                latency_sec=time.monotonic() - t0, question_kind="narrative",
                diagnostics={"n_rounds": n_rounds, "queries": queries},
            )

        ctx = "\n\n".join(
            f"[corp={h.get('corp_code')} sec={h.get('section','')[:30]} "
            f"score={h.get('score', 0):.3f}]\n{h.get('text','')[:800]}"
            for h in all_hits[:8]
        )
        answer, cost, tokens, refused = synthesize(
            [
                {"role": "system", "content": "검색된 근거 본문만 근거로 한국어로 답하세요. "
                                              "여러 문서를 종합해 multi-hop 답을 도출하세요."},
                {"role": "user", "content": f"질문: {question}\n\n근거:\n{ctx}"},
            ],
            caller="eval_itervec_synth", max_tokens=800,
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
                for i, h in enumerate(all_hits)
            ],
            latency_sec=time.monotonic() - t0,
            cost_usd=cost,
            tokens_used=tokens,
            question_kind="narrative",
            diagnostics={"n_rounds": n_rounds, "queries": queries,
                         "n_chunks": len(all_hits)},
        )

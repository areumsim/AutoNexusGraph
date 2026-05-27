"""에이전트 StateGraph 상태 정의.

LangGraph 도입 시 그대로 StateGraph[AgentState] 로 사용 가능한 형태.
현재는 langgraph 미설치 → graph.py 가 단순 함수 체인으로 동작.
"""

from __future__ import annotations

from typing import Any, Literal, TypedDict


QuestionKind = Literal["factual", "narrative", "structural", "multi_hop", "unknown"]


class AgentState(TypedDict, total=False):
    """conversation 한 turn 의 누적 상태."""

    # 입력
    thread_id: str
    question: str
    history: list[dict]               # 이전 messages — multi-turn 컨텍스트

    # 전처리 (rewriter / temporal 결과)
    question_rewritten: str           # coreference 해소 + 시점 정규화된 query
    temporal_audit: dict              # {applied, year_from, year_to, reference_date}
    rewrite_audit: dict               # {called, reason, output}
    safety_signals: list[str]         # prompt injection 감지 토큰 (있으면 telemetry)

    # Triage / Planner 결정
    question_kind: QuestionKind
    target_companies: list[str]       # corp_code 목록 (lookup_company 결과)
    session_carryover: bool           # 이번 turn 의 target 이 이전 세션에서 borrow 됐는지
    plan: list[dict]                  # [{"tool": "list_subsidiaries", "args": {...}, "purpose": "..."}, ...]

    # 실행 결과
    tool_results: list[dict]          # 도구별 출력 묶음
    evidence_chunks: list[dict]       # search_documents 결과
    graph_subgraph: dict | None       # 시각화용
    fallback_used: bool               # 빈 결과 회복으로 fallback search_documents 호출됐는지

    # 합성
    answer: str
    citations: list[dict]             # [{"chunk_id": ..., "corp_code": ..., "section": ...}]
    visualizations: list[dict]        # [{"kind": "subgraph", ...}, {"kind": "chart", ...}]

    # Validation (PRD §7.5.5)
    validation_status: str            # 'pending' | 'passed' | 'failed'
    validation_issues: list[str]      # 검증 실패 사유들
    grounding: dict                   # verify_answer_grounding 결과

    # 메타·비용
    llm_usage_usd: float
    n_replans: int
    aborted_reason: str | None

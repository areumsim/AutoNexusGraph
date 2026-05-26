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

    # Triage / Planner 결정
    question_kind: QuestionKind
    target_companies: list[str]       # corp_code 목록 (lookup_company 결과)
    plan: list[dict]                  # [{"tool": "list_subsidiaries", "args": {...}, "purpose": "..."}, ...]

    # 실행 결과
    tool_results: list[dict]          # 도구별 출력 묶음
    evidence_chunks: list[dict]       # search_documents 결과
    graph_subgraph: dict | None       # 시각화용

    # 합성
    answer: str
    citations: list[dict]             # [{"chunk_id": ..., "corp_code": ..., "section": ...}]
    visualizations: list[dict]        # [{"kind": "subgraph", ...}, {"kind": "chart", ...}]

    # 메타·비용
    llm_usage_usd: float
    n_replans: int
    aborted_reason: str | None

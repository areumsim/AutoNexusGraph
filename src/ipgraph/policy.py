"""IPGraph 도메인 라우팅 + 룰 분류 + planner DAG.

autograph/policy.py 와 동일 인터페이스를 특허 도메인에 맞춰 제공.

- ``classify_question_ip(q)`` → IPQuestionKind
- ``select_tools_ip(kind)``    → 권장 intent 목록
- ``plan_ip_tasks(state)``     → planner_node 가 위임할 task DAG
- ``route_domain_ip(question, hint)`` → 'ip' 또는 None (다른 라우터에 양보)
"""

from __future__ import annotations

from typing import Literal

IPQuestionKind = Literal[
    "patent_lookup",       # 특정 특허 식별 (lookup_patent)
    "assignee_patents",    # assignee 의 특허 목록·집계
    "cpc_search",          # CPC 코드 기반 분야 탐색
    "citation_network",    # 인용 네트워크
    "patent_compare",      # assignee 간 출원량 비교
    "patent_narrative",    # 자유 텍스트 (abstract/claims 의미 검색)
    "unknown",
]


# ── 룰 ─────────────────────────────────────────────────────
KW_PATENT_GENERIC = (
    "특허", "patent", "출원", "발명", "등록특허", "공개특허",
    "patent application", "patent grant",
)
KW_CPC = ("CPC", "IPC", "분류코드", "기술분야", "technology field")
KW_CITATION = ("인용", "피인용", "citation", "cited", "cites")
KW_COMPARE = ("비교", "vs", "차이", "compare", "versus")
KW_ASSIGNEE = ("출원인", "applicant", "assignee", "특허권자")
KW_INVENTOR = ("발명자", "inventor")

# Cross-Domain 트리거 — 회사 재무·자동차 + 특허 동시 등장.
KW_FIN = ("매출", "영업이익", "재무", "R&D", "주가", "revenue", "earnings", "R&D비")
KW_AUTO = ("리콜", "차종", "OEM", "공급사", "recall", "supplier")


def _has_any(q: str, kws) -> bool:
    return any(k in q for k in kws)


def classify_question_ip(question: str) -> IPQuestionKind:
    """IP 도메인 질문 유형 룰 분류 — LLM 미사용."""
    q = question or ""
    if _has_any(q, KW_CITATION):
        return "citation_network"
    if _has_any(q, KW_COMPARE) and _has_any(q, KW_PATENT_GENERIC + KW_ASSIGNEE):
        return "patent_compare"
    if _has_any(q, KW_CPC):
        return "cpc_search"
    if _has_any(q, KW_ASSIGNEE) and _has_any(q, KW_PATENT_GENERIC):
        return "assignee_patents"
    if _has_any(q, KW_PATENT_GENERIC):
        return "patent_narrative"
    return "unknown"


def select_tools_ip(kind: IPQuestionKind) -> list[str]:
    if kind == "patent_lookup":
        return ["lookup_patent", "get_patent_info"]
    if kind == "assignee_patents":
        return ["lookup_assignee_graph", "list_patents_of_assignee",
                "count_patents_by_field"]
    if kind == "cpc_search":
        return ["list_patents_in_cpc", "list_assignees_in_field"]
    if kind == "citation_network":
        return ["get_citation_network", "most_cited_patents"]
    if kind == "patent_compare":
        return ["compare_assignees_patent_volume"]
    if kind == "patent_narrative":
        return ["search_patents"]
    return []


def plan_ip_tasks(*, question: str, target_assignees: list[str] | None = None,
                  target_cpcs: list[str] | None = None,
                  target_corps: list[str] | None = None) -> list[dict]:
    """planner_node 위임 — IP-L1~L3 task DAG.

    autograph.policy.plan_auto_tasks 와 동일 dict shape:
        {"id": str, "intent": str, "args": dict, "depends_on": list[str]}
    """
    kind = classify_question_ip(question)
    tasks: list[dict] = []

    if kind == "assignee_patents" and (target_assignees or target_corps):
        tasks.append({
            "id": "lookup_assignee",
            "intent": "lookup_assignee_graph",
            "args": {"query": (target_assignees or target_corps)[0]},
            "depends_on": [],
        })
        tasks.append({
            "id": "list_patents",
            "intent": "list_patents_of_assignee",
            "args": {"assignee_id": "{{lookup_assignee.assignee_id}}"},
            "depends_on": ["lookup_assignee"],
        })
    elif kind == "cpc_search" and target_cpcs:
        tasks.append({
            "id": "cpc_patents",
            "intent": "list_patents_in_cpc",
            "args": {"cpc_code": target_cpcs[0], "include_subclasses": True},
            "depends_on": [],
        })
    elif kind == "citation_network":
        # 발견된 patent / assignee 없으면 narrative search 로 1차 retrieval.
        tasks.append({
            "id": "search_seed",
            "intent": "search_patents",
            "args": {"query": question, "top_k": 8},
            "depends_on": [],
        })
    elif kind == "patent_narrative":
        tasks.append({
            "id": "search_patents",
            "intent": "search_patents",
            "args": {"query": question, "top_k": 8},
            "depends_on": [],
        })
    return tasks


def plan_cross_ip_tasks(*, question: str,
                        target_assignees: list[str] | None = None,
                        target_corps: list[str] | None = None) -> list[dict]:
    """CD-L3/L4 — 특허 ↔ 재무 / 부품 / 리콜 cross-domain task.

    예: "삼성SDI 배터리 특허(H01M) 영업이익 + 그 셀 쓰는 OEM 리콜"
    """
    tasks: list[dict] = []
    if target_corps:
        tasks.append({
            "id": "cross_query_ip",
            "intent": "cross_query_ip",
            "args": {"corp_code": target_corps[0], "question": question},
            "depends_on": [],
        })
    return tasks


# ── 라우터 — register_router 로 core 에 등록 ────────────────
def route_domain_ip(question: str, hint: str | None) -> str | None:
    """질문 → 'ip' 또는 None.

    hint 가 'ip' 면 즉시 'ip'. 그 외에는 키워드 기반:
    - 특허·patent + 회사재무/자동차 동시 → 'cross_domain' (autograph 라우터가 받게 양보)
    - 특허만 → 'ip'
    - 그 외 → None (다음 라우터 시도)
    """
    if hint == "ip":
        return "ip"
    q = question or ""
    has_patent = _has_any(q, KW_PATENT_GENERIC + KW_CPC + KW_ASSIGNEE +
                              KW_CITATION + KW_INVENTOR)
    if not has_patent:
        return None
    has_fin = _has_any(q, KW_FIN)
    has_auto = _has_any(q, KW_AUTO)
    if has_fin or has_auto:
        # cross_domain 라우터 (autograph) 가 받도록 양보 — 본 라우터는 'ip' 단독 question 만 잡음.
        return None
    return "ip"


__all__ = [
    "IPQuestionKind",
    "classify_question_ip",
    "select_tools_ip",
    "plan_ip_tasks",
    "plan_cross_ip_tasks",
    "route_domain_ip",
]

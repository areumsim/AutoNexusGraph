"""에이전트 라우팅 정책 + cost guard.

원칙 (PRD §7.1):
- 단순 사실 (회사·연도·지표) → financials tool 직접
- 의미·서술 → retrieve.search_documents
- 관계·구조 → graph tools
- 멀티홉 → 다중 도구 조합

cost guard:
- 한 turn 의 누적 비용이 AGENT_TURN_BUDGET_USD 초과 시 즉시 답변 단계로 점프.
"""

from __future__ import annotations

import os
import re

from .state import AgentState, QuestionKind

# 룰 기반 1차 분류 — 빠르고 LLM 호출 없음. 모호하면 'unknown' → planner LLM 이 재분류.
RE_YEAR        = re.compile(r"(19|20)\d{2}\s*년?")
KW_FINANCIAL   = ("매출", "영업이익", "순이익", "자산", "부채", "ROE", "ROA", "PER", "PBR")
KW_STRUCTURAL  = ("자회사", "임원", "대표", "주주", "지분", "계열사", "기업집단", "모회사")
KW_NARRATIVE   = ("위험", "전략", "전망", "사업 개요", "비즈니스 모델", "주요사항", "ESG")
KW_MULTIHOP    = ("중에", "들의", "함께", "동시에", "vs", "비교", "합산", "총합")


def classify_question(question: str) -> QuestionKind:
    """질문 유형 룰 분류 — LLM 호출 X. 모호하면 unknown."""
    q = question or ""
    has_year = bool(RE_YEAR.search(q))
    f = any(k in q for k in KW_FINANCIAL)
    s = any(k in q for k in KW_STRUCTURAL)
    n = any(k in q for k in KW_NARRATIVE)
    m = any(k in q for k in KW_MULTIHOP)

    # 우선순위: multi_hop > structural > factual > narrative
    if m and (f or s):
        return "multi_hop"
    if s and not n:
        return "structural"
    if f and has_year:
        return "factual"
    if n:
        return "narrative"
    if s:
        return "structural"
    if f:
        return "factual"
    return "unknown"


def turn_budget_remaining(state: AgentState) -> float:
    """이 turn 의 남은 예산 (USD). 0 또는 음수면 중단 신호.

    도메인별 override 가 있으면 그것을 사용 — auto/cross_domain 분리 추적.
    """
    from ..config import turn_budget_for_domain
    used = float(state.get("llm_usage_usd") or 0.0)
    return turn_budget_for_domain(state.get("domain")) - used


def turn_budget_exceeded(state: AgentState) -> bool:
    return turn_budget_remaining(state) <= 0.0


def select_tools(kind: QuestionKind) -> list[str]:
    """질문 유형 → 권장 도구 목록 (Planner 가 ground 잡는 용도)."""
    if kind == "factual":
        return ["lookup_company", "get_revenue", "get_operating_income"]
    if kind == "structural":
        return ["lookup_company", "list_subsidiaries", "get_executives",
                "get_major_shareholders", "get_subgraph"]
    if kind == "narrative":
        return ["lookup_company", "search_documents"]
    if kind == "multi_hop":
        return ["lookup_company", "list_subsidiaries", "get_companies_of_person",
                "find_paths", "get_revenue", "search_documents"]
    # unknown → 안전한 default
    return ["lookup_company", "search_documents"]


# ── Cross-store 수치 랭킹 게이트 (V5 일반화) ──────────────────────────
# 인물·자회사 등 graph 후보 → SQL `compare_companies` 수치 랭킹의 cross-store 라우팅.
# 기존엔 flat 최상급 키워드(_RANK_KEYWORD_LEGACY)만으로 게이트해 패러프레이즈
# ("매출 1위"·"순위가 가장 높은"·"매출이 더 많은")에 발화 안 돼 win 상실(thesis §1).
# structural 모드 = 비교·서열·최상급 구조(Signal A) ∧ 수치 metric(Signal B) 의 곱.
# metric 요구가 정밀도를 지킨다(비-수치 multi-hop 은 B 부재 → 비발화 → main 비회귀).

# legacy 키워드 — keyword 모드에서 현 동작 보존용 (llm_planner 인라인 리스트와 동일).
_RANK_KEYWORD_LEGACY = (
    "가장 큰", "가장 작은", "가장 높은", "가장 낮은", "최대", "최소",
    "가장 많은", "가장 적은", "최고", "최저",
)

# Signal A: 비교·서열·최상급 구조 (패러프레이즈 견고).
_RANK_STRUCT_SUBSTR = (
    "가장", "최대", "최소", "최고", "최저",                 # 최상급
    "순위", "상위", "하위", "순으로",                       # 서열
    "더 큰", "더 작은", "더 많은", "더 적은", "더 높은", "더 낮은",   # 비교급
    "큰 순", "작은 순", "높은 순", "낮은 순", "많은 순", "적은 순",
    "보다 큰", "보다 작은", "보다 많은", "보다 적은", "보다 높은", "보다 낮은",
)
_RANK_ORDINAL_RE = re.compile(r"\d+\s*위")   # "1위", "3 위"

# Signal B: 수치 metric 어휘 (KW_FINANCIAL 확장).
KW_NUMERIC_METRIC = KW_FINANCIAL + (
    "당기순이익", "자본", "시가총액", "시총", "직원", "종업원", "고용",
)


def detect_cross_store_ranking(q: str) -> bool:
    """구조적 cross-store 수치 랭킹 감지 — Signal A(비교·서열 구조) ∧ B(수치 metric).

    flat 최상급 키워드보다 넓은 패러프레이즈(서수 'N위'·비교급 '더 많은'·'순위')를
    포착하면서, metric 토큰 요구로 비-수치 multi-hop 질문의 오발화를 차단한다.
    결정적·LLM 불요·지연 0. → `llm_planner` 가 sql `compare_companies` 힌트 노출 여부 결정.
    """
    s = q or ""
    a = any(k in s for k in _RANK_STRUCT_SUBSTR) or bool(_RANK_ORDINAL_RE.search(s))
    if not a:
        return False
    return any(m in s for m in KW_NUMERIC_METRIC)


def rank_gate_mode() -> str:
    """cross-store 랭킹 게이트 모드 — env `ANXG_RANK_GATE`.

    "off"(힌트 비노출) / "keyword"(legacy flat 키워드) / "structural"(`detect_cross_store_ranking`).
    **default=structural** — 측정으로 T-G1(패러프레이즈 재현율 +50.0pp)·T-G2(main 비회귀,
    0/62 발화) 확인 후 keyword→structural 플립(thesis §1, 2026-06-16). 3-way 재현 측정용 토글.
    """
    mode = (os.getenv("ANXG_RANK_GATE") or "structural").strip().lower()
    return mode if mode in ("off", "keyword", "structural") else "structural"


def is_cross_store_ranking(q: str) -> bool:
    """현재 게이트 모드에 따른 cross-store 랭킹 판정 — `llm_planner` 진입점."""
    mode = rank_gate_mode()
    if mode == "off":
        return False
    if mode == "structural":
        return detect_cross_store_ranking(q)
    return any(k in (q or "") for k in _RANK_KEYWORD_LEGACY)   # keyword (default)


__all__ = [
    "classify_question", "turn_budget_remaining", "turn_budget_exceeded",
    "select_tools",
    "detect_cross_store_ranking", "rank_gate_mode", "is_cross_store_ranking",
]

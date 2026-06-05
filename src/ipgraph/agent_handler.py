"""IPGraph (도메인3) DomainHandler — core 와 plug-in 결합.

PRD §10.12 의도: core (autonexusgraph) → ipgraph 의존 0건. 본 모듈은 import 1회로
``register_handler(IPGraphHandler())`` + ``register_router(route_domain_ip)`` 부작용.

Protocol 6 메서드 (실 spec = ``src/autonexusgraph/agents/_domain_handler.py:44-81``):
- ``identify_targets`` — assignee/corp_code/CPC 코드를 state 에 채움
- ``plan_tasks``       — IP-L1~L3 task DAG
- ``toolbox_modules``  — [ipgraph.tools]
- ``allowed_intents``  — kind 별 화이트리스트
- ``fallback_search``  — search_patents 또는 None
- ``retrieve_module``  — ipgraph.tools.retrieve
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from typing import Any

log = logging.getLogger(__name__)


# ── 화이트리스트 (PRD §7.5.10 — 자유 SQL/Cypher 금지) ──────────────
IP_GRAPH_ALLOWED = {
    "lookup_assignee_graph", "list_patents_of_assignee",
    "get_inventors_of_patent", "find_co_assignees",
    "list_patents_in_cpc", "list_assignees_in_field",
    "get_citation_network", "most_cited_patents",
}
IP_SQL_ALLOWED = {
    "lookup_patent", "get_patent_info",
    "list_patents_by_assignee", "count_patents_by_field",
    "compare_assignees_patent_volume",
    # bridge — corp 매핑은 SQL 워커가 호출.
    "bridge_assignee_to_corp", "bridge_corp_to_assignee",
    "cross_query_ip",
}
IP_RESEARCH_INTENTS = {
    "search_patents", "search_by_metadata_ip", "get_chunk_ip",
}


# ── target 추출 — assignee 이름 / CPC 코드 룰 ─────────────────────
# CPC 코드 패턴: A47C / H01M 10/052 / B60W 30/00 등.
_CPC_PATTERN = re.compile(
    r"\b([A-H]\d{2}[A-Z](?:\s*\d+(?:/\d+)?)?)\b",
)

# 한국 주요 특허 출원인 (docs/ipgraph.md §5 우선 OEM/배터리社).
_PRIORITY_ASSIGNEES = {
    "현대자동차": "hyundai",
    "현대차":     "hyundai",
    "기아":       "kia",
    "삼성SDI":    "samsung_sdi",
    "LG에너지솔루션": "lg_es",
    "LG엔솔":     "lg_es",
    "현대모비스": "mobis",
    "Samsung SDI": "samsung_sdi",
    "LG Energy Solution": "lg_es",
    "Hyundai Motor": "hyundai",
    "Hyundai Mobis": "mobis",
}


def _identify_ip_targets(state: Any, question: str) -> None:
    """assignee / cpc / corp_code 룰 추출 → state.target_* 채움."""
    q = question or ""

    cpcs = sorted({m.group(1).replace(" ", "") for m in _CPC_PATTERN.finditer(q)})
    if cpcs:
        state["target_cpcs"] = cpcs            # type: ignore[index]

    assignees: list[str] = []
    for label, slug in _PRIORITY_ASSIGNEES.items():
        if label in q and slug not in assignees:
            assignees.append(slug)
    if assignees:
        state["target_assignees"] = assignees   # type: ignore[index]


# ── IPGraphHandler ────────────────────────────────────────────────
class IPGraphHandler:
    """domain='ip' 핸들러 — 특허 단독 도메인 동작."""

    domain = "ip"

    def identify_targets(self, state: Any, *, question: str) -> None:
        _identify_ip_targets(state, question)

    def plan_tasks(self, state: Any, *, question: str) -> list[dict]:
        from .policy import plan_ip_tasks
        return plan_ip_tasks(
            question=question,
            target_assignees=state.get("target_assignees") or [],
            target_cpcs=state.get("target_cpcs") or [],
            target_corps=state.get("target_companies") or [],
        )

    def toolbox_modules(self) -> list[Any]:
        try:
            from . import tools as ip_tb
        except ImportError as exc:
            log.warning("[ipgraph.tools] import 실패 (skip): %s", exc)
            return []
        return [ip_tb]

    def allowed_intents(self, kind: str) -> set[str]:
        return {
            "graph":    IP_GRAPH_ALLOWED,
            "sql":      IP_SQL_ALLOWED,
            "research": IP_RESEARCH_INTENTS,
        }.get(kind, set())

    def fallback_search(
        self, state: Any, *, query: str,
    ) -> tuple[str, Callable, dict] | None:
        try:
            from .tools.retrieve import search_patents
        except Exception as exc:   # noqa: BLE001 — [agent_handler] fail-soft 흡수 → None 반환 (log 동반)
            log.warning("[ip.fallback] tools.search_patents unavailable: %s", exc)
            return None
        args: dict[str, Any] = {"query": query, "top_k": 6}
        ta = state.get("target_assignees") or []
        if ta:
            args["assignee_id"] = ta[0]
        return ("search_patents", search_patents, args)

    def retrieve_module(self) -> Any | None:
        try:
            from .tools import retrieve
            return retrieve
        except Exception as exc:   # noqa: BLE001 — [agent_handler] fail-soft 흡수 → None 반환 (log 동반)
            log.warning("[ip.retrieve] tools.retrieve unavailable: %s", exc)
            return None


def _register() -> None:
    """import 부작용 — core registry 에 핸들러 + 라우터 등록.

    core handler API 미가용 (테스트 환경 등) 또는 policy 가용 안 함 시 fail-soft.
    """
    try:
        from autonexusgraph.agents._domain_handler import (
            register_handler,
            register_router,
        )
    except Exception as exc:   # noqa: BLE001 — core registry import 실패 → register skip (finance-only / 테스트 환경)
        log.debug("[ipgraph.agent_handler] core handler API unavailable: %s", exc)
        return
    try:
        register_handler(IPGraphHandler())
    except Exception as exc:   # noqa: BLE001 — handler 등록 실패 흡수 → silent (debug log, core 가 finance 폴백)
        log.debug("[ipgraph.agent_handler] register_handler failed: %s", exc)

    try:
        from .policy import route_domain_ip
        register_router(route_domain_ip)
    except Exception as exc:   # noqa: BLE001 — router 등록 실패 흡수 → silent (라우팅이 finance 만 동작)
        log.debug("[ipgraph.agent_handler] register_router failed: %s", exc)


_register()


__all__ = [
    "IPGraphHandler",
    "IP_GRAPH_ALLOWED",
    "IP_SQL_ALLOWED",
    "IP_RESEARCH_INTENTS",
]

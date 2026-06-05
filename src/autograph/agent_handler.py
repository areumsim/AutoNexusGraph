"""autograph 의 DomainHandler 구현 — core agent 와 plug-in 결합.

본 모듈은 ``src/autograph/__init__.py`` 가 import 1회로 인해 두 핸들러 (auto,
cross_domain) + 라우터 (route_domain) 를 core registry 에 자동 등록한다.

PRD §10.12 의도: core 는 ``from autograph`` 를 0건 보유. 핸들러 등록이 의존
방향을 바꾼다 (autograph → core, 반대 아님).

각 핸들러가 보유:
- ``identify_targets``  : triage_node 위임 — target_vehicles/models/makes 채움
- ``plan_tasks``        : planner_node 위임 — task DAG 반환
- ``toolbox_modules``   : workers._toolbox_for — tool 함수 모듈 list
- ``allowed_intents``   : workers._allowed_intents — kind 별 화이트리스트
- ``fallback_search``   : executor fallback — (tool, fn, args) 또는 None
- ``retrieve_module``   : workers.research_worker — retrieve 모듈
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from autonexusgraph.agents._domain_handler import (
    DomainHandler,
    register_handler,
    register_router,
)
from autonexusgraph.agents.state import AgentState

from .policy import (
    identify_auto_targets,
    plan_auto_tasks,
    plan_cross_domain_tasks,
    route_domain,
)


log = logging.getLogger(__name__)


# ── 도메인별 화이트리스트 (구 core 의 _AUTO_*_ALLOWED 가 여기로 이동) ──
AUTO_GRAPH_ALLOWED = {
    "lookup_vehicle_graph", "lookup_supplier",
    "list_components", "list_systems_of_model", "list_models_with_system",
    "list_recalls_affecting",
    "list_investigations_affecting", "get_investigation_recall_chain",
    "get_suppliers_of_component", "get_vehicles_using_component",
    "find_vehicle_component_paths",
}
AUTO_SQL_ALLOWED = {
    "lookup_vehicle", "get_vehicle_info", "get_spec",
    "compare_vehicles", "get_safety_rating",
    # 생산 & 공정 (DART + 산단공 + KAMA) — 2026-06-01 신규
    "get_plant_capacity", "get_oem_production", "list_plants_by_oem",
    "search_processes",
    "get_macro_industry", "get_macro_production",
    # bridge 도 SQL 워커가 호출 (PG 단일 호출)
    "bridge_corp_to_entity", "bridge_entity_to_corp",
    "bridge_sec_cik_to_entity", "bridge_entity_to_sec_cik",
    "get_oem_financials_sec",
    "cross_query",
}
AUTO_RESEARCH_INTENTS = {
    "search_documents_auto", "search_by_metadata_auto", "get_chunk_auto",
}


# ── AutoHandler ────────────────────────────────────────────────────
class AutoHandler:
    """domain='auto' 핸들러 — 자동차 단독 도메인 동작."""

    domain = "auto"

    def identify_targets(self, state: AgentState, *, question: str) -> None:
        identify_auto_targets(state, question=question)

    def plan_tasks(self, state: AgentState, *, question: str) -> list[dict]:
        return plan_auto_tasks(
            question=question,
            target_vehicles=state.get("target_vehicles") or [],
            target_models=state.get("target_models") or [],
            target_makes=state.get("target_makes") or [],
        )

    def toolbox_modules(self) -> list[Any]:
        from . import tools as auto_tb
        return [auto_tb]

    def allowed_intents(self, kind: str) -> set[str]:
        return {
            "graph":    AUTO_GRAPH_ALLOWED,
            "sql":      AUTO_SQL_ALLOWED,
            "research": AUTO_RESEARCH_INTENTS,
        }.get(kind, set())

    def fallback_search(
        self, state: AgentState, *, query: str,
    ) -> tuple[str, Callable, dict] | None:
        try:
            from .tools import search_documents_auto
        except Exception as exc:   # noqa: BLE001 — fail-soft 흡수 → None 반환 (log 동반)
            log.warning("[auto.fallback] tools.search_documents_auto unavailable: %s",
                        exc)
            return None
        args: dict[str, Any] = {"query": query, "top_k": 6}
        # 좁혀줄 수 있는 model_id 가 있으면 활용. target_makes/vehicles 는 호환
        # 시그니처가 없어 미적용.
        if state.get("target_models"):
            models = state["target_models"]
            args["model_id"] = models[0] if len(models) == 1 else models
        return ("search_documents_auto", search_documents_auto, args)

    def retrieve_module(self) -> Any | None:
        try:
            from .tools import retrieve
            return retrieve
        except Exception as exc:   # noqa: BLE001 — fail-soft 흡수 → None 반환 (log 동반)
            log.warning("[auto.retrieve] tools.retrieve unavailable: %s", exc)
            return None


# ── CrossDomainHandler ────────────────────────────────────────────
class CrossDomainHandler(AutoHandler):
    """domain='cross_domain' 핸들러 — finance + auto 동시 처리."""

    domain = "cross_domain"

    def plan_tasks(self, state: AgentState, *, question: str) -> list[dict]:
        return plan_cross_domain_tasks(
            question=question,
            target_companies=state.get("target_companies") or [],
            target_makes=state.get("target_makes") or [],
            target_models=state.get("target_models") or [],
            target_vehicles=state.get("target_vehicles") or [],
        )

    def toolbox_modules(self) -> list[Any]:
        # auto 가 먼저 — auto 전용 intent 가 finance 의 동명 함수보다 우선 매치.
        from . import tools as auto_tb
        from autonexusgraph import tools as fin_tb
        return [auto_tb, fin_tb]

    def allowed_intents(self, kind: str) -> set[str]:
        from autonexusgraph.agents.workers import (
            FIN_GRAPH_ALLOWED, FIN_SQL_ALLOWED, FIN_RESEARCH_INTENTS,
        )
        fin = {
            "graph":    FIN_GRAPH_ALLOWED,
            "sql":      FIN_SQL_ALLOWED,
            "research": FIN_RESEARCH_INTENTS,
        }.get(kind, set())
        return super().allowed_intents(kind) | fin


# ── 모듈 import 시점 자동 등록 ────────────────────────────────────
register_handler(AutoHandler())
register_handler(CrossDomainHandler())
register_router(route_domain)


__all__ = [
    "AutoHandler",
    "CrossDomainHandler",
    "AUTO_GRAPH_ALLOWED",
    "AUTO_SQL_ALLOWED",
    "AUTO_RESEARCH_INTENTS",
]

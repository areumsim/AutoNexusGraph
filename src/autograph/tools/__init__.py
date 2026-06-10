"""AutoGraph 사전 정의 tool — 자유 SQL/Cypher 금지.

모듈 구성 (finance 의 tools 패턴과 동일):
- spec     : PG 정형 (차종 식별, 제원, 안전 등급)
- graph    : Neo4j 관계 탐색 (리콜, 컴포넌트, 공급사) — cypher 템플릿 경유
- retrieve : pgvector 의미 검색 (자동차 청크 메타 필터)
- bridge   : Cross-Domain (corp_code ↔ entity_id)

본 패키지 import 시점에 AUTO_TEMPLATES 가 finance 의 TEMPLATES 에 병합된다 → 같은
render_template / _run / cypher_guard 파이프라인을 그대로 통과.
"""

# ── Cypher 템플릿 자동 병합 (import 1회) ─────────────────────
# register_templates() 가 spec shape 도 eager 검증 → AUTO_TEMPLATES 가 finance
# 와 동일 스키마를 따르지 않으면 import 시점에 즉시 실패 (drift 방지).
from autonexusgraph.tools.cypher_templates import (
    TEMPLATES as _FIN_TEMPLATES,
)
from autonexusgraph.tools.cypher_templates import (
    register_templates as _register_templates,
)

from ..cypher_templates_auto import AUTO_TEMPLATES as _AUTO_TEMPLATES

_register_templates(_FIN_TEMPLATES, _AUTO_TEMPLATES)


from .bridge import (
    bridge_corp_to_entity,
    bridge_entity_to_corp,
    bridge_entity_to_sec_cik,
    bridge_sec_cik_to_entity,
    cross_query,
    get_oem_financials_sec,
)
from .graph import (
    find_vehicle_component_paths,
    get_investigation_recall_chain,
    get_suppliers_of_component,
    get_vehicles_using_component,
    list_components,
    list_investigations_affecting,
    list_models_with_system,
    list_recalls_affecting,
    list_systems_of_model,
    lookup_supplier,
)
from .graph import lookup_vehicle as lookup_vehicle_graph
from .process import (
    get_process_info,
    get_process_metrics,
    list_materials_of_process,
    list_plants_of_process,
    list_process_route,
    list_steps_of_process,
    lookup_process,
)
from .retrieve import (
    get_chunk_auto,
    search_by_metadata_auto,
    search_documents_auto,
)
from .spec import (
    compare_vehicles,
    get_macro_industry,
    get_macro_production,
    get_oem_production,
    get_plant_capacity,
    get_safety_rating,
    get_spec,
    get_vehicle_info,
    list_plants_by_oem,
    lookup_vehicle,
    search_processes,
)

__all__ = [
    # spec
    "lookup_vehicle",
    "get_vehicle_info",
    "get_spec",
    "compare_vehicles",
    "get_safety_rating",
    # 생산 & 공정 (DART + 산단공 + KAMA)
    "get_plant_capacity",
    "get_oem_production",
    "list_plants_by_oem",
    "search_processes",
    "get_macro_industry",
    "get_macro_production",
    # graph
    "lookup_vehicle_graph",
    "lookup_supplier",
    "list_components",
    "list_systems_of_model",
    "list_models_with_system",
    "list_recalls_affecting",
    "list_investigations_affecting",
    "get_investigation_recall_chain",
    "get_suppliers_of_component",
    "get_vehicles_using_component",
    "find_vehicle_component_paths",
    # retrieve
    "search_documents_auto",
    "search_by_metadata_auto",
    "get_chunk_auto",
    # bridge
    "bridge_corp_to_entity",
    "bridge_entity_to_corp",
    "bridge_sec_cik_to_entity",
    "bridge_entity_to_sec_cik",
    "get_oem_financials_sec",
    "cross_query",
    # BoP 공정 (ProcessGraph — :Process/:ProcessStep/PRECEDES)
    "lookup_process",
    "get_process_info",
    "list_process_route",
    "list_steps_of_process",
    "list_plants_of_process",
    "list_materials_of_process",
    "get_process_metrics",
]

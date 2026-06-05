"""IPGraph 사전 정의 tool — 자유 SQL/Cypher 금지.

모듈 구성 (autograph 의 tools 패턴과 동일):
- patents  : PG 정형 (특허 식별, 출원인, CPC 집계)
- graph    : Neo4j 관계 탐색 (인용, CPC 계층, co-assignee) — cypher 템플릿 경유
- retrieve : pgvector 의미 검색 (abstract+claims 청크 메타 필터)
- bridge   : Cross-Domain (assignee_id ↔ corp_code via anxg_ip.assignee_corp_map)

본 패키지 import 시점에 ``IP_TEMPLATES`` 가 finance 의 ``TEMPLATES`` 에 병합된다 →
같은 render_template / _run / cypher_guard 파이프라인을 그대로 통과.
"""

# ── Cypher 템플릿 자동 병합 (import 1회) ─────────────────────
from autonexusgraph.tools.cypher_templates import (
    TEMPLATES as _FIN_TEMPLATES,
    register_templates as _register_templates,
)
from ..cypher_templates_ip import IP_TEMPLATES as _IP_TEMPLATES

_register_templates(_FIN_TEMPLATES, _IP_TEMPLATES)


from .patents import (
    compare_assignees_patent_volume,
    count_patents_by_field,
    get_patent_info,
    list_patents_by_assignee,
    lookup_patent,
)
from .graph import (
    find_co_assignees,
    get_citation_network,
    get_inventors_of_patent,
    list_assignees_in_field,
    list_patents_in_cpc,
    list_patents_of_assignee,
    lookup_assignee_graph,
    most_cited_patents,
)
from .retrieve import (
    get_chunk_ip,
    search_by_metadata_ip,
    search_patents,
)
from .bridge import (
    bridge_assignee_to_corp,
    bridge_corp_to_assignee,
    cross_query_ip,
)


__all__ = [
    # patents
    "lookup_patent",
    "get_patent_info",
    "list_patents_by_assignee",
    "count_patents_by_field",
    "compare_assignees_patent_volume",
    # graph
    "lookup_assignee_graph",
    "list_patents_of_assignee",
    "get_inventors_of_patent",
    "find_co_assignees",
    "list_patents_in_cpc",
    "list_assignees_in_field",
    "get_citation_network",
    "most_cited_patents",
    # retrieve
    "search_patents",
    "search_by_metadata_ip",
    "get_chunk_ip",
    # bridge
    "bridge_assignee_to_corp",
    "bridge_corp_to_assignee",
    "cross_query_ip",
]

"""AutoGraph — 자동차 제품·부품·리콜·공급망 GraphRAG 도메인 (PRD v2.0).

AutoNexusGraph 코어(LangGraph multi-agent, PG/Neo4j/pgvector, cost/number/cypher guard)를
재사용하면서 자동차 도메인 어댑터·tool·ingestion·loader 만 본 패키지에 둔다.

코어 라우팅 결정:
- 자유 SQL/Cypher 금지 — 모든 Cypher 는 ``autograph.cypher_templates_auto.AUTO_TEMPLATES``
  레지스트리에 등록.
- 정량 수치는 PG 조회 결과만 사용 (LLM 생성 금지). bridge.corp_entity 경유로 finance 와 연결.
- 관계 정보는 Neo4j 에 두되 source / confidence / validated_status / snapshot_year 강제.
"""

__version__ = "0.1.0"


# ── DomainHandler 자동 등록 (PRD §10.12) ───────────────────────────
# autograph 패키지가 import 되는 순간 core registry 에 AutoHandler +
# CrossDomainHandler + route_domain 라우터를 등록한다. 이로써 core 는
# ``from autograph`` 0건을 유지하면서도 자동차 도메인 동작.
#
# 등록은 idempotent — register_handler 는 같은 domain 키를 덮어쓰는 정책.
# 따라서 다중 import / reload 환경에서도 안전.
from . import agent_handler as _agent_handler  # noqa: F401

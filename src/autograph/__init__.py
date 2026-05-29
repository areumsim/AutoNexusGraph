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

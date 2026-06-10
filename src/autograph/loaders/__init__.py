"""AutoGraph loaders — raw → PG (auto.*) → Neo4j → bridge → anxg_vec.chunks 의 멱등 적재.

PG 가 SSOT. Neo4j 는 PG 적재 결과를 MERGE 로 동기화. 본 흐름이 깨지지 않는 한
Neo4j 단독 수정은 금지 (재현·감사 깨짐).
"""

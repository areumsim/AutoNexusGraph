# ADR 0004 — Deterministic-first 추출 (P1~P4) + 7키 엣지 메타

**Status**: Accepted

## Context
관계 그래프를 LLM 으로만 채우면 환각이 그래프에 영구 박힌다. 그러나 서술형 텍스트(리콜 본문·IR·매뉴얼)의 관계는 결정적 매핑만으로는 못 잡는다. 둘을 같은 그래프에 섞되 **신뢰도를 추적 가능**하게 해야 한다.

## Decision
- **4-pass 추출**:
  - **P1/P2 — 정형 직매핑**(deterministic): XBRL·vPIC·NHTSA·Wikidata 등 → grade A/B.
  - **P3 — Selective LLM**: 서술형 텍스트에서 관계 후보(`SUPPLIED_BY` 등) 추출, schema-aware, `anxg_auto.staging_relations` 적재 → grade C (저신뢰 LLM 후보).
  - **P4 — Cross-validate**: P3 vs P2 SSOT 비교 → `validated`(일치) / `rejected`(충돌, deterministic 우선) / `candidate`(≥0.80) / `needs_review`(≥0.65). `p4_decision` 컬럼 + Neo4j MERGE 시 `validated_status`.
- **모든 관계 엣지 7키 메타 의무**: `source_type/source_id/confidence_score/validated_status/snapshot_year/extraction_method/schema_version`.
- **승급 규칙**: `SUPPLIED_BY` 등은 A/B 출처 + P4 통과 시에만 `validated=true`. **C 단독은 절대 validated 금지**.
- P3 활성 관계는 보수적으로 최소화 — P3 LLM 추출 활성은 `SUPPLIED_BY`/`CAUSED_BY_PROCESS`; `COMPETES_WITH` 만 `enabled:false`(비용·환각 위험 검증 전). (`RECALL_OF` 는 P3 아닌 P2 deterministic — `ontology/auto/relations.yaml`.)

## Consequences
- (+) 결정적 사실과 LLM 후보가 출처·검증상태로 분리 → 환각이 답변에 새지 않음. `audit-edge-meta --strict` 로 7키 100% 강제.
- (+) hop/confidence 메트릭(E-3) 과 calibration(Q-2) 의 토대.
- (−) P3/P4 풀 실측은 LLM 키 필요(현재 시뮬). `COMPETES_WITH`(enabled:false) 활성은 후속 검증 대기.

## Alternatives
- LLM-only 추출 → 환각 그래프, 기각.
- deterministic-only → 서술형 관계 누락, 기각(P3 보강 채택, 단 C 등급 격리).

## References
- `src/autograph/extractors/` (run_p3 / cross_validate) · `ontology/auto/relations.yaml`(enabled 플래그) · `scripts/audit/edge_meta_invariants.py` · [mental_model §2.2.5 · §2.3](../mental_model.md) · README §3.7/§4.0

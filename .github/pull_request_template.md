<!-- CONTRIBUTING.md 참조. 본인이 수정한 파일만 커밋 (병렬 작업 흡수 금지). -->

## 무엇을 / 왜
<!-- 변경 요약 + BACKLOG 항목 ID (예: O-3 / A-4) -->

## 변경 유형
- [ ] feat / [ ] fix / [ ] docs / [ ] refactor / [ ] chore

## 체크리스트
- [ ] **`make smoke-e2e` 통과** (CI 동일 게이트)
- [ ] 자유 SQL/Cypher 없음 — tool pool + cypher 템플릿만
- [ ] 새 관계 엣지면 **7키 메타**(source_type/source_id/confidence_score/validated_status/snapshot_year/extraction_method/schema_version)
- [ ] 새 데이터 소스면 `ingestion/_license.py::LICENSE_POLICY` 등록
- [ ] 온톨로지 변경이면 `make audit-ontology` PASS
- [ ] 키 부재 graceful skip + 멱등(ON CONFLICT/MERGE)
- [ ] **[BACKLOG.md](../BACKLOG.md) 항목 상태 갱신** + 관련 README 표기
- [ ] 코어 변경(`src/{autonexusgraph,fingraph}`)이 크면 §10.12 baseline reset 고려
- [ ] 시크릿/PII 미포함 (`.env.*` 커밋 금지)

## 측정 / 검증
<!-- 테스트 추가분, make audit-* 결과, 수동 검증 -->

# rag_tools.md — 폐기 (2026-06-02)

> **본 문서는 폐기됨.** 모든 내용이 [docs/api_reference.md](../api_reference.md) 에 흡수.

## 흡수 매핑

| 옛 `operations/rag_tools.md` 절 | 새 위치 |
|---|---|
| §모듈 구성 + finance 도구 시그니처 (financials / graph / retrieve) | [api_reference.md §1 Finance 도메인](../api_reference.md) |
| §tools.cypher_templates 레지스트리 | [api_reference.md §0.2 안전 가드](../api_reference.md) — param_schema 검증 |
| §tools.graph 주요 함수 | [api_reference.md §1.2](../api_reference.md) |
| §tools.retrieve Hybrid 검색 | [api_reference.md §1.3](../api_reference.md) |
| §시나리오 예시 5개 (위험요인 / ESG A+ / 이재용 임원 / 경로 / 부정 뉴스) | [api_reference.md §4.4 Finance 단일 도메인 시나리오](../api_reference.md) |
| §안전 가드 (자동 적용) | [api_reference.md §5 안전 가드 동작 표](../api_reference.md) |
| §임베딩 서버 | [docs/operations/docker_setup.md §임베딩 (BGE-M3 / Reranker)](docker_setup.md) |

## 폐기 사유

`api_reference.md` 가 3 도메인 (finance / auto / ip) 통합 시그니처·반환 스키마 SSOT 가 되면서 `rag_tools.md` 의 finance only 시나리오만 단편 잔존 — 가치 약함. 분담 명확화 + 단일 진입점 정책.

## cross-link 갱신 (2026-06-02 일괄 처리)

- `docs/operations/agents.md` 머리말 — `api_reference.md` 로 변경 ✓
- `README.md §12` — 폐기 표시 ✓ (api_reference.md 인용)
- `docs/api_reference.md` 머리말 — 흡수 표시 + §4.4 신설 ✓

본 stub 은 git history 보존 및 외부 참조 redirect 용. 신규 cross-link 는 절대 본 파일을 인용하지 말 것.

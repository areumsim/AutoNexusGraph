# Troubleshooting

> **SSOT**: [docs/faq.md](./docs/faq.md) — FAQ · Troubleshooting (진단 트리). 본 파일은 발견성용 포인터이며, 중복 방지를 위해 내용은 faq.md 단일 SSOT 에 둔다 (BACKLOG F-2).

## 빠른 색인 (자주 막히는 7 범주)

| 범주 | 대표 증상 | 위치 |
|---|---|---|
| 환경·부팅 | `make health` 실패 / 포트 충돌 / pgvector 미설치 / Neo4j auth | [faq §Q1](./docs/faq.md#q1-환경부팅) |
| LLM·비용 | `[FAKE LLM]` / cost approval / hard limit / **rate limit 429** | [faq §Q2](./docs/faq.md#q2-llm비용) |
| 데이터 적재 | FK 위반 / 적재 0 row / **API 키 만료(DART·data.go.kr)** / embedding backfill | [faq §Q3](./docs/faq.md#q3-데이터-적재정합) |
| Cypher·Neo4j | `assert_read_only` 차단 / multi-hop timeout | [faq §Q4](./docs/faq.md#q4-cypherneo4j) |
| 평가·DoD | eval 비용 폭주 / `⊘` 항목 / edge-meta strict fail | [faq §Q5](./docs/faq.md#q5-평가dod) |
| 관측·디버깅 | trace 안 보임 / replan 루프 / clarification interrupt | [faq §Q6](./docs/faq.md#q6-관측디버깅) |
| 운영·보안 | thread 히스토리 접근 / 인증·rate limit | [faq §Q7](./docs/faq.md#q7-운영보안) |

운영 절차 상세: [docs/operations/](./docs/operations/) · 기여/보안: [CONTRIBUTING.md](./CONTRIBUTING.md) / [SECURITY.md](./SECURITY.md)

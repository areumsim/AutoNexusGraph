# Architecture Decision Records (ADR)

> 핵심 컴포넌트의 **되돌리기 어려운 결정**을 context·decision·consequences 로 기록 (F-3).
> 진행형 결정 카탈로그([확정]/[잠정]/[미정] 라벨)는 [docs/mental_model.md](../mental_model.md),
> 구조 SSOT 는 [docs/architecture.md](../architecture.md). ADR 은 그중 **이미 굳은 결정의 근거**를 요약하고 코드 라인으로 위임한다 (본문 중복 금지).

| # | 결정 | 상태 |
|---|---|---|
| [0001](0001-langgraph-stategraph.md) | LangGraph StateGraph (11 노드) + 함수체인 fallback | Accepted |
| [0002](0002-domainhandler-plugin.md) | DomainHandler Protocol + plug-in soft-load | Accepted |
| [0003](0003-bridge-corp-entity.md) | Cross-Domain Bridge 분리 테이블 (candidate→reviewed) | Accepted |
| [0004](0004-p1-p4-extraction.md) | Deterministic-first 추출 (P1~P4) + 7키 메타 | Accepted |

## 작성 규칙
- 파일명 `NNNN-kebab-title.md`, 번호 순증.
- 섹션: Status · Context · Decision · Consequences · Alternatives · References.
- 결정을 바꾸면 새 ADR 로 supersede (기존은 Status 만 갱신, 삭제 금지).

# ADR 0003 — Cross-Domain Bridge 분리 테이블 (candidate→reviewed)

**Status**: Accepted

## Context
finance(`corp_code`) ↔ auto/ip entity 를 한 turn 안에서 묶어야 하지만, 자동 매칭(이름·QID)은 오탐 위험이 있어 그래프에 직접 FK 로 박으면 Cross-Domain 환각을 유발한다.

## Decision
- 도메인 직접 FK 가 아닌 **별도 테이블 `anxg_bridge.corp_entity`** 에 매핑 보유 — `confidence_score` · `match_method` · **`reviewed_status`(candidate/reviewed/rejected)** · source 메타.
- **매칭 우선순위**: `wikidata_qid > lei > business_no > name`(+ 글로벌 OEM 진입점 `sec_cik`).
- 자동 매칭은 `candidate` 적재, 사람 검토로 `reviewed`/`rejected` 승급. 조회 도구는 `rejected` 항상 제외, `candidate` 는 플래그 제어(`src/autograph/tools/bridge.py`).
- **타 도메인 join 은 `corp_entity` 직접 변경 금지** — 신규 join 테이블(예 `anxg_ip.assignee_corp_map`)이 같은 미검토→reviewed SOP 재사용. (단 미검토 상태값은 `corp_entity` 의 `candidate` 가 아니라 `auto` — `19_ipgraph_bridge.sql:16`.)

## Consequences
- (+) 검토 전 매핑이 답변 신뢰도를 오염시키지 않음. 6개월 미검토 자동 만료 + KPI(Q-1, `bridge_review.py`).
- (+) §10.12 보존 — 새 도메인 bridge 가 코어/기존 테이블 무수정.
- (−) candidate 누적(4,792) → 검토 운영 SOP 필수(Q-1로 도구화). 다형 N-domain bridge 일반화는 미정(BACKLOG A-5/R-1).

## Alternatives
- 도메인 테이블에 직접 corp_code FK → 오탐이 그래프 오염, rollback 어려움으로 기각.
- corp_entity 에 도메인별 컬럼 누적 → 2-domain 가정 고착, 기각(신규 join 테이블 채택).

## References
- `infra/postgres/init/08_bridge.sql` + `26_bridge_review.sql` · `src/autonexusgraph/bridge_review.py` · `src/autograph/tools/bridge.py` · [docs/operations/bridge_review.md](../operations/bridge_review.md) · [mental_model §2.1.2](../mental_model.md) · README §3.5

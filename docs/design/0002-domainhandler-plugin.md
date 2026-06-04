# ADR 0002 — DomainHandler Protocol + plug-in soft-load

**Status**: Accepted

## Context
N-domain 확장(finance → auto → ip → …)을 하면서 **코어 변경 < 5%**(§10.12)를 정량 증명해야 했다. 새 도메인이 코어 그래프/노드 코드를 수정하면 확장성 주장이 무너진다.

## Decision
- 도메인별 로직을 **`DomainHandler` Protocol**(6 메서드: company/entity 해석, allowed_intents, tool 해석, fallback_search 등, `src/autonexusgraph/agents/_domain_handler.py`)로 추상화.
- 도메인 패키지는 import 부작용으로 **`register_handler()`** 등록. 코어는 ENV **`AUTONEXUSGRAPH_DOMAIN_PLUGINS`**(CSV, 기본 `autograph`)의 모듈을 첫 호출 시 **soft-load**(`discover_plugins`) — 미설치/실패는 graceful skip.
- 새 도메인 = `register_handler` + `ontology/<domain>/*.yaml` + 사전정의 도구 + cypher 템플릿 + intent 화이트리스트 + gold seed 추가만. **코어 파일 무수정**.

## Consequences
- (+) ip(도메인3) 추가가 core diff 0 LOC 로 실증 → 확장성 정량 증거(baseline reset 후 측정, [ledger](../../eval/reports/core_diff_baseline_ledger.md)).
- (+) `cross_domain` 핸들러는 finance∪auto allowed_intents 합집합으로 조합.
- (−) 도메인 간 결합이 필요하면(예: ip↔auto bridge) 별도 join 테이블 필요(ADR 0003), Protocol 만으론 부족.

## Alternatives
- if/elif 도메인 분기 코어 내장 → §10.12 위반으로 기각.
- entry-points 기반 무거운 플러그인 → soft-import ENV 한 줄로 충분, 기각.

## References
- `src/autonexusgraph/agents/_domain_handler.py` · `src/{autograph,ipgraph}/agent_handler.py` · [mental_model §2.2.2](../mental_model.md) · README §10.12/§12.5

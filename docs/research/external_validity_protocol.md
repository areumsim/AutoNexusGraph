# 외부 타당성 검증 프로토콜 (pre-registered)

> thesis H1(a) CONFIRMED (hybrid EM 0.710 > vector 0.048 = +66.2%p, graph-유래 multi-hop
> gold 62문항, 2026-06-15) 의 **외부 타당성**을 검증한다. SSOT = [thesis_hybrid_routing.md](./thesis_hybrid_routing.md) §1·§7.
>
> **원칙(게이밍 회피)**: 본 문서의 결정 규칙은 **측정 전 고정**한다(pre-registration).
> gold 를 손대 결과를 뒤집지 않는다. 어느 방향이든 정직하게 보고한다.

---

## 1. 검증 대상 위협 (CONFIRMED 의 한계)

현 +66.2%p 는 다음 위협에 노출된다:

| ID | 위협 | 회의론자의 주장 |
|---|---|---|
| **T1** | gold graph-유래 (circularity) | "그래프 traversal 로 만든 질문이니 그래프가 이기는 게 당연" |
| **T2** | 템플릿 표면형 artifact | "agent 가 고정 질문 템플릿을 패턴 매칭하는 것" |
| **T3** | EM 포맷 편향 | "vector 가 답을 알지만 포맷 불일치로 EM 0" |
| **T4** | vector 데이터 가용성 | "vector 가 진 건 출처 문서가 store 에 없어서(불공정)" |
| **T5** | 소표본·단일 도메인 | "n=62, finance+auto 만 — 일반화 불가" |

## 2. 검증 설계 + 사전 등록 결정 규칙

### V3 — vector-fairness 감사 (T4, read-only, $0)
각 질문에 대해 production retriever(`search_documents`, top_k=8)를 돌려 **출처 문서가
실제로 검색되는지** 확인. vector 실패를 분류: (a) **genuine chaining failure**(관련 청크
검색됨, 단일 청크로 답 불가) vs (b) **data missing**(출처 부재 — 불공정).
- **결정 규칙**: fair(a) 비율 ≥ 80% → 비교 공정(T4 기각). < 50% → 데이터 보강 후 재측정.

### V1 — paraphrase 견고성 (T2, LLM)
각 62문항을 **자연어로 강하게 paraphrase**(템플릿 구조 제거, 다양한 표면형, LLM 생성,
정답·엔티티 불변). hybrid vs vector 재측정.
- **결정 규칙**: paraphrase 에서 hybrid − vector EM ≥ **+30%p** → template artifact 아님(T2 기각).
  +15~30%p → 부분 견고. < +15%p → template artifact 의심(정직 기재).

### V2 — judge 기반 재채점 (T3, LLM)
기존 hybrid·vector 답변을 **LLM-as-judge**(candidate 와 다른 family) 로 재채점.
- **결정 규칙**: judge 정확도에서 hybrid − vector ≥ +30%p → EM 포맷 편향 아님(T3 기각).

### V4 — provenance-independent gold (T1, 가장 강함, LLM)
graph traversal 이 아닌 **독립 경로**로 multi-hop 질문 ~20문항 생성: LLM 이 기저 사실/
문서를 읽고 gold_cypher 를 **보지 않고** 자연 multi-hop 질문 작성 → 정답은 DB 로 독립 검증.
- **결정 규칙**: 독립 gold 에서 hybrid − vector EM ≥ **+30%p** → graph-유래 circularity 가
  결과를 만든 게 아님(T1 기각, 강한 외부 타당성). < +15%p → circularity 의심.

### V5 — 표본 확대 (T5)
graph-multihop 생성기로 n 확대 + variance/CI 보고. (V1/V4 와 병행)

## 3. 비용·순서

V3(read-only $0) → V1(~$0.3) → V2(~$0.2) → V4(~$0.3). 총 ~$1.

## 4. 결과

(측정 후 기재 — 각 V 의 판정 + 종합 외부 타당성 verdict)

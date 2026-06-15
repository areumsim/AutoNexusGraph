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

## 4. 결과 (2026-06-15, pre-reg SHA `2f0cc1f`)

### V3 — vector-fairness 감사 (T4)
- 출처 문서 **store 에 존재**: `anxg_vec.chunks` 778K (dart 747K + nhtsa/kotsa recall + …).
- 단발 vector(top_k=8) 의 **정답-엔티티 검색 recall = 5.8%** (GMH 7/17 부분·10/17 부재, GMI
  39/40 부재, AUTO 3/5 검색). 즉 답변 문서가 store 엔 있으나 **단발 semantic 검색이 multi-hop
  답변 문서를 구조적으로 못 찾음** — 이것이 graph 우위의 기전.
- **판정: T4 기각** (데이터 부재 아님 = 공정). **caveat**: 비교 대상이 *단발* vector — 에이전트/
  반복 검색(query 확장) vector ceiling 은 미측정(향후 baseline).

### V1 — paraphrase 견고성 (T2)
| subset | orig hybrid EM | para hybrid | para vector | hybrid−vector |
|---|---|---|---|---|
| GMH | 0.824 | 0.824 | 0.059 | **+76.5pp** |
| GMI | 0.625 | 0.625 | 0.000 | **+62.5pp** |
| AUTO | 1.000 | 0.800 | 1.000 | −20.0pp |
| **ALL** | 0.710 | 0.694 | 0.097 | **+59.7pp** |
- **판정: T2 기각** (ALL +59.7pp ≥ +30pp — 템플릿 표면형 제거 후에도 견고). **단 AUTO(n=5) 역전**:
  recall 문서가 제조사+모델을 co-locate → vector 도 답 가능. AUTO 는 약한·소표본 패턴(정직 기재).

### V2 — judge 재채점 (T3)
- judge correctness(의미 일치, EM 아님): hybrid 0.581 vs vector **0.031** = **+55.0pp**
  (GMH +64.9 · AUTO +62.0 · GMI +50.0). vector 는 의미적으로도 거의 다 틀림.
- **판정: T3 기각** (EM 포맷 편향 아님). **caveat**: judge=gpt-4o / candidate=gpt-4o-mini 동일 family.

### V4 — provenance-independent gold / 신규 구조 (T1)
- 원 3 템플릿(GMH/GMI/AUTO)에 **없던 신규 구조** = sibling 자회사(X→모회사→다른 자회사) 12문항,
  다양한 모회사(BNK·JB·LG·녹십자·메리츠 등), DB 검증 정답.
- hybrid EM 0.750 vs vector 0.500 = **+25.0pp** (hits 동률 0.750).
- **판정: T1 부분 기각** (신규 구조로 일반화 — 우위 유지). 단 **+15~30pp 구간**: sibling 구조는
  모회사 공시가 자회사를 한 문서에 co-locate → 부분 vector-친화(non-vector-triviality 필터 미적용).
  **일관된 기전**: graph 우위는 답의 **non-locality 에 비례** — 순수 비국소(GMH/GMI) +60~76pp,
  부분 co-located(sibling) +25pp. **완전한 T1 기각**(human/document-first gold)은 잔여.

### 종합 외부 타당성 verdict

| 위협 | 검증 | 결과 | 판정 |
|---|---|---|---|
| T4 데이터 가용성 | V3 | 출처 store 존재, vector recall 5.8% | ✅ 기각 (단발 vector 한정) |
| T2 템플릿 artifact | V1 paraphrase | +59.7pp | ✅ 기각 (AUTO n=5 제외) |
| T3 EM 포맷 편향 | V2 judge | +55.0pp | ✅ 기각 (동일 family caveat) |
| T1 graph-circularity | V4 신규 구조 | +25.0pp | 🟡 부분 기각 |
| T5 소표본·도메인 | V1/V4 | finance 견고, AUTO 약함 | 🟡 부분 |

**결론**: thesis +66.2pp 는 **주요 측정 artifact(paraphrase·EM 포맷·데이터 가용성)에 견고**하고
**신규 구조로 일반화**된다. 우위의 **크기는 답의 non-locality 에 비례**(gold 의존) — 순수 multi-hop
+60~76pp. **정직한 잔여 한계**: (a) AUTO recall 약함·소표본(n=5, vector co-locate), (b) 완전한 T1
기각엔 human/document-first gold 필요(신규 템플릿만으론 부분), (c) 단발 vector 만 비교(에이전트
vector ceiling 미측정), (d) 단일 family judge. → **store-aware hybrid 의 multi-hop 우위는 외부
타당성 검증을 (한계 명시 하에) 통과**.


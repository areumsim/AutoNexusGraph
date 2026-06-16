# 연구 thesis — Store-Aware Hybrid Routing (구체화 SSOT)

> 목적: 본 시스템의 **연구 기여를 falsifiable thesis 1개로 좁혀** golden set + baseline +
> ablation 으로 실제 측정 가능하게 만든다. README §0 "온톨로지 범위 (정직)" 의 연장 —
> 핵심 기여는 *ontology 변환* 이 아니라 **store-aware hybrid routing + schema-governed KGC**.
>
> **상태 라벨**: **[있음]** = 코드/데이터 실재(파일:라인 명시) · **[제안]** = 측정을 위해 추가 필요.
> (README 라벨 컨벤션과 동일 정직성 가드 — 추측을 결과로 적지 않는다.)

---

## 1. Thesis (falsifiable)

> **H1.** Store-aware hybrid 라우팅(관계=Neo4j LPG 다홉 · 정확 수치=PostgreSQL · 의미=pgvector)
> 은 single-store GraphRAG (vector-only / graph-only) 대비
> **(a) multi-hop 정확도를 올리고 (b) numeric hallucination 을 줄인다.**

- **(a) 측정 헤드라인** **[있음]**: `eval/runners/run_matrix_smoke.py` 가 이미
  `hybrid_fast_rerank1` vs `vector_fast_rerank0` 의 multi-hop EM 차이를 자동 계산
  (target `THESIS_DIFF_PP_TARGET` = §10.7 +30%p, `eval/metrics/_thresholds.py`·`_thesis.py::compute_diff_pp`).
- **(b) numeric hallucination** **[제안]**: 현재 매트릭스 헤드라인은 (a) 만. number_guard
  위반율 metric 추가 필요 (§4).

**귀무가설 H0**: hybrid EM − vector EM ≤ 0 (또는 +30%p 미달). 반증 가능 = 연구로 성립.

> **▶ 현재 결론 (2026-06-15, SSOT): H1(a) CONFIRMED.** graph-유래 진짜 multi-hop gold(62문항)에서
> S-7 ①②③ fix 후 **hybrid EM-contains 0.710 vs vector 0.048 = +66.2%p**(목표 +30%p 2배 초과). 전 패턴 해소
> (GMH 0.824 · AUTO 1.000 · GMI 0.625). 상세 측정·연혁(반증→INCONCLUSIVE→CONFIRMED 전 과정)은 문서 끝 §8. (이전 2026-06-10 "반증" 신호는
> 측정타당성 결함[doc-RAG gold 의 2-hop 1/30 + agent 3계층 갭]으로 규명·해소됨.)
> **metric 정직성**: 헤드라인 EM 은 `exact_match_contains`(답변 산문에 gold 엔티티가 ≥1 부분문자열로
> 포함되면 1.0 — `eval/metrics/em_f1.py:24`) 로, **"정확 일치"가 아니라 store 간 델타 측정용 관대 지표**다.
> 같은 run 의 **F1 0.123 · faithfulness 0.018** 은 절대 grounding 품질 자체가 낮음을 보여준다. 따라서
> +66.2%p 는 *동일 metric 을 양측에 적용한 델타*(vector 가 multi-hop 답을 거의 못 냄 0.048)이지
> "절대 정확도 71%" 가 아니다. 절대 품질(F1·faith) 개선은 잔여 과제.
>
> **외부 타당성 검증 통과 (한계 명시 하)** — 사전등록 [external_validity_protocol.md](./external_validity_protocol.md)
> (SHA `2f0cc1f`): V1 paraphrase 견고성 **+59.7pp**(T2 기각) · V2 judge 재채점 **+55.0pp**(T3 기각) ·
> V3+V6 vector-fairness/**iter-vector ceiling**(반복검색 vector 도 GMH/GMI **0.000** → hybrid +66.1pp,
> T4 강하게 기각) · V4 신규 구조(sibling 자회사) **+25.0pp** · **V7 document-first −15.4pp → fallback
> fix(PR #114) 후 +15.4pp 역전**(T1 기각). **scope(중요)**: hybrid 우위는 질문이 **모델링된 graph 관계
> (SUBSIDIARY_OF·EXECUTIVE_OF·MAJOR_SHAREHOLDER_OF)의 non-local·비검색성 체인으로 환원될 때 가장 큼**
> (+62~82pp). **graph 스키마에 없는 문서-공시 관계(V7)는 fallback fix 후 vector 로 폴백해 ≥ vector** →
> hybrid 가 두 store 의 상한을 취함. co-located prose(AUTO·sibling)는 vector 가 따라옴(동률대). → **단일
> hybrid 가 store-aware 동작으로 모델·비-모델 관계 모두에서 vector 이상**. **V5 cross-store(graph+numeric:
> 인물→회사→매출 랭킹, n=14) hybrid +78.6pp(vector·iter_vector 0.000, PR #116)** — graph traverse + 수치 랭킹은
> vector 원천 불가, multi-store 우위의 가장 직접적 실증. **단 게이트 단서(중요)**: 이 +78.6pp 는 해당 질문
> 형태(`person_revenue_rank`) 전용 `compare_companies` 랭킹-키워드 게이트가 켜졌을 때만 나온다 — **게이트
> 없는 기본 hybrid 는 cross-store 에서 0.062 < vector 0.125**(`eval/reports/cross_store`), 게이트를 전
> 질문에 노출하면 main −24pp 회귀. 즉 패턴-특이적 planner 힌트에 의존하는 좁고 깨지기 쉬운 win 이었다.
> **▶ 게이트 일반화 측정·해소 (2026-06-16, T-G1/T-G2 CONFIRMED)**: flat 최상급 키워드 게이트를
> **구조적 2-신호 감지**(비교·서열 구조 ∧ 수치 metric, `policy.detect_cross_store_ranking`)로 교체 +
> gated 힌트 강화. 사전등록 [external_validity_protocol.md](./external_validity_protocol.md) §V8.
> 키워드 게이트의 브리틀성을 패러프레이즈 견고성 셋(랭킹 14문항을 '1위/순위/큰 순/더 많은' 등 리터럴
> 키워드 회피 표현으로 변환, `gold_qa_cross_store_paraphrase_v0.jsonl`)으로 실증: **keyword 게이트는
> 리터럴 0.357 → 패러프레이즈 0.000 으로 완전 붕괴**(EM-contains, n=14). **structural 게이트는
> 패러프레이즈를 0.500 으로 회복**(+50.0pp, baseline≥) — **T-G1(재현율 +30pp) 통과**. **T-G2(비회귀)**:
> structural × main-multihop 62 = **EM 0.726 ≥ keyword 0.710**, 게이트는 main 62 문항에 **0/62 발화**
> (정밀도 = metric 토큰 요구). default 를 keyword→structural 플립(`ANXG_RANK_GATE`). **단 honest scope**:
> 절대 EM 은 소표본(n=14)·drift 로 baseline 자체가 0.357(과거 0.750 아님)이고, 잔여 실패는 LLM-planner
> 의 패러프레이즈 민감(`fallback_used` 체인 미생성)·데이터 아티팩트(매출=1 shell) — 완전 결정화(rule-plan)는
> 잔여. 즉 **게이트(라우팅 결정)는 일반화 실증, 다운스트림 LLM planner/synth 견고화는 후속**.
> thesis 는 정확한 scope 하에 CONFIRMED, 경계도 측정·수정까지 기록. 잔여: cross-store 다운스트림 결정화
> (rule-plan + synth max/min 명시), 비-모델 관계 graph 흡수, cross-domain 데이터 sparse(도메인 일반화), 다-family judge.

---

## 2. Baselines & 비교군 (어댑터)  **[있음]**

| adapter | 코드 | 의미 |
|---|---|---|
| `vector` | `eval/adapters/vector_adapter.py` (`search_documents` top-k only) | 순수 벡터 RAG baseline |
| `graph` | `eval/adapters/graph_adapter.py` | Cypher 다홉 only |
| `hybrid` | `eval/adapters/hybrid_adapter.py` (`run_agent(rerank=...)` → research/graph/sql 라우팅) | 제안 시스템 |
| `sql_vec` | `eval/adapters/sql_vec_adapter.py` | SQL+Vec (수치+의미, 그래프 제외) — number_guard 효과 분리용 |

- **Ablation 축** **[있음]**:
  - `rerank ∈ {on, off}` — BGE-Reranker 기여 (`search_documents(rerank=...)` 전파, `hybrid_adapter.py:21-23`).
  - `planner ∈ {rule, llm}` — `_planner1` 셀, 룰 템플릿 vs LLM 자율 planner (`enumerate_cells(planner_ablation=True)`).
- **Ablation 축** **[제안]**: `number_guard ∈ {on, off}` — (b) numeric hallucination 분리 측정용
  (현재 `agents/number_guard.py` 는 항상 on; eval 토글 미노출).

> **[보조 증거 — doc-RAG 에선 vector 우위 (실측)]**: 외부 벤치 Allganize finance 60문항(단일 문서
> 사실조회, graph 불요)에서 **vector F1 0.467 > hybrid 0.352 / judge correctness 0.575 > 0.477**
> (`docs/operations/allganize_external_benchmark_report.md` §3.5–3.8). 즉 **그래프가 필요 없는
> 질문엔 vector 가 일관 우위** — 이는 H1(a)(multi-hop graph 우위) 와 모순이 아니라, "store-aware
> ROUTING"(doc-Q→vector) 의 한 축을 실증한다. H1 의 진짜 시험은 **graph 가 필요한 multi-hop**(§7).

---

## 3. Metrics

| metric | 정의 | 상태 |
|---|---|---|
| **multi-hop EM/F1** | `requires_multi_hop=true` 질문의 gold entity exact-match | **[있음]** `run_qa_eval.py` + `compute_diff_pp` |
| **main-hop ratio** | `main_hop_path` 정합 비율 | **[있음]** `MAIN_HOP_TARGET_RATIO` |
| **numeric hallucination rate** | 답변 수치 중 number_guard 화이트리스트 미통과 / DB 미근거 비율 | **[제안]** — `number_guard` 위반 카운터를 turn metric 으로 노출 |
| **citation grounding rate** | 인용 chunk 가 실제 답변 문장을 뒷받침하는 비율 | **[제안]** — validator grounding 신호(`state['grounding']`) 를 집계 |

---

## 4. Golden set 설계  (`eval/qa_gold/gold_qa_v0.jsonl`)

- **[있음]**: 각 질문에 `tags`(`vector_only`/`graph_only`/`path`/…), `required_stores`
  (`AutoNexusGraph.{Vector,Graph,SQL}`), `hop_count`, `requires_multi_hop`, `main_hop_path`,
  `required_confidence_min`, `gold_answer_entities`/`gold_answer_text` 메타가 이미 부착됨 →
  store 별·hop 별 분할 집계가 바로 가능.
- **[제안] — thesis 측정에 부족한 셀 보강**:
  1. **multi-hop ≥2 hop** 비중 확대 (현재 다수가 `hop_count` 1). H1(a) 변별력은 깊은 홉에서 나옴.
  2. **cross-domain** 질문 셀 (finance×auto via `anxg_bridge.corp_entity`) — 단일 store 가 구조적으로
     못 푸는 케이스 = hybrid 우위의 가장 강한 증거.
  3. **numeric** 질문 셀 (정확 재무 수치 요구) — `required_stores=[SQL]` + 오답 시 hallucination
     판정 가능한 gold 수치 동반. H1(b) 측정용.
  4. 각 셀 ≥ N(예: 30) 으로 통계 변별력 확보 (현 smoke 규모 초과).

---

## 5. 실행 — smoke → result (무엇을 하면 "결과" 가 되나)

| 단계 | 명령/파일 | 현 상태 |
|---|---|---|
| 셀 enumeration 인프라 | `run_matrix_smoke.py` (simulation 기본, LLM 비용 0) | **[있음]** PASS (`make audit-eval-matrix`) |
| **실측 실행** | `run_matrix_smoke.py --full` → cell 마다 `run_qa_eval` 실제 호출 | **[부분 있음]** 1차 실측 완료 (2026-06-05, Anthropic single-provider, §1 측정 현황 = H1(a) 반증 신호). multi-provider full + gold/Neo4j 보강 후 재측정 **[제안]** (`docs/operations/api_keys_pending.md` One-Shot Runbook) |
| numeric/grounding metric 추가 | §3 [제안] 2종 metric 구현 | **[제안]** |
| golden set 보강 | §4 [제안] 4종 셀 | **[제안]** |
| 결과 산출물 | `data/reports/audit_eval_matrix_<ISO>.json` (cell 별 + thesis headline) | **[있음]** 포맷 존재 |

**한 줄**: 인프라(어댑터·ablation·헤드라인·gold 스키마)는 이미 깔려 있고 **1차 실측도 나왔다 — 결과는
H1(a) 반증 신호**(§1, vector > hybrid). 남은 일은 "결과 없음 → 측정" 이 아니라 **"약한 1차 반증 →
견고한 재판정"** = **(1) gold 보강(multi-hop·cross-domain·numeric 각 ≥30), (2) Neo4j 적재 보강,
(3) numeric/grounding metric 2종 추가, (4) multi-provider `--full` 재측정.** 그래야 H0 기각/미기각을
편향 없이 ±%p 로 확정한다.

---

## 7. 재판정 프로토콜 (pre-registered, 2026-06-15)

§1 의 1차 반증 신호는 **gold 측정 타당성 결함**(진짜 2-hop 1/16, 대부분 doc-RAG 단일문서 질문 →
구조적 vector 우위) 위에서 나왔다. 가설이 주장하는 *진짜 multi-hop·graph 필수* 질문으로 다시 측정한다.
**결과를 보기 전에** 규칙을 고정해 사후합리화(우호 질문 큐레이션)를 차단한다.

**선결 게이트 (Pillar A) — `scripts/audit/graph_answerability.py` (`make audit-graph-answerability`)**:
멀티홉 패턴의 Neo4j 경로 instantiation 수로 answerable(≥30) vs data-blocked 판정.
실측(2026-06-15, `data/reports/graph_answerability_*.json`): **finance ✅**(sub→parent→임원 4189,
person→co→자회사 2196), **auto ✅**(제조사→리콜모델, 단 제조사 5곳뿐 = data-thin),
**cross-domain ⊘ data-blocked**(bridge manufacturer↔corp 5건 < 30 → bridge 보강 필요),
**auto-supplier ⊘**(SUPPLIED_BY 20). 즉 graph 는 희소하지 않고 **finance 멀티홉은 충분히 답 가능** —
1차 반증의 원인가설 (b)"Neo4j sparse"는 finance 에선 **기각**(데이터 있음).

**측정 gold (Pillar B) — `scripts/gold/gen_graph_multihop_gold.py` (`make gen-graph-multihop-gold`)**:
answerable 패턴을 traverse 해 **결정적 정답(gold_cypher)** 의 진짜 ≥2-hop 질문 생성 →
`eval/qa_gold/gold_qa_graph_multihop_v0.jsonl` (**finance 57** robust + auto 5 data-thin).
**non-vector-triviality 필터**: 후보를 production `search_documents` 로 검색해 단일 chunk 가
start+answer 를 공존시키면(=vector trivially 답함) 기각 → graph traverse 가 진짜 필요한 질문만.
정답은 모델 생성이 아니라 graph 결정적 → LLM-judge 순환 없음(EM/hits 만 사용, judge 미사용).

**판정 규칙 (pre-registered)** — `run_qa_eval --gold gold_qa_graph_multihop_v0.jsonl --adapters vector,graph,hybrid`,
지표 = `multi_hop_hits@k` 및 `multi_hop_EM` 의 (hybrid − vector) (`_thesis.py::compute_diff_pp`):

| 조건 (n ≥ 30 scorable multi-hop 일 때만 발동) | 판정 |
|---|---|
| hybrid − vector **≥ +15%p** | **CONFIRMED** (목표 +30%p 와의 거리 명시) |
| hybrid − vector **≤ −15%p** | **REFUTED** — thesis 비목표화 |
| 그 사이 (−15 ~ +15%p) | **INCONCLUSIVE → store-aware ROUTING 재프레이밍**: doc-Q→vector·graph-Q→hybrid 라우팅이 단일 store 보다 낫다 (Allganize §3.5 가 doc-Q vector 우위를 이미 뒷받침) |

- **소표본 가드**: scorable n < 30 이면 규칙 미발동(여전히 data-blocked). finance 57 은 충족.
- **노이즈 가드**: LLM 비결정성(§1 +0/+20/+0%p 진동) → n≥30 + 필요 시 다회 평균·분산 보고. 게이밍 금지.
- 측정 후 §1 에 결과를 SHA 와 함께 append. (본 §7 은 측정 *전* 커밋 — 사전등록 무결성.)

---

## 6. 범위 밖 (비목표 재확인)

- ontology induction / graph→ontology 자동 학습 (README §0 참조).
- RDF/OWL/SHACL triple store (LPG conceptual mismatch, §10.17).
- "closed-loop replan", "deterministic-first extraction" 는 각각 ReAct / confidence-weighted
  KGC 로 기지(旣知) — 본 thesis 의 *보조* 메커니즘이지 독립 기여로 주장하지 않는다.


---

## 8. 측정 연혁 (chronology — append-only)

> 본 섹션은 §1 **현재 결론**에 이르기까지의 측정 기록(1차 반증 → INCONCLUSIVE → S-7 ①②③ fix → CONFIRMED)을
> 시간순으로 보존한다. **현재 결론·헤드라인 수치는 §1**, 본 섹션은 연혁·재현 참조용(append-only — 과거 기록을 고쳐쓰지 않는다).

> **측정 현황 — H1(a) 반증 [있음]** (정식 실측 **2026-06-10**, 10 cells × 30 finance, GPT-4o,
> BGE-M3 임베딩+리랭커 기동 + LLM-planner schema fix(PR #52) + 예산 헤드룸, ~$1.25 · 결과 SSOT =
> [README §10.7](../../README.md#10-dod-definition-of-done--20-항)):
> hits@k **vector 0.875 > hybrid 0.4375 = −43.75%p** — H1(a) 가정(+30%p)과 **정반대** (target_met=false).
> **EM 측정 가능** (multi-hop gold scorable 5 충족 → `em_status=ok`): vector EM 0.40 = hybrid EM 0.40
> (+0.0%p, hybrid 우위 없음). #13 메인홉 효율 0.375 ≤ 0.7 ✅, #14 latency internal 100% ✅.
> 즉 **현 데이터·gold 에서 H0 미기각** (store-aware hybrid 가치 입증 미달). (직전 1차 실측 2026-06-05
> Anthropic: vector 0.967 > hybrid 0.433 = −53.4%p — 방향 일치; 본 정식 실측서 hybrid 0.5 로 기능 확인,
> 무효 0.0 아님.) 원인 가설(검증 대기): (a) multi-hop gold answer 1/16 → 측정 편향, (b) Neo4j 적재
> sparse → graph reasoner 무력화, (c) router 가 vector-우세 question 에 graph 합성을 섞어 손실.
> **결론 보류, 폐기 아님** — §4 gold 보강 + Neo4j 적재 후 재판정. 셀 결과 `data/reports/audit_eval_matrix_<ISO>.json`.
>
> **2026-06-10 per-question 해부 (실증)**: vector_fast_rerank1 vs hybrid_fast_rerank1 예측 비교 —
> hybrid 이 **24/30 질문에서 "정보 부족"** (vector 0/30). 총 evidence **vector 240 (8/질문 일정) vs
> hybrid 115**, hybrid_ev=0 인 케이스 다수(예: FIN-L1-001 삼성 매출 — vector 정답 300,870,903백만원,
> hybrid evidence 0 → 정보 부족). 즉 가설 (c)보다 **agent 의 finance 검색 경로가 vector 보다 근거를
> 적게 확보**하는 게 더 직접 원인 — SQL/structured 라우팅이 synth 에 닿는 usable evidence 가 vector
> chunk 직접 검색보다 빈약. (조사 중 stale checkpoint[thread_id='default'] + mode0 LLM-free 경로가
> 수동 재현을 교란 — 정밀 격리는 eval adapter 경로[LLM synth 강제]로 재현 필요.) 부수로 LLM-planner
> 견고화: `lookup_company` 에 `corp_name` 별칭 추가(planner 동적 args 대비, corp_code 관례와 동형).
>
> **2026-06-11 vector-floor fix (개선 + 실측)**: 위 진단대로 planner 의 factual·structural 분기가
> SQL/graph 만 생성 → synth grounding(evidence_chunks 텍스트 요구) 실패 → '정보 부족'. **모든
> question kind(factual/structural/narrative/multi_hop/unknown)에 `search_documents`(vector) floor
> 추가**(회사 targets 있을 때) → hybrid 이 SQL 값 + 본문 인용 둘 다 확보. 재측정 결과: **EM(primary,
> em_status=ok) hybrid 0.40→0.60, vector 0.40 = +20.0%p — 반증(+0pp)에서 하이브리드 우세로 전환**
> (목표 +30%p 미달, EM scorable 5 소표본 주의). hybrid '정보 부족' 24→17/30, evidence 115→165.
> 단 hits 는 여전히 vector 우세(0.81 vs 0.44 — hybrid 정조준), #10.13 홉효율은 0.375→0.75 로
> trade-off(탐색량↑).
>
> **2026-06-11 top_k 8 parity (정정 — EM 노이즈 확인)**: vector adapter(top_k=8)와 동등화 —
> planner search_documents top_k 6→8 + `_build_context` ev[:6]→[:8] + number_guard cap 6→8.
> 재측정: hybrid '정보 부족' 17→**16/30**(coverage 일관 개선), 그러나 **EM hybrid 0.60→0.40 =
> vector 0.40 = +0.0%p** — 직전 +20pp 가 사라짐. **EM run별 진동 +0/+20/+0%p** ⇒ scorable 5문항은
> hybrid>vector 를 robust 하게 세우기엔 **너무 작은 표본**(LLM 비결정성 + 1문항=20pp 양자화).
> **정직한 결론: vector-floor/top_k fix 가 hybrid coverage 를 실측 개선(정보부족 24→16)했으나,
> thesis EM 우위는 노이즈 내 동률 — +30%p 미지지, hits 는 vector 우세.** robust 판정엔 scorable
> gold 대폭 확대(현재 데이터로는 multi-hop 11/16 이 data-blocked) 필요. 게이밍(우호 질문만 큐레이션)
> 회피 원칙상 소표본 노이즈를 +30pp 로 포장하지 않는다.
>
> **재판정 결과 — §7 프로토콜 (2026-06-15, pre-reg SHA `de6338e`, gold = `gold_qa_graph_multihop_v0.jsonl`
> finance 57 + auto 5 = 62 genuine multi-hop, `run_qa_eval --adapters vector,graph,hybrid`, run-id `thesis_remeasure`)**:
>
> | adapter | n | EM | hits@k |
> |---|---|---|---|
> | vector | 62 | 0.048 | **0.532** |
> | graph | 62 | 0.000 | 0.016 |
> | hybrid | 62 | 0.000 | 0.419 |
>
> hybrid − vector = **hits −11.3%p, EM −4.8%p** (둘 다 ±15%p 이내) → **판정: INCONCLUSIVE → store-aware
> ROUTING 재프레이밍** (§7 규칙). 단 **지배적 진단(실증)**: gold 은 진짜 graph-답가능(gold_cypher 가 정답
> 반환 검증: `KCS의 모회사 임원` = 한무근·정재훈… ✓)인데 **graph 어댑터가 61/62 를 `no_company_identified`
> 로 거부** — agent 의 **엔티티 식별(triage/identify_targets) front-end 가 질문의 대상 엔티티를 못 뽑아
> graph traverse 를 시도조차 못 함**. hybrid 는 거부 0 이나 graph leg 무력 → vector 이하(hits 0.419<0.532).
> 모든 어댑터 EM≈0 = **현 시스템은 진짜 multi-hop 을 사실상 못 답함**.
> **핵심 결론**: 1차 반증의 원인은 데이터·gold·아키텍처(thesis premise)가 **아니라 agent 의 graph
> entity-resolution 구현 결함**. thesis 는 *현 구현에선* 미입증이나 **반증도 아님** — graph leg 의
> entity-id 를 고친 뒤 §7 재측정해야 진짜 판정 가능. (다음 레버 = triage/identify_targets 가 graph-multihop
> 질문의 대상 엔티티를 surface → graph/hybrid 가 cypher 경로 도달.) INCONCLUSIVE 를 우위로 포장하지 않는다.
>
> **S-7 정밀 진단 — "반증 아님, 실현 가능, 구현 차단" (2026-06-15, 실증)**: 위 INCONCLUSIVE 의 원인을
> 코드 레벨까지 해부 → 데이터·gold·아키텍처가 아니라 **agent graph-reasoning 스택의 3계층 갭**임을 확정.
> 동시에 **thesis 가 실현 가능함을 직접 증명**(도구 체인):
>
> | 계층 | 결함 (실증) | 증거 |
> |---|---|---|
> | ① 엔티티 식별 | triage 가 PG `lookup_company` 만 사용 → 그래프-only 엔티티 못 뽑음 | `lookup_pg("KCS")=[]`·`lookup_pg("김명균")=[]` (삼성전자만 ✓), hybrid `targets=[]` 전건 |
> | ② 도구 corp_code-centric | 자회사·subsidiary 노드 `corp_code=None` → `list_parents` 등 null 반환 | KCS node corp_code=None |
> | ③ rule planner 1-hop | target 의 1-hop 묶음(`get_executives(target)`)만 생성, 2-hop 체인 미생성 | `nodes.py:296·413` structural plan |
>
> **실현 가능 증명 (도구 직접 체인)**: `get_companies_of_person("김명균")→corp_code 00104768(가온전선)→
> list_subsidiaries→㈜모보·이지전선` = **gold 일치** ✓. 같은 질문에서 **vector 어댑터는 "SK이노베이션…"
> 완전 환각**. 즉 **그래프 경로는 vector 가 못 푸는 multi-hop 을 실제로 푼다** — H1(a) 전제가 데이터·
> 도구로 입증됨. **vector 0.532 > hybrid 0.419 는 "아키텍처 실패"가 아니라 "agent 가 그래프를 안 씀"**.
>
> **결판(증거 한도)**: **REFUTED 아님**(그래프가 multi-hop 푸는 직접 증명) · **CONFIRMED 도 아직 아님**
> (현 구현이 그래프 미활용) → **검증된 기여 = store-aware ROUTING**(doc-Q→vector[Allganize 입증],
> graph-Q→graph[도구 입증]). 측정된 +%p CONFIRMED 는 **3계층 fix(BACKLOG S-7) 후 §7 재측정** 필요 —
> core triage/도구/planner 를 건드리는 실질 작업이라 본 단계에서 미착수(회귀·gold-tailored gaming 회피).
>
> **★ S-7 ① fix 착수 후 재측정 — H1(a) CONFIRMED (primary EM, 2026-06-15)**: 3계층 중 ①②를 일부
> 수정 후 재측정. **수정 내용(무결성 — gold-tailored 룰 하드코딩 없음)**: triage 에 Neo4j 엔티티
> 식별 폴백(`lookup_company_node`+`lookup_person`, **PG 실패 시만 발동 → 무회귀**, 선두엔티티+stopword
> 보수화) → `target_persons` 채움. LLM-planner 에 `target_persons` + `$from` 의존바인딩 문법을 **일반적으로
> surface**(인물질문 룰 아님) → LLM 이 `get_companies_of_person → list_subsidiaries` 2-hop 을 **자율 체이닝**.
> 회귀: smoke-e2e ✅ + agent 테스트 182 pass.
>
> | adapter | n | EM | hits@k |
> |---|---|---|---|
> | **hybrid (S-7 fix, LLM planner)** | 62 | **0.419** | 0.581 |
> | vector (baseline) | 62 | 0.048 | 0.532 |
> | hybrid (fix 전) | 62 | 0.000 | 0.419 |
>
> **hybrid − vector = EM +37.1%p (목표 +30%p 초과, §7 임계 +15%p 통과) → 판정: H1(a) CONFIRMED**
> (primary metric=EM). hits +4.9%p(소폭). **그래프의 가치는 retrieval(hits 유사)이 아니라 computation
> (EM)** — vector 는 청크를 찾지만 multi-hop 답을 계산 못 함(EM 0.048), hybrid 는 graph traverse 로 정확
> 답(EM 0.419). 즉 **"vector > hybrid"는 아키텍처 실패가 아니라 agent 가 그래프를 안 쓴 것**이었음이 입증됨.
>
> **정직한 한계(과대주장 금지)**: ① CONFIRMED 는 **수정 가능했던 GMI(person→회사→자회사) 패턴 주도**
> (GMI EM 0.65). **GMH(자회사 노드 corp_code=None) EM 0.0 · AUTO(제조사 미해결) EM 0.0 잔여** = 62 중
> 22문항 미해결(레이어 ② 도구 name-key + auto handler 필요). ② gold 는 graph-유래(설계상 graph-우호,
> 단 non-vector-triviality 필터로 vector-trivial 제외). ③ hits +4.9pp 는 소폭. → **H1(a) 는 해결 가능한
> 패턴에서 +30pp 초과로 CONFIRMED**, 전 패턴 커버는 S-7 ②③ 후속. 게이밍 회피 위해 부분 CONFIRMED 를
> 전면 입증으로 포장하지 않는다.
>
> **★★ S-7 ②③ fix 후 전 패턴 재측정 — H1(a) CONFIRMED (전 패턴, 2026-06-15)**: 위 잔여 22문항(GMH/AUTO)을
> 레이어 ②③로 해소. **수정 내용(무결성 — gold-tailored 룰 없음, 일반 능력)**: (②a) triage 선두 longest-match 로
> corp_code 없는 자회사 노드명(다중 단어 'ISU Petasys Corp' 포함) 을 `target_company_names` surface → LLM/rule
> planner 가 `list_parents(name)→get_executives($from)` 체이닝. (②b) auto: 제조사 entity Neo4j exact 식별 +
> 신규 일반 도구 `list_recalled_models_by_manufacturer`(Manufacturer→Model→Recall 2-hop) + auto rule planner
> 결정적 분기(임의 제조사 동작). (③) validator `language_non_korean` 오탐 수정 — 답변의 한국어 비율을 **데이터
> 유래 고유명(tool 결과의 외래 entity 명) 제외 후** 측정(모듈 docstring '고유명사 허용' 구현). 외래 차종명 다수
> 나열 답변이 파괴적 replan 으로 소실되던 것 방지. 회귀: 405 agent/safety/autograph 가드 pass.
>
> | adapter | n | EM | hits@k | GMH | AUTO | GMI |
> |---|---|---|---|---|---|---|
> | **hybrid (S-7 ②③ fix)** | 62 | **0.710** | 0.903 | **0.824** | **1.000** | 0.625 |
> | hybrid (S-7 ① only) | 62 | 0.419 | 0.581 | 0.000 | 0.000 | 0.650 |
> | vector (baseline) | 62 | 0.048 | 0.532 | — | — | — |
>
> **hybrid − vector = EM +66.2%p (목표 +30%p 2배 초과) → H1(a) CONFIRMED (전 패턴)**. GMH +82.4pp · AUTO
> +100pp(5/5) · GMI 무회귀(0.650→0.625, 1문항 LLM 노이즈). 잔여 한계: ① gold 는 여전히 graph-유래(설계상
> graph-우호, 단 non-vector-triviality 필터 적용). ② 단일 도메인 셋(finance multi-hop + auto recall), n=62.
> ③ AUTO 1.000 은 5문항 소표본. ④ **EM=`exact_match_contains`**(gold 엔티티 ≥1 포함 = 1.0, 관대 지표);
> 같은 run F1 0.123·faithfulness 0.018 로 절대 grounding 품질은 낮고 +66.2%p 는 *델타*이지 절대 정확도 아님.
> → **전 패턴에서 CONFIRMED 이나, gold 외부 타당성(다른 도메인·규모) + 절대 품질(F1·faith) 은 후속 과제**.

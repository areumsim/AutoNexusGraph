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

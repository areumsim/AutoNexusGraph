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

## 6. 범위 밖 (비목표 재확인)

- ontology induction / graph→ontology 자동 학습 (README §0 참조).
- RDF/OWL/SHACL triple store (LPG conceptual mismatch, §10.17).
- "closed-loop replan", "deterministic-first extraction" 는 각각 ReAct / confidence-weighted
  KGC 로 기지(旣知) — 본 thesis 의 *보조* 메커니즘이지 독립 기여로 주장하지 않는다.

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
  2. **cross-domain** 질문 셀 (finance×auto via `bridge.corp_entity`) — 단일 store 가 구조적으로
     못 푸는 케이스 = hybrid 우위의 가장 강한 증거.
  3. **numeric** 질문 셀 (정확 재무 수치 요구) — `required_stores=[SQL]` + 오답 시 hallucination
     판정 가능한 gold 수치 동반. H1(b) 측정용.
  4. 각 셀 ≥ N(예: 30) 으로 통계 변별력 확보 (현 smoke 규모 초과).

---

## 5. 실행 — smoke → result (무엇을 하면 "결과" 가 되나)

| 단계 | 명령/파일 | 현 상태 |
|---|---|---|
| 셀 enumeration 인프라 | `run_matrix_smoke.py` (simulation 기본, LLM 비용 0) | **[있음]** PASS (`make audit-eval-matrix`) |
| **실측 실행** | `run_matrix_smoke.py --full` → cell 마다 `run_qa_eval` 실제 호출 | **[제안]** LLM 키 + DB 적재 필요 (`docs/operations/api_keys_pending.md` One-Shot Runbook) |
| numeric/grounding metric 추가 | §3 [제안] 2종 metric 구현 | **[제안]** |
| golden set 보강 | §4 [제안] 4종 셀 | **[제안]** |
| 결과 산출물 | `data/reports/audit_eval_matrix_<ISO>.json` (cell 별 + thesis headline) | **[있음]** 포맷 존재 |

**한 줄**: 인프라(어댑터·ablation·헤드라인·gold 스키마)는 이미 깔려 있다. "측정 게이트만 깔린
상태" 를 "결과" 로 바꾸는 일 = **(1) --full 실측 (키+DB), (2) numeric/grounding metric 2종 추가,
(3) multi-hop·cross-domain·numeric gold 셀 보강.** 그러면 H1 을 ±%p 로 보고할 수 있다.

---

## 6. 범위 밖 (비목표 재확인)

- ontology induction / graph→ontology 자동 학습 (README §0 참조).
- RDF/OWL/SHACL triple store (LPG conceptual mismatch, §10.17).
- "closed-loop replan", "deterministic-first extraction" 는 각각 ReAct / confidence-weighted
  KGC 로 기지(旣知) — 본 thesis 의 *보조* 메커니즘이지 독립 기여로 주장하지 않는다.

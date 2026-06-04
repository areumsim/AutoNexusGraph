# Runbook Traces — 대표 질문 × 의도된 호출 sequence

> **본 문서의 위치**: 8 개 대표 질문이 시스템 안에서 **어떤 tool 호출 sequence + replan 발생 여부 + 실패 가능 지점** 으로 처리되는지 의도된 trace.
>
> **주의 — 시뮬레이션 trace**: 본 문서는 README §10.7/§10.13/§10.14 의 실측 (LLM 키 활성 후 측정) 이 아직 미실시이므로, **의도된 호출 흐름** (code-derived) 만 trace. 실측은 `make eval-full` / `eval-auto` / `eval-cross` 실행 후 `eval/reports/<run>/manifest.json` 으로 본 문서 갱신.
>
> **목적**: 시스템 자랑 ("3 도메인 한 turn 묶기") 의 실제 작동 메커니즘 시연. cold review ([docs/system_review.md](system_review.md)) 의 P0-(2) 항목 해소.
>
> 코드 SSOT: [docs/architecture.md §5](architecture.md) (StateGraph 11 노드 read/write) + [docs/api_reference.md](api_reference.md) (tool 시그니처).

---

## 0. trace 표 읽는 법

> **worker 종류 (사실 정정 2026-06-02)**: 실제 4 worker = `research_worker` / `graph_worker` / `sql_worker` / `calculator_worker` (`agents/workers.py`). **bridge tool 은 별도 worker 가 아니라 `sql_worker` 가 PG `bridge.corp_entity` 테이블을 SQL 로 조회**. 즉 `bridge_corp_to_entity` / `bridge_sec_cik_to_entity` / `bridge_corp_to_assignee` 모두 `sql_worker` intent.

각 trace 는 다음 항목으로 구성:
- **질문** — 사용자 발화
- **예상 도메인 라우팅** — `auto_detect_domain` 결과
- **planner DAG** — task list (id / agent / intent / depends_on)
- **호출 sequence** — supervisor round 별 worker dispatch
- **예상 cost (USD)** — `cost_estimator.py` 추정 (FAST tier 기준)
- **예상 latency** — README §10.14 목표 (도메인내 <8초 / Cross <12초)
- **실패 가능 지점** — 어디서 깨질 수 있는지
- **gold QA 매핑** — 본 trace 가 어느 gold row 와 대응

---

## 1. Finance — L1 (단순 사실)

### 질문: "삼성전자 2024년 매출은?"

| 항목 | 내용 |
|---|---|
| 라우팅 | `auto_detect_domain` → 키워드 부재 → `default = finance` |
| question_kind | `factual` (`classify_question` 의 KW_NUMERIC 키워드 매칭) |
| planner DAG | `[t1: sql_worker.lookup_company('삼성전자')] → [t2: sql_worker.get_revenue('00126380', 2024) depends_on=t1]` |
| supervisor round 1 | `Send(worker_sql, t1)` (의존성 없음) |
| supervisor round 2 | `Send(worker_sql, t2)` (t1 done 후) |
| synthesizer | `tool_results=[lookup, revenue]` → LLM 으로 한국어 답변 생성 |
| validator | length OK / language ≥ 0.30 / hallucinated_numbers (revenue 값 화이트리스트 ✓) → passed |
| 예상 cost | ~$0.002 (FAST tier Sonnet, 1 LLM 호출 = synthesizer 만 — worker 는 tool only) |
| 예상 latency | ~3초 (PG 조회 2 회 + LLM 1 회) |
| 실패 지점 | (a) `lookup_company` 모호성 (삼성+SDI/디스플레이/생명/물산 다수) → triage 가 HITL clarification interrupt 발동. (b) DART XBRL 의 IFRS 별도/연결 혼동 → 답변 paraphrase 부족 시 EM 실패 |
| gold QA | `gold_qa_v0.jsonl` FIN-L1 30 row 중 다수 |

---

## 2. Finance — L2 (2-hop, graph + financials)

### 질문: "삼성전자 자회사 중 매출 1조 이상은?"

| 항목 | 내용 |
|---|---|
| 라우팅 | `finance` |
| question_kind | `structural` (KW_STRUCTURAL "자회사") |
| planner DAG | `[t1: sql_worker.lookup_company('삼성전자')] → [t2: graph_worker.list_subsidiaries('00126380') depends_on=t1] → [t3: sql_worker.get_revenue(<for each child>) depends_on=t2]` |
| supervisor round 1~3 | t1 → t2 → t3 (3 round 순차, t3 는 N 개 child × N 호출 sequential 또는 batch) |
| cost | ~$0.01 (synthesizer 1 회 + LLM 미호출 worker N 회) |
| latency | ~5~7초 (자회사 N=20 가정 시 SQL N+2 회) |
| 실패 지점 | (a) `list_subsidiaries` 가 snapshot_year 미명시 → 최신 데이터로 fallback. (b) child_corp_code 가 null 인 자회사 (외국 자회사) → SQL 건너뜀 → 답변 누락. (c) **multi-hop** — multi_hop_em/f1 측정 subset |
| gold QA | `gold_qa_v0.jsonl` FIN-L2 |

---

## 3. Auto — L2 (recall + variant)

### 질문: "Hyundai Sonata 2024 ABS 관련 리콜 사례는?"

| 항목 | 내용 |
|---|---|
| 라우팅 | `auto_detect_domain` → `KW_RECALL` ("리콜") 매칭 → `auto` (실제 키워드 set 은 `src/autograph/policy.py` 의 `KW_AUTO_GENERIC` + `KW_RECALL` + `KW_COMPLAINT`. "Hyundai" / "Sonata" 는 키워드 아니지만 "리콜" 단일 매칭으로 auto 라우팅) |
| planner | `autograph.policy.plan_auto_tasks` — `classify_question_auto` = `vehicle_recall` → DAG: `[t1: sql_worker.lookup_vehicle('Sonata 2024')] → [t2: graph_worker.list_recalls_affecting(variant_id) depends_on=t1] → [t3: research_worker.search_documents_auto('ABS', variant_id=..., source='nhtsa_recall')]` |
| supervisor round 1 | `Send(worker_sql, t1)` |
| supervisor round 2 | `Send(worker_graph, t2)` + `Send(worker_research, t3)` (병렬) |
| cost | ~$0.005 |
| latency | ~6초 (pgvector 검색 + Cypher) |
| 실패 지점 | (a) "Sonata 2024" 모델 매핑 fuzzy (vPIC `SONATA` vs `Sonata Hybrid` 다중) → ambiguity warning. (b) `:Part` 노드 0 — ABS 부품 구체 못 찾음 → 리콜 campaign 본문에서 LLM 이 ABS 언급 chunk 만 인용 |
| gold QA | `gold_qa_auto_v0.jsonl` AUTO-L2 |

---

## 4. Auto — L3 (3-hop, supply chain)

### 질문: "현대모비스가 공급하는 차종 중 최근 리콜 사례는?"

| 항목 | 내용 |
|---|---|
| 라우팅 | `auto` — `KW_RECALL` ("리콜") 매칭. "모비스" / "공급" 은 키워드 set 에 없으나 "리콜" 단일 매칭으로 auto |
| planner | `classify_question_auto` = `supply_chain` → DAG 5 단계: `[t1: sql_worker.bridge_corp_to_entity('00164788', entity_type='supplier')] → [t2: graph_worker.get_vehicles_using_component(<supplier_id>) depends_on=t1] → [t3: graph_worker.list_recalls_affecting(<each vehicle>) depends_on=t2]` |
| supervisor round 1~3 | sequential (t2 → t3 모두 N×에 호출 fan-out) |
| cost | ~$0.015 |
| latency | ~8~10초 — multi-hop graph traversal + N 차종별 recall 조회 |
| 실패 지점 | (a) **`SUPPLIED_BY` 30 distinct edges 가 manual seed** — 현대모비스가 supplier_seed.yaml 에 등록된 부품만 추적 (`autograph.md §5.1` 정직 표시). 즉 답변 cover 가 yaml 의존. (b) `bridge.corp_entity` 의 supplier 매핑 정확도 — name match candidate 의 false-positive 위험 (mental_model §5.3). (c) latency 8초 임계 근처 — 차종 N>10 이면 timeout 가능 |
| gold QA | `gold_qa_auto_v0.jsonl` AUTO-L3 |

---

## 5. Cross-Domain — CD-L1 (직접 Bridge)

### 질문: "현대차가 제조한 모델의 리콜 건수와 현대차 영업이익을 같이 보여줘"

| 항목 | 내용 |
|---|---|
| 라우팅 | `auto_detect_domain` → `KW_FIN` ("영업이익") + `KW_RECALL` ("리콜") **동시 매칭** → `cross_domain` (코드: `autograph/policy.py:route_domain` 에서 KW_FIN ∩ KW_AUTO* 동시) |
| planner | `autograph.policy.plan_cross_domain_tasks` → DAG: `[t1: sql_worker.lookup_company('현대자동차')] → [t2: sql_worker.bridge_corp_to_entity('00164742', entity_type='manufacturer') depends_on=t1] + [t4: sql_worker.get_operating_income('00164742', 2024) depends_on=t1]` (병렬) → `[t3: graph_worker.list_recalls_affecting(<manufacturer_id>) depends_on=t2]` |
| supervisor round 1 | `Send(worker_sql, t1)` |
| supervisor round 2 | `Send(worker_sql, t2)` + `Send(worker_sql, t4)` (병렬 — t1 의 결과 사용) |
| supervisor round 3 | `Send(worker_graph, t3)` (t2 의 manufacturer_id 사용) |
| cost | ~$0.012 |
| latency | ~7초 (병렬 fan-out 의 효과 — t2/t4 동시) |
| 실패 지점 | (a) bridge 매핑 정확 (`reviewed_status='reviewed'` confidence ≥0.9) ✓ — manufacturer reviewed 11 안에 현대차 포함. (b) 리콜 N 건이 manufacturer 단위 통합인지 model 별 분리인지 LLM 합성 시점에 결정 |
| gold QA | `gold_qa_cross_v0.jsonl` CD-L1 10 row |

---

## 6. Cross-Domain — CD-L3 (3 도메인 — finance + auto + bridge)

### 질문: "LG에너지솔루션 배터리를 쓰는 차종을 가진 OEM 의 최근 영업이익은?"

| 항목 | 내용 |
|---|---|
| 라우팅 | `cross_domain` (LG엔솔 = supplier + 영업이익 + 차종) |
| planner | DAG 5 단계: `[t1: sql_worker.lookup_company('LG에너지솔루션')] → [t2: sql_worker.bridge_corp_to_entity('00373220', entity_type='supplier') depends_on=t1] → [t3: graph_worker.get_vehicles_using_component(<supplier_id>) depends_on=t2] → [t4: graph_worker.<manufacturer_id 추출> depends_on=t3] + [t5: sql_worker.get_operating_income(<each manufacturer's corp_code>) depends_on=t4]` |
| supervisor round 1~4 | 의존성 chain — 순차 4 round |
| cost | ~$0.025 |
| latency | ~10초 — 4 round + N OEM 별 corp 역매핑 + 영업이익 N 호출 |
| 실패 지점 | (a) LG엔솔 entity 가 `bridge.corp_entity` 의 supplier candidate 인 경우 — `include_candidate=True` 기본 (`bridge_corp_to_entity`) 이므로 동작. 단 confidence < 0.9 면 답변 "후보 정보" 명시. (b) `get_vehicles_using_component` 가 `:Component` (Module / Part) 단위인데 supplier↔module 매핑은 manual seed 의존 (§4 참조) — coverage 한계. (c) 각 manufacturer 의 corp_code 가 한국 (DART) 가 아닌 글로벌 (SEC) 인 경우 — `bridge_sec_cik_to_entity` 거꾸로 호출 필요 — 현재 planner 가 자동 분기 안 함 → **실패 가능 지점** |
| gold QA | `gold_qa_cross_v0.jsonl` CD-L3 12 row |

---

## 7. Cross-Domain — CD-L4-IP (3 도메인 동시 + 특허)

### 질문: "삼성SDI 배터리 특허(H01M) 집중 분야 + 영업이익 + 그 셀을 쓰는 OEM 리콜"

| 항목 | 내용 |
|---|---|
| 라우팅 | `cross_domain` — 키워드 3 도메인 모두 (특허 / 영업이익 / 셀 / 리콜) |
| planner DAG | **5 도메인 호출**: `[t1: sql_worker.lookup_company('삼성SDI')] → [t2_a: sql_worker.bridge_corp_to_assignee('00126362') depends_on=t1] + [t2_b: sql_worker.bridge_corp_to_entity('00126362', entity_type='supplier') depends_on=t1] + [t2_c: sql_worker.get_operating_income('00126362', 2024) depends_on=t1]` (3 병렬) → `[t3: graph_worker.list_patents_in_cpc('H01M', include_subclasses=True) depends_on=t2_a]` + `[t4: graph_worker.get_vehicles_using_component(<supplier_id>) depends_on=t2_b]` → `[t5: graph_worker.list_recalls_affecting(<each vehicle>) depends_on=t4]` |
| supervisor round 1 | t1 |
| supervisor round 2 | t2_a + t2_b + t2_c (3 병렬) |
| supervisor round 3 | t3 + t4 (2 병렬) |
| supervisor round 4 | t5 |
| cost | ~$0.040 |
| latency | ~12초 (README §10.14 Cross 12초 임계 한계) |
| 실패 지점 | (a) **`ip.patents` 0 row** — KIPRIS/USPTO 미적재 → `list_patents_in_cpc` 빈 결과 → "정보 부족" 응답. **현재 본 시나리오는 wire-up 만 완료**. (b) bridge_corp_to_assignee 의 `ip.assignee_corp_map` 도 0 row — assignee 적재 후 매핑. (c) 4 단계 의존 chain — 1 단계 실패 시 전체 실패. (d) latency 12초 임계 — N 차종 별 recall 조회가 N>5 면 timeout |
| gold QA | `gold_qa_cross_v0.jsonl` CD-L3-IP / CD-L4-IP 6 row (IP 결합 변형) |

> **현재 본 시나리오는 README §10.16 의 wire-up 완료 + 측정 대기 상태**. KIPRIS/USPTO 적재 후 실측 → 본 trace 갱신.

---

## 8. IP — IP-L1 (특허 카운트, 단순)

### 질문: "삼성전자 2023년 출원 특허 수는?"

| 항목 | 내용 |
|---|---|
| 라우팅 | `auto_detect_domain` → KW_IP ("특허", "출원") → `ip` |
| planner | `ipgraph.policy.plan_ip_tasks` → DAG: `[t1: sql_worker.lookup_company('삼성전자')] → [t2: sql_worker.count_patents_by_field('00126380', year_range=(2023, 2023))]` |
| supervisor round 1 | t1 |
| supervisor round 2 | t2 |
| cost | ~$0.003 |
| latency | ~3초 |
| 실패 지점 | (a) **`ip.patents` 0 row** — 현재 적재 안 됨 → "정보 부족" 응답. (b) 삼성전자 → `ip.assignee_corp_map` 매핑 부재 (assignee 적재 후) → bridge 실패 |
| gold QA | `gold_qa_ip_v0.jsonl` IP-L1 — **현재 gold_answer 비어있음** (KIPRIS/USPTO 적재 후 채움) |

---

## 9. Refusal — DB 에 없는 질문 (`is_answerable=false`)

### 질문: "삼성전자 2050년 매출은?"

| 항목 | 내용 |
|---|---|
| 라우팅 | `finance` (KW_FIN "매출") |
| planner | `[t1: lookup_company] → [t2: get_revenue('00126380', 2050)]` |
| t2 결과 | `null` (fin.financials 에 2050 row 없음) |
| synthesizer | tool_results 가 empty/null — LLM 이 "정보 부족" 응답 생성 (number_guard 화이트리스트에 2050 없음 — 환각 차단) |
| validator | answer 가 "정보 부족" 형태면 `validation_status='passed'` (self-report bypass) — **refusal precision** 측정 대상 |
| 예상 정답 | "2050년 매출 데이터 부족" — `gold_qa_v0.jsonl` 의 `is_answerable=false` row 와 매칭 |
| 실패 지점 | (a) LLM 이 환각으로 "2050 매출은 X 조" 답변 생성 → validator 가 `hallucinated_numbers` 검사로 fail → replan. (b) replan 후에도 환각 → max replans 도달 → `⚠️ 검증 실패` prefix |

---

## 10. 통합 — Trace 별 자랑 vs 실제 매핑 → [system_review.md §3.8 로 이관 (2026-06-02)]

본 절은 [docs/system_review.md §3.8 Trace 별 자랑 vs 실제 (9 trace)](system_review.md) 가 SSOT.

**종합 (system_review §3.8 흡수)**: 9 trace 중 4 개 (§1/§2/§3/§5) 가 **즉시 작동**. 3 개 (§4/§6/§7) 가 **부분 작동 (한계 명시)**. 2 개 (§8/§9) 가 **wire-up 완료 / 측정 대기**.

---

## 11. 실측 trace 흡수 절차 (LLM 키 활성 후)

```bash
# 1. LLM 키 설정
export OPENAI_API_KEY=...   # 또는 ANTHROPIC_API_KEY / GOOGLE_API_KEY

# 2. eval 실행
make eval-full       # finance 30 row
make eval-auto       # auto 56 row (L1~L3 + AUTO-PROC 10)
make eval-cross      # cross 49 row (CD-L1~L4 + CD-PROC 5 + IP 결합 변형)
# (ip 도메인은 KIPRIS/USPTO 적재 후 — make eval-ip)

# 3. 본 trace 갱신
# eval/reports/finance_<ts>/manifest.json 의 tool 호출 sequence + cost + latency 를 본 문서의 §1~§9 표에 실측값 reverse-feed
# (수동 작업 — 자동 routine `scripts/audit/update_trace_runbook.py` 미구현)
```

**자동화 routine 미구현** — 본 문서는 의도된 trace 정의이고, 실측 갱신은 PR 단위 수기 작업.

---

## 12. 더 깊이

- 11 노드 상세: [docs/architecture.md §5](architecture.md) (read/write 매트릭스)
- tool 시그니처: [docs/api_reference.md](api_reference.md)
- 데이터 lineage: [docs/data_lineage.md](data_lineage.md)
- gold QA 운영: [docs/gold_qa_guide.md](gold_qa_guide.md)
- 시스템 한계 통합 review: [docs/system_review.md](system_review.md)

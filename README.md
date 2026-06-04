# AutoNexusGraph — README + PRD 통합 SSOT v3.0

> **자동차/제조 (auto + BoP 공정) + 한국 상장사 재무·지배구조 (finance) 를 그래프·정형·벡터 하이브리드로 추론하고, `bridge.corp_entity` + `ip.assignee_corp_map` 로 특허(ip 보조축) 까지 한 turn 안에 묶는 산업·기업 인텔리전스 그래프.** 벡터 단독 RAG 가 풀지 못하는 **멀티홉 / Cross-Domain / 시점 포함 공급망 / BoM ⟂ BoP 직교 추론** 을 **Neo4j (관계) + PostgreSQL (수치·메타) + pgvector (의미)** 하이브리드 + **LangGraph multi-agent (StateGraph 11 노드)** 로 해결한다. LLM Provider 는 ENV 한 줄로 OpenAI / Anthropic / Google / 로컬 교체.

**본 문서 = 단일 SSOT (v3.0, 2026-06-02).** README(소개·현황·Quickstart) + PRD(요구사항·DoD·로드맵·의사결정 로그) 가 하나로 통합됨 — 두 문서 간 버전·DoD 항수·수치 drift 영구 해소. 도메인 상세 설계는 분리 SSOT 위임: 자동차 [docs/autograph.md](./docs/autograph.md) · **제조 공정(BoP) [docs/process_graph.md](./docs/process_graph.md)** · 특허(보조) [docs/ipgraph.md](./docs/ipgraph.md).

문서 본문 측정값은 별도 명시 없으면 **2026-06-01 기준** (`make audit-data-channels` + `make audit-dod` 재실행 시 갱신).

---

## 0. 축 위계 (이 시스템의 척추)

> 넓이가 아니라 깊이. 도메인을 평평하게 나열하지 않고, **본체 1 + 대칭 1 + 보조 1 + 곁가지**로 위계화한다.

| 위계 | 도메인 | 역할 | 상태 |
|---|---|---|---|
| **본체 (수직 심화)** | **auto** = 제품·부품·리콜·공급망 **+ 제조 공정(BoP)** | 도메인 본체. BoM⟂BoP 로 "무엇을 만드나"+"어떻게 만드나" | auto 구현 / **process = 1급 모델 + sparse 인스턴스** ([§10.18~20](#10-dod-definition-of-done--20-항)) |
| **대칭 도메인** | **finance** = 한국 상장사 공시·재무 | corp_entity 로 auto 와 cross. 가장 조밀·권위(DART) | 구현 |
| **보조축 (수평 cross)** | **ip** = 특허·기술혁신 | assignee→corp 브리지를 타는 **수평 cross 진입 어댑터** (corp_entity 브리지 전용). 풀 도메인 어댑터 완료, 데이터 부분 적재 | 구현 (CPC 10,695 + OpenAlex 629) |
| **곁가지 (L6)** | 배터리·소재 | 공개 거시(USGS) + Wikidata chem | (부분 적재 — Material 6 / Mineral 5 / DERIVED_FROM 17 / MADE_OF 8) |

**process 가 "주요 축"인 근거 (정직):** BoP 모델(`:Process` 410 / `:ProcessStep` 550 / `INSTANTIATES` 550 / `PRECEDES` 410, C grade taxonomy) 은 이미 적재 완료. **회사 귀속 인스턴스 `PERFORMED_AT` 94 적재** (manual_seed 35 validated B + factoryon 59 candidate A공장/추론공정, DoD #19 ≥30 충족). `PRODUCED_BY` 46 candidate (부품→공정 카테고리 추론), `CAUSED_BY_PROCESS` 96 candidate (리콜→공정). `CONSUMES_MATERIAL`/`USES_EQUIPMENT` 등은 0 (산단공 소재·설비 정보 부재). "주요 축" = **1급 BoM⟂BoP 직교 모델 + sparse 인스턴스** 라는 뜻이지 "데이터가 풍부한 본체"라는 뜻이 아니다. 성공 기준은 "지금 몇 개 질문에 답하나"가 아니라 **"내부 데이터가 들어왔을 때 코드·온톨로지·도구를 거의 안 바꾸고 꽂을 수 있는가(수용 능력)"** 다.

> **정직성 가드 2개 필수:** (1) "준비된 빈 축" 명시 — 합성·공개데이터(산단공·KAMP)는 패턴/검증용이지 사실 주장용 아님 (회사 귀속 엣지 hard-check 차단). (2) **내부 데이터 수용 규격**(로더 계약 + 등급 승급 C합성→A내부)을 결과물로 보유 (DoD §10.20). 상세 [docs/process_graph.md](./docs/process_graph.md).

**ip 가 "보조축"인 근거:** ip 와 process 는 층위가 다르다. process 는 도메인 본체에 붙는 **수직 심화**(BoM⟂BoP), ip 는 `bridge.corp_entity` 브리지를 타는 **수평 외부 소스**. ip 도 정식 도메인 어댑터(코드/온톨로지/도구 모두 완료) 지만, finance/auto 와 달리 **bridge 진입만 하는 cross 진입 어댑터** 라는 의미에서 "보조축". CPC bulk 10,695 + OpenAlex works 629 적재, 특허 본문은 KIPRIS/USPTO ODP bulk 발급 대기.

> **라벨 컨벤션 (문서 전체):** *(라벨 없음, 수치만)* = 구현 완료 + SSOT 측정값 · **⊘ 측정 대기** = 구현 완료, LLM 키 등 외부 의존 · **(scaffold)/(wired)** = 코드 있음, 데이터·키 부재 · **(예정)** = 미구현 + 최종 필수 · **(부분 적재)** = 일부 데이터 있음, 본격 진입 전 · **(예정, 보조)** = 보조축, 후순위 · **(비전)** = 우선순위 강등.

## 5분 진입점

| 무엇 | 왜 | 어떻게 (코드 진입점) |
|---|---|---|
| 3 도메인 + Bridge 를 한 turn 안에 묶는 GraphRAG 에이전트 | 단일 벡터 RAG 로는 "현대모비스 매출 ↔ 모비스가 공급하는 차종의 최근 리콜" 같은 멀티홉·교차도메인 질의 불가 | StateGraph 11 노드: Triage→Planner→Supervisor↔Workers(research/graph/sql/calculator)→Synthesizer→Validator (`agents/graph.py:110-123`) + Send-API 병렬 + Replan 최대 2회 (`validator.py:36 MAX_REPLANS=2`) |
| 도메인 plug-in 으로 N-domain 확장 | 4번째 도메인 추가 시 "코어 변경 < 5%" 가 확장성 정량 증거 (§10.12). 첫 plug-in 검증 = ip 도메인 = **inflection +1,877 LOC (13.32%) → baseline reset 후 0/15,396 LOC = 0.00%** ([정직 표기](./eval/reports/core_diff_baseline_ledger.md#정직-review--코어-변경--5-가-정말-의미-있는가-p1-5) — 두 숫자 같이 인용) ✅ | ENV `AUTONEXUSGRAPH_DOMAIN_PLUGINS` (CSV, 기본 `"autograph"`) 의 모듈을 첫 호출 시 soft-load (`_domain_handler.discover_plugins`, 라인 130). 외부 패키지가 `register_handler()` 부작용으로 등록 |
| 서비스 등급 (MCP·관측가능성·평가 실측) 정량 증명 | 데모가 아닌 운영 등급으로의 증명이 1차 목표 (§10.15~§10.17) | MCP 래퍼 59 tools (`src/autonexusgraph/mcp/`) · Langfuse 4.x OTEL (`agents/tracing.py`) · 축소 평가 매트릭스 4 어댑터 × FAST tier (`eval/runners/run_matrix_smoke.py`) |

### 핵심 용어 (자세한 정의는 [docs/learning_guide.md](./docs/learning_guide.md))

- **bridge.corp_entity** — 한국 corp_code ↔ 글로벌 entity (manufacturer/supplier/assignee) 양방향 매칭. 우선순위 `wikidata_qid > LEI > sec_cik > business_no > name`. 함수: `bridge_corp_to_entity(corp_code, *, entity_type=None, min_confidence=0.0, include_candidate=True)` / `bridge_entity_to_corp` / `bridge_sec_cik_to_entity` (`src/autograph/tools/bridge.py:23, 47, 64`). `reviewed_status='rejected'` 자동 제외.
- **도메인 plug-in** — core 는 외부 도메인 패키지를 직접 import 하지 않는다. ENV 모듈을 첫 호출 시 soft-load 후 `register_handler` 부작용으로 활성. core ↔ 도메인 어댑터 분리.
- **4 가드** — `prompt_safety` (injection 단발 차단) · `cypher_guard` (READ-ONLY 강제 + APOC write 블록, `safety/cypher_guard.py:assert_read_only`) · `number_guard` (큰 숫자 화이트리스트, `agents/number_guard.py`) · `language_guard` (한국어 비율 ≥ `FINGRAPH_MIN_KOREAN_RATIO=0.30`, `safety/language_guard.py:16`).
- **cost tier** — 비용 가드는 3 계층: **세션** hard limit (`LLM_SESSION_HARD_LIMIT_USD`) → **도메인별 turn** budget (`config.turn_budget_for_domain`, ENV override) → **호출별 사전 추정** (Rewriter / Synthesizer / Title, `cost_estimator.py`) + `LLM_COST_AUTO_APPROVE_USD` (기본 $0.50) 초과 시 HITL 승인.
- **AgentState** — TypedDict, **33 필드** (입력 7 / 전처리 4 / triage·planner 5 / 누적 5 / 합성 3 / 검증 3 / HITL 3 / 메타 3). `_last_wins` reducer 로 병렬 worker 충돌 회피 (`agents/state.py:35-89`).

### 진입점 다이어그램

```
질문 ─▶ [_init_state] ─▶ domain 자동 라우팅 (auto_detect_domain) ─▶
   ┌──────────────────────────── StateGraph 11 노드 ────────────────────────────┐
   │  triage ─▶ planner ─▶ supervisor ─┬─▶ worker_research  ─┐                  │
   │                                   ├─▶ worker_graph     ─┤                  │
   │                                   ├─▶ worker_sql       ─┼─▶ synthesizer ─▶ │
   │                                   ├─▶ worker_calculator─┤      validator    │
   │                                   └─▶ executor_legacy  ─┘        │         │
   │                                                                  ▼         │
   │                            replan (n_replans < 2) ◀──── needs_replan?     │
   │                                                                  │         │
   │                                                                finalize    │
   └────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
            [3-Store 백엔드] Neo4j (관계) · PostgreSQL (수치+메타) · pgvector (청크 의미)
                                       │
                                       ▼
            [도메인 plug-in] finance (core) · auto (autograph) · ip (ipgraph)
                                       │
                                       ▼  ←─ bridge.corp_entity ─→  Cross-Domain
                                       ▼
                              [답변 + 출처 + confidence]
```

### 더 깊이

- **요구사항·DoD·범위**: 본 문서 [§10 DoD 20항](#10-dod-definition-of-done--20-항) (v3.0 — IPGraph 정식 #15~#17 + ProcessGraph #18~#20 신규)
- **시스템 구조 SSOT** (패키지 토폴로지·LangGraph 노드·SSOT 색인): [docs/architecture.md](./docs/architecture.md)
- **도메인별 SSOT**: [docs/autograph.md](./docs/autograph.md) (자동차) · [docs/ipgraph.md](./docs/ipgraph.md) (특허 — 보조축) · **[docs/process_graph.md](./docs/process_graph.md) (제조 공정 BoP — auto 수직 심화, 주요 축)**
- **세미나 가능 수준 심화 가이드** (이론 → 코드 → 한계 → 최신연구): [docs/learning_guide.md](./docs/learning_guide.md)
- **결정 카탈로그** ([확정]/[잠정]/[미정] + 트레이드오프 + 열린 질문): [docs/mental_model.md](./docs/mental_model.md)
- **장기 비전·로드맵**: 본 문서 [§11 최종 비전](#11-최종-비전--장기-로드맵) (Phase A/B/C 현재 + Phase D/E 비전)
- **의사결정 로그 + 변경 로그**: 본 문서 [§16 부록](#16-부록-의사결정-로그--변경-로그)
- **즉시 실행**: [§14 Quickstart](#14-quickstart) (finance) · [Quickstart — AutoGraph](#quickstart--autograph-자동차-도메인) · [Quickstart — IPGraph](#quickstart--ipgraph-특허-도메인)

---

## 1. 한눈에 보는 현황

> 측정 기준: **2026-06-01**. 갱신 = [docs/data_inventory.md](./docs/data_inventory.md) + `eval/reports/prd_dashboard_latest.md`. 재조회 명령: `make audit-data-channels` + `make audit-dod`. 모든 정량 수치는 ingestion 재실행 후 변동 가능 — 발표·인용 시 PG / Neo4j 직접 조회 권장.

### Finance 도메인 (코스피200 + 코스닥100)

| 영역 | 적재량 | 비고 |
|---|---:|---|
| `master.companies` (코스피200+코스닥100) | 295 | 활성 회사 |
| `master.entity_map` (ticker/QID/LEI/CIK/ISIN/…) | 1,979 | 10 종 외부 ID |
| `master.persons` / 임원 이력 | 9,948 / 22,303 | (name, birth_year) 분리 |
| `fin.financials` (XBRL) / `fin.filings` | 184K / 4.6K | 3년치 |
| `news.articles` / 멘션 | 338 / 141 | 연합뉴스 RSS 3종 |
| `wiki.wikipedia_pages` / `wiki.wikidata_facts` | 276 / 466 | 93.6% / 55.6% 매핑 |
| `sec.filings` (한국 ADR) / `sec.lei` (GLEIF KR) | 1,857 / 2,704 | GLEIF API enrich — sec.lei.corp_code 113→**128** / `master.entity_map(lei)` 120→**128** / bridge.corp_entity.lei 0→**5** (supplier strong-match 2→**4** +100%) |
| `vec.chunks` (DART + Wikipedia) | 748,812 | embedding backfill 진행 중 |
| Neo4j Company / Person / NewsEvent | 12,914 / 14,536 / 85 | 동명이인 2,171 분리 |
| Neo4j SUBSIDIARY_OF / EXECUTIVE_OF / MAJOR_SHAREHOLDER_OF ⭐ 6/1 재측정 + 7키 cover | 8,661 / **36,399** / **16,725** | 100% 7키 메타 cover (`audit-edge-meta` PASS 2026-06-01 — DART 공시 grade A: `source_type='dart_otr_cpr_invstmnt/exctv_sttus/hyslr_sttus'`, `confidence_score=0.95`, `validated_status='verified'`, `snapshot_year`, `schema_version='v2.2'`). 73,602 finance 엣지(SUBSIDIARY/RELATED/EXEC/SHAREHOLDER/HAS_CEO/LISTED_IN/IN_INDUSTRY/MENTIONS/CO_MENTIONED) 일괄 backfill + loader 4 파일(graph.py/graph_structural.py/load_news.py/load_graph_news_corel.py) cypher 7키 SoT 적재. 동명이인 분리는 (name, birth_year). |

### Auto 도메인 (HYUNDAI/KIA/GENESIS/TESLA/FORD × 2020–2024 — 5 OEM 확장 완료, KGM/르노코리아는 data.go.kr 키 발급 후 추가 예정)

| 영역 | 적재량 | 비고 |
|---|---:|---|
| `auto.master_manufacturers` | 22,145 | NHTSA vPIC 12K + Wikidata mfr 10K (QID 10,027 매핑) |
| `auto.master_vehicle_models` | 6,770 | vPIC + Wikidata 모델 |
| `auto.master_vehicle_variants` | 428 | HYUNDAI/KIA/GENESIS/TESLA/FORD × 2020–2024 |
| `auto.master_suppliers` | 4,812 | Wikidata + manual seed (legacy QID → numeric supplier_id 마이그레이션 완료) |
| `auto.events_recalls` (NHTSA) | 493 | 모두 manufacturer_id / 92% model·variant 매핑 (FORD 274 추가) |
| `auto.events_complaints` (NHTSA) | 16,005 | 100% mfr / 97% model·variant 매핑 |
| `auto.events_investigations` (NHTSA ODI) | **154** | PE 89 / EA 32 / DP 14 / RQ 11 / AQ 3 — 리콜 전단계 결함 조사 |
| `auto.spec_measurements` (NHTSA NCAP + EPA + vPIC Canadian) | **3,329** | NCAP 1,680 + EPA 1,426 + Canadian 223 |
| `auto.components` (NHTSA taxonomy + AI Hub + manual seed) | **220** | NHTSA taxonomy 176 + aihub_578 22 + supplier seed 18 + aihub_71347 4 — 모두 L4 (Module) |
| `auto.oem_financials_sec` | **3,199** | 글로벌 OEM (Ford/GM/Stellantis/Toyota/Honda/Tesla …) XBRL facts |
| `vec.chunks` (auto: nhtsa + aihub + epa + datagokr + wikipedia) | **16,435 / 모두 embedded** | manufacturer/model/variant 메타 필터 가능 |
| `bridge.corp_entity` (suppliers 포함) † | **4,806** | manufacturer reviewed 10 (sec_cik 9 + corp_code 1 + qid 1) / supplier candidate 4,792 / supplier reviewed 2 |
| Neo4j Manufacturer / Model / Variant / Recall | 22,145 / 6,770 / 428 / 493 | `AFFECTED_BY` 인덱스 매칭 |
| Neo4j Complaint / Investigation | 16,005 / 154 | NHTSA REPORTED_IN / INVESTIGATED_BY |
| Neo4j System / Module / Part | (load-auto-all 후) | Level 3 / 4 / 5 — `system_taxonomy.yaml` 19 시스템 (POWERTRAIN, BRAKE, ADAS, …) |
| Neo4j Supplier / SUPPLIED_BY | **30 SUPPLIED_BY 엣지** (100% meta — `source_type='manual_supplier_seed'`) | `supplier_seed.yaml` 19 공급사 × 46 (supplier, customer, component) tuple 매핑. Neo4j 엣지는 supplier↔component dedupe (customer 다중은 별도 `:CONTAINS_COMPONENT` 엣지로 표현) → 30 distinct edges. **edge_meta_invariants 8 invariant 모두 PASS** |
| Neo4j RECALL_OF / CONTAINS_COMPONENT | 601 RECALL_OF | NHTSA taxonomy 적재 후 recall→component 매칭율 100% |
| Neo4j Standard / Plant / Complaint | (seed 후) | `standards.yaml` 22 + `plants.yaml` 18 + `manufactured_at_seed.yaml` 46 모델↔공장 |
| `auto.staging_relations` (P3 LLM + Wikidata P176) | extract-auto-p3 후 | SUPPLIED_BY / RECALL_OF 후보 — P4 검증 후 그래프 적재 |
| `auto.processes` (산단공 합성 15151075) | **550 row / 410 공정명** | C 등급 (0.50) — 공정명 정규형 사전. agent tool `search_processes` / `lookup_process` |
| **ProcessGraph (BoP 축)** Neo4j `:Process` / `:ProcessStep` / `PRECEDES` / `INSTANTIATES` | **410 / 550 / 410 / 550** | C 등급 — 산단공 공정사전 → BoP routing (회사 비귀속). `tools/process.py` + `auto_proc_*`. **회사 귀속 `PERFORMED_AT` 94 적재** (manual_seed 35 + factoryon 59 candidate, DoD #19 충족). 품질(CAUSED_BY_PROCESS) / 메트릭(KAMP)은 (scaffold) — 데이터 대기, SSOT [docs/process_graph.md](./docs/process_graph.md) |
| `auto.plant_capacity` + `plant_production` (DART III. 생산·설비) | **107 + 77 row** (Hyundai 12 plants × 4~7년 + Kia 5 plants × 6년) | B 등급 (0.80) — Hyundai/Kia. agent tool `get_plant_capacity` / `get_oem_production` / `list_plants_by_oem`. Kia 파서는 `품목/소재지` schema 변형 대응 |
| `auto.plant_utilization` (DART III. (3) 가동률) | **53 row** | B 등급 — Hyundai HMC 116.6% / 베트남 HTMV 54.1% 등 explicit util_pct |
| `auto.macro_production_yearly` (KAMA 15051116) | **21 row** (2005~2025) | A 등급 (0.95) — 연 단위 한국·세계 생산량. 2024 한국 점유 4.55%. agent tool `get_macro_production` |
| `auto.macro_industry_monthly` (KAMA 15051118) | **204 row** (2009-01~2025-12) | A 등급 — 월 단위 내수·수출·수출금액. agent tool `get_macro_industry` |
| `auto.events_oem_news` (IR/뉴스룸) | **37 row** (Hyundai 25 + Kia worldwide 12) | B 등급 — sitemap-first crawler + robots/ToS 게이트. Mobis/Kia 한국 비활성 (SPA/robots Disallow) |
| `auto.events_inspections` (KOTSA 15155857) | **47,171 row** (2016~2025) | A 등급 — 사고 46,883 / 침수 183 / 도난 35 / 기타 70 검사 |
| Neo4j MANUFACTURED_AT (DART) | **99 edges** (12 plants × 4~7년 시계열) | `(Manufacturer)-[r:MANUFACTURED_AT {snapshot_year, capa_units, actual_units, utilization_pct, source_type='dart_business_report', confidence_score=0.80}]->(Plant)`. MERGE 키에 year 포함 — 시계열 보존 |
| `plants.yaml` (Hyundai/Kia 글로벌 30 plant) | 30 plant (HYU_ULSAN/HMMA/HMI/HAOS/HMMC/HMMR/HMB/HTMV/HMMI/HMGMA/HMTR + KIA_HWASEONG/WEST_POINT/ZILINA/MONTERREY/ANANTAPUR …) | `_DART_PLANT_CODE_MAP` 17 raw → :Plant.code 매핑. plants_skipped 0 (전 plant 매핑) |
| `auto.master_minerals` (USGS MCS) | **5 row** (Li/Ni/Co/Mn/Graphite, snapshot_year=2024) | A 등급 (0.95) — `usgs_mcs` PDF parser. world_production·world_reserves·import_reliance·price |
| Neo4j Material / Mineral / DERIVED_FROM / MADE_OF (L6) | 6 / 5 / **17** / 8 | `materials_seed.yaml` 6 cathode chem (NCM811/622/523/NCA/LFP/GRAPHITE_ANODE). DERIVED_FROM 7-key 100%. MADE_OF 는 기존 :Module name 매칭 8 |

> **† 측정값 정합 (2026-06-01 재조회 완료)**:
> - **`bridge.corp_entity` 4,806** — manufacturer candidate 1 + reviewed 11 + supplier candidate 4,790 + reviewed 4 = 합 일치.
> - **SUPPLIED_BY 30 edges** — yaml 46 `(supplier, customer, component)` tuple → Neo4j 는 supplier↔component dedupe (customer 다중은 `:CONTAINS_COMPONENT` 엣지). `edge_meta_invariants` 8 invariant 모두 PASS.
> - **strong_match 15/15 (100%)** — `confidence_score >= 0.9` 기준: manufacturer 11 + supplier 4.
> - **Cypher 템플릿** — finance **22** (정적 14 + 동적 helper `find_paths_{1..5}hops` 5 + `get_subgraph_d{1..3}` 3, `list_templates()` enumerate 기준) / auto **24** (정적 20 + 동적 `auto_find_paths_{1..4}hops` 4, `AUTO_TEMPLATES` dict) / ip **25** (`IP_TEMPLATES` dict).

### IPGraph 도메인 (ip — 보조축 / corp_entity 브리지 전용 / 코드·온톨로지·도구 완료, 데이터 부분 적재)

> 최종 목표 = "N-domain 확장성 정량 증명". 도메인3 추가 후 §10.12 "코어 변경 < 5%" 재측정 — `make audit-dod` 현재 default baseline `831e72d` (상용화 P0/P1 일괄 후 reset, [ledger](./eval/reports/core_diff_baseline_ledger.md)) 기준 **0% from 831e72d** ✅ (ip 통합 inflection `bab9411→414bc1b=+1,877 LOC`, 상용화 inflection `414bc1b→831e72d=+1,583 LOC` 별도 기록) (정직 표기: 통합 inflection `bab9411→414bc1b = +1,877 LOC` 후 reset — 두 숫자 같이 인용해야 정직, [ledger §B-D 참조](./eval/reports/core_diff_baseline_ledger.md#정직-review--코어-변경--5-가-정말-의미-있는가-p1-5)). baseline reset 이력·정책 + 정직 review §A-E SSOT: [eval/reports/core_diff_baseline_ledger.md](./eval/reports/core_diff_baseline_ledger.md) + §10.12 본문 + §11.1. 상세 설계 SSOT 는 [docs/ipgraph.md](./docs/ipgraph.md). 코드: `src/ipgraph/{agent_handler,policy,ontology,cypher_templates_ip}.py + tools/{bridge,graph,patents,retrieve}.py + loaders/{load_cpc,load_openalex}.py + ingestion/{cpc_scheme,kipris,uspto_odp,openalex}.py`. `make audit-ipgraph` PASS. 데이터 적재: CPC bulk 10,695 + OpenAlex works 629 (line 89, 92-96). **PG schema 12 ip.* 테이블 적용 완료 (2026-06-01 — 18/19_ipgraph.sql, schema drift 해소)** — patents/assignees/citations row 적재는 KIPRIS_API_KEY 발급 + USPTO ODP bulk download 대기.

| 영역 | 적재량 | 비고 |
|---|---:|---|
| `ip.patents` (KIPRIS + USPTO ODP) | 0 | PG schema 적용 완료 (pub_no/jurisdiction/source). KIPRIS_API_KEY 발급 + USPTO ODP bulk download 후 데이터 적재 |
| `ip.assignees` (Wikidata QID·LEI·business_no 매칭) | 0 | PG schema 적용 완료. Assignee → corp_entity 브리지 (M-3), USPTO ODP / KIPRIS 적재 후 |
| `ip.cpc_scheme` (CPC 분류 계층 depth ≥ 4) | **10,695** (section 9 + class 137 + subclass 681 + main_group 9,868) | ✅ USPTO+EPO 공동 CPC bulk (CPCTitleList202605.zip, 무인증). subgroup 250K 는 별도 cron |
| `ip.citations` (PatentsView 후속 USPTO ODP) | 0 | PG schema 적용 완료. 인용 네트워크, `get_citation_network(depth≤2)` cap 강제 |
| `ip.assignee_corp_map` (신규 join 테이블) | 0 | PG schema 적용 완료 (19_ipgraph_bridge.sql). `bridge.corp_entity` 직접 변경 회피, supplier candidate 운영 SOP 재사용 |
| `ip.inventors / ip.patent_inventors / ip.patent_assignees / ip.patent_cpc` | 0 / 0 / 0 / 0 | PG schema 적용 완료 (18_ipgraph.sql). Patent 적재 후 FK ON DELETE CASCADE 로 자동 채워짐 |
| `ip.works` (OpenAlex 논문) / `ip.institution` / `ip.work_institution` | **629 / 38 / 638** | ✅ KR 38 corp_code 매칭 (현대차/모비스/기아/만도/LG/네이버/효성/금호석유/한미약품/Hyundai Steel …) × 상위 인용 work 20씩, 2020~. abstract 423건 → vec.chunks (embedding NULL = BGE-M3 backfill 대상). 특허×논문×재무 3중 cross 진입점 |
| Neo4j Work / Institution / AUTHORED_AT / IS_ENTITY | 629 / 38 / **638** / 38 | AUTHORED_AT 7-key 100% / IS_ENTITY (Institution→Company) cross-domain bridge |
| Neo4j Patent / Assignee / Inventor / CPCCode | 0 / 0 / 0 / **10,695** | CPCCode 적재 완료. Patent/Assignee/Inventor 는 KIPRIS/USPTO ODP 데이터 적재 후 |
| Neo4j ASSIGNED_TO / INVENTED / CLASSIFIED_AS / CITES / SUBCLASS_OF | 0 / 0 / 0 / 0 / **10,686** | SUBCLASS_OF 7-key 100% (cpc_scheme A 등급). 나머지 4종은 KIPRIS/USPTO ODP 후 |
| `eval/qa_gold/gold_qa_ip_v0.jsonl` | **30** | IP-L1/L2/L3 각 10. validate-gold-qa 0 errors. Patent 적재 후 gold_answer 채움 |

---

## 2. 핵심 특징

- **멀티도메인** — `finance` + `auto` + `ip` (코드/온톨로지/스키마 완료, 특허 데이터 적재 대기) + `cross_domain` 4 모드. 도메인은 hint 또는 키워드 자동 라우팅 (`src/autograph/policy.py::route_domain` + 후속 `src/ipgraph/policy.py::route_domain_ip`). 단일 에이전트가 도메인 + 그 교차 추론을 한 turn 안에 처리. core 는 외부 도메인 패키지를 직접 import 하지 않고 `_domain_handler.discover_plugins()` 가 ENV `AUTONEXUSGRAPH_DOMAIN_PLUGINS` (csv, 기본 `autograph`, ip 활성 시 `autograph,ipgraph`) 를 기반으로 첫 호출 시 1회 soft-import — finance-only 환경에서는 ENV 를 빈 값으로 두면 됨
- **금융 도메인** — DART 공시 / KRX 마스터 / ECOS / Wikidata / Wikipedia / SEC EDGAR / GLEIF / 연합뉴스 RSS / KCGS ESG → 코스피200+코스닥100 대상
- **자동차 도메인** — NHTSA vPIC/Recalls/Complaints / Wikidata (manufacturers/models/suppliers) / (옵션) car.go.kr / KATRI / KNCAP / 한국교통안전공단 수리검사. BOM Level 0~5 — Manufacturer → Model → Variant → System(L3) → Module(L4) → Part(L5, 리콜·LLM 출처에서 부분 커버). **Level 6 (소재·공법) (예정)** — 배터리 셀 chem + 핵심광물 + 무역통계 (§10.2 / [docs/autograph.md §2.5.4](./docs/autograph.md))
- **3-Store 하이브리드** — Neo4j (관계 그래프) + PostgreSQL (수치·메타) + **pgvector** (PostgreSQL 16 내장 확장, 청크 의미 벡터). 청크 ≤ 100만은 pgvector 통합 운영 (현재 finance 748K + auto 16K), 그 이상은 **Qdrant 분리 옵션**. 각 store 의 책임 분리는 §3 "저장소 역할 분리 원칙" 표
- **Multi-Agent + Planning (LangGraph)** — Triage / Planner / Supervisor / Workers / Validator / Synthesizer 역할 분리 ([docs/operations/agents.md](./docs/operations/agents.md))
- **채팅형 UI + 대화 히스토리** — thread 기반 multi-turn (FastAPI `/chat/stream` + Streamlit · §3)
- **Deterministic-first 추출** — XBRL 재무·지배구조는 정형 직매핑 (0% LLM), 서술형 관계만 selective LLM (§3.6 4-Pass + Bridge Pass)
- **LLM 어댑터 패턴** — `LLMClient` 단일 인터페이스, `LLM_PROVIDER` 한 줄로 백엔드 교체
- **한국어 자체 임베딩** — BGE-M3 + BGE-Reranker (GPU 자체 호스팅)
- **통합 Entity Resolution 마스터** — `entity_id` + `entity_type` 다형 키 (§3.4). corp_code 는 **finance 연동 키**로 wikidata_qid / lei / cik / isin / business_no 등과 매핑. 동명이인 인물은 (name, birth_year) 분리
- **재실행 가능한 멱등 파이프라인** — raw → processed → DB. 모든 적재 `ON CONFLICT DO UPDATE` / `MERGE`. raw 만 있으면 언제든 재생성 가능
- **도메인 확장성 (N-domain plug-in)** — core 는 외부 도메인 패키지를 직접 import 하지 않음. `_domain_handler.discover_plugins()` 가 ENV `AUTONEXUSGRAPH_DOMAIN_PLUGINS` 의 모듈을 첫 호출 시 soft-import 하고, 도메인 패키지의 `register_handler()` 부작용으로 활성. §10.12 "코어 변경 < 5%" 보존 — **도메인3 (ip = 특허) 이 첫 plug-in 확장 정량 검증.** §10.12 baseline reset 후 코어 변경 < 5% 가 N-domain 확장성의 정량 증거. 의약품·전자제품·에너지·식품은 비전 (§10.1 Phase D/E)
- **출처 등급 기반 confidence (A/B/C)** — 모든 그래프 엣지의 `confidence_score` 기본값을 출처에 따라 결정 (NHTSA/공식 = 0.95 A / Wikidata = 0.80 B / LLM P3 = 0.50 C). `validated_status` 가 candidate/validated/needs_review/rejected — 답변 인용 시 grade 표시
- **시점 + provenance 강제** — auto 도메인 모든 엣지에 `source_type` / `source_id` / `confidence_score` / `validated_status` / `snapshot_year` / `extraction_method` / `schema_version` 7키 의무. `make audit-edge-meta --strict` 가 invariant 강제

---

## 3. 아키텍처

```
[데이터 계층]
├─ Neo4j        : 기업·인물·관계 그래프 (자회사·임원·주주·뉴스·기업집단)
├─ PostgreSQL   : 재무 수치 + 마스터 + 메타 + 청크 벡터 (pgvector)
└─ (옵션) Qdrant: 청크 100만 넘으면 분리

[모델 계층]
├─ BGE-M3 (1024 dim)        : 한국어 임베딩 (GPU 0)
└─ BGE-Reranker-v2-m3       : 한국어 재랭킹 (GPU, 옵션)

[애플리케이션 계층]
├─ Ingestion Workers : DART/KRX/ECOS/Wikidata/Wikipedia/News/SEC/GLEIF/KCGS + NHTSA/AI Hub/EPA + (예정) KIPRIS/USPTO ODP/CPC bulk 클라이언트
├─ Loaders            : PG/Neo4j 멱등 적재 (P1 deterministic / P2 deterministic / P3 LLM / P4 cross-validate)
├─ Tools              : 사전 정의 함수 풀 (finance: financials/graph/retrieve · auto: spec/graph/retrieve/bridge · ip: patents/graph/retrieve/bridge — 코드 완료) — 자유 SQL/Cypher 금지
├─ Safety             : prompt_safety (XML escape + injection 감지 + high-risk 단발 차단) · cypher_guard (READ-ONLY + APOC write/dynamic-cypher procedure 블록) · language_guard
├─ Agents (LangGraph) : Triage → Planner(DAG) → Supervisor ↔ Workers(병렬: research/graph/sql/calculator)
│                       → Synthesizer → Validator (replan ≤ 2, tasks/result 자동 리셋)
│                       · Send API 병렬 디스패치 · 세션 메모리 (thread별 TTL/LRU)
│                       · checkpoint (chat.checkpoints) · streaming (SSE / st.status)
│                       · tracing (Langfuse/LangSmith)
└─ API / UI           : FastAPI 5 엔드포인트 (`POST /chat` · `POST /chat/stream` (SSE) · `POST /chat/resume` (HITL 재개) · `GET /threads/{id}` (히스토리) · `GET /health` (PG/Neo4j ping)). Streamlit 채팅 (node progress · 👍/👎/📝). **인증 없음 — 외부 노출 시 reverse proxy + auth gateway 필요 (§12.2 운영 보안 P1)**

[외부 의존성]
└─ LLM Provider : OpenAI / Anthropic / 로컬 (환경변수 전환)
```

상세는 [docs/operations/agents.md](./docs/operations/agents.md) 참조.

### 저장소 역할 분리 원칙

| 저장소 | 책임 | 예시 질의 | 코드 진입점 |
|---|---|---|---|
| Neo4j 5.18 | **관계·구조** (자회사·임원·주주·뉴스·SUPPLIED_BY·RECALL_OF) | "현대차 자회사 중 매출 1조 이상은?" / "Tesla Model Y 의 ADAS 시스템 공급사는?" | `tools/graph.py` + `src/autograph/tools/graph.py` (Cypher 템플릿 경유, `cypher_guard.assert_read_only`) |
| PostgreSQL 16 | **정확한 수치 + 메타** (XBRL 재무·spec·마스터·이벤트) | "삼성전자 2023년 매출은?" / "현대모비스 R&D 비?" | `tools/financials.py` + `src/autograph/tools/spec.py` |
| pgvector (PG 내장) | **의미·서술 검색** (DART 본문·Wikipedia·NHTSA complaint 텍스트) | "삼성전자의 주요 사업 위험 요인은?" / "이 부품의 결함 신고 패턴은?" | `tools/retrieve.py` (`search_documents` / `search_by_metadata` — pgvector 코사인 + 메타 필터) |

> 재무 수치는 절대 LLM 이 생성하지 않는다 — 반드시 PostgreSQL 조회 결과만 사용. `number_guard` 가 답변 합성 시 비-화이트리스트 큰 숫자를 마스킹.

**왜 3-store 분리?** (대안과 기각 사유)

- **Neo4j 단독 거부** — 관계 traversal 은 강력하지만, XBRL 재무 같은 정확한 수치를 store + 시계열 집계가 약함 (Cypher 의 numeric aggregation 은 SQL 의 window function 보다 표현력 부족). 또 pgvector 의 ivfflat/hnsw 같은 ANN 인덱스가 없어 대량 청크 의미 검색이 느림.
- **PostgreSQL 단독 거부** — pgvector + JSONB 로 모든 것을 담을 수 있지만, 다중 홉 그래프 traversal (예: `(:Manufacturer)-[:CONTAINS_MODULE*1..3]->(:Module)-[:SUPPLIED_BY]->(:Supplier)`) 을 SQL recursive CTE 로 흉내내면 쿼리 복잡도 폭발 + 인덱스 활용 불가. Neo4j 의 native graph storage 가 다중 홉에서 압도적.
- **PostgreSQL + pgvector 통합 (Qdrant 별도 거부)** — pgvector 가 PG 16 에 내장돼 운영 단순. 청크 수 < 100만 까지는 hnsw + 메타 필터가 충분히 빠름 (`retrieve.py`). Qdrant 는 분산·고성능 ANN 이지만 별도 노드 운영 + 메타 join 시 PG round-trip 비용 — 청크 ≥ 100만 도달 시 분리 옵션 (`docs/mental_model.md §3` 트레이드오프 박스).

→ **3-store 는 "올바른 도구를 올바른 일에" 원칙**. 각 store 가 자신이 가장 강한 질의 형태에만 호출되도록 worker 가 라우팅 (`agents/workers.py` 의 `research/graph/sql` 분리).

### 3.4 Entity Resolution 마스터 (`master.entities`)

`vehicle_id` 단일 중심 / `corp_code` 단일 중심으로는 자동차·특허·공정 도메인의 식별 체계를 다 담을 수 없다. **`entity_id` + `entity_type` 다형 키** 로 일반화:

```sql
CREATE TABLE master.entities (
    entity_id        VARCHAR PRIMARY KEY,        -- 내부 통합 ID (prefix+seq 또는 UUID)
    entity_type      VARCHAR NOT NULL,           -- manufacturer | supplier | vehicle_model
                                                  -- | vehicle_variant | component | recall | standard | plant
                                                  -- | (확장) process | process_step | material | mineral | patent | assignee
    canonical_name   VARCHAR NOT NULL,
    canonical_name_en VARCHAR,
    -- 외부 식별자 (entity_type에 따라 일부만 채워짐)
    wikidata_qid     VARCHAR,
    lei              VARCHAR,                    -- 법인만
    corp_code        VARCHAR,                    -- 한국 상장사만 (finance 연동 키)
    business_no      VARCHAR,                    -- 한국 법인만
    cik              VARCHAR,                    -- SEC 등록 법인만
    nhtsa_model_id   VARCHAR,                    -- 차량 모델만
    nhtsa_campaign_id VARCHAR,                   -- 리콜만
    -- 메타
    source_priority  INT,                        -- 1=primary, 2=alias, ...
    confidence_score NUMERIC,
    valid_from       DATE,
    valid_to         DATE,
    schema_version   VARCHAR,
    created_at       TIMESTAMP DEFAULT NOW(),
    updated_at       TIMESTAMP DEFAULT NOW()
);
```

**엔티티 타입별 권장 식별자:**

| 엔티티 타입 | 권장 식별자 |
|---|---|
| Manufacturer / Supplier | `entity_id`, `wikidata_qid`, `lei`, `corp_code` |
| Vehicle Model | `entity_id`, `wikidata_qid`, `nhtsa_model_id` |
| Vehicle Variant (Trim/Year) | `entity_id` (내부 생성) |
| Component | `entity_id` (내부 생성) |
| Recall | `entity_id`, `nhtsa_campaign_id`, `car_go_kr_id` |
| Patent / Assignee (ip 보조축) | `entity_id`, `wikidata_qid` (`ip.patents` 외부 PK 별도) |

**동명이인 인물:** `master.persons` 는 `(name, birth_year)` 분리 키. 충돌 빈도가 높은 이름은 `(name, birth_year, 회사)` 보조 키 (P1, §12.4).

**finance 연동:** `entities.corp_code` 가 채워진 행이 곧 `bridge.corp_entity` 후보. 동일 corp_code 가 다양한 `entity_type` (manufacturer + supplier) 으로 동시에 등장 가능.

#### 3.4.1 마이그레이션 1:1 매핑 (finance ↔ auto)

`master.companies` 단일 중심에서 `master.entities` 다형으로 일반화하면서, finance 도메인 자산 ↔ auto 도메인 자산은 다음 1:1 매핑으로 통합:

| finance (AutoNexusGraph 원본) | auto (AutoGraph 흡수) | 변경 정도 |
|---|---|---|
| `master.companies` | `master.entities` (entity_type='manufacturer') | **통합 ER 로 일반화** |
| `master.persons` | `master.entities` (entity_type='supplier') 또는 별도 `master.persons` 유지 | 도메인 선택 |
| `master.entity_map` | `master.entities` 안에 흡수 | **단일 테이블로 통합** |
| `fin.financials` | `spec.measurements` | 시계열 구조 동일 |
| `fin.filings` | `doc.manuals` | 메타 구조 동일 |
| `news.articles` | `events.recalls` + `events.complaints` | 시점·멘션 구조 동일 |
| `wiki.*` | `wiki.*` | **완전히 동일** |
| `vec.chunks` | `vec.chunks` | **완전히 동일** (메타에 `entity_id`) |
| Neo4j `Company` 노드 | `Manufacturer` + `VehicleModel` + `VehicleVariant` + `Component` + `Supplier` + `Recall` | 라벨 다양화 |
| `SUBSIDIARY_OF` | `MANUFACTURES` / `CONTAINS_*` (계층 main_hop) | 메인 홉 등급 부여 |
| `EXECUTIVE_OF` | `SUPPLIED_BY` / `MANUFACTURED_AT` | 인적 → 공급망 |

**핵심 원칙:** 인프라(Docker/Neo4j/PG/pgvector) · LangGraph multi-agent · Safety guards · BGE-M3 임베딩 · LLM 어댑터는 **그대로**. 도메인별로 다른 것은 (a) 데이터 소스 (b) 핵심 엔티티 (c) 핵심 관계 (d) 정량 수치 (e) 이벤트 — 도메인 어댑터 패키지가 흡수. ip 보조축도 동일 패턴 (`src/ipgraph/` plug-in).

### 3.5 Bridge 일반화 — `bridge.corp_entity`

v0 의 `bridge.corp_manufacturer` (완성차 OEM 만) 는 부족하다. **실제 Cross-Domain 가치는 배터리사·반도체사·타이어사·ADAS 공급사·특허 assignee 까지 확장될 때 발현.** v2.1 부터 일반화:

```sql
CREATE TABLE bridge.corp_entity (
    bridge_id         BIGSERIAL PRIMARY KEY,
    corp_code         VARCHAR NOT NULL,         -- finance 키
    entity_id         VARCHAR NOT NULL,         -- master.entities.entity_id
    entity_type       VARCHAR NOT NULL,         -- manufacturer | supplier (battery/component/semi/tire/ADAS …)
    -- 매칭에 사용된 식별자들 (감사·재현용)
    wikidata_qid      VARCHAR,
    lei               VARCHAR,
    cik               VARCHAR,
    business_no       VARCHAR,
    -- 매칭 메타
    match_method      VARCHAR NOT NULL,         -- qid_exact | lei_exact | business_no_exact
                                                 --   | corp_code_exact | fuzzy_name | manual
    confidence_score  NUMERIC NOT NULL,         -- 0.0 ~ 1.0
    -- 시점
    valid_from        DATE,
    valid_to          DATE,
    -- 거버넌스
    source            VARCHAR,                  -- wikidata | gleif | manual | derived
    reviewed_status   VARCHAR DEFAULT 'auto',   -- auto | reviewed | rejected
    reviewed_by       VARCHAR,
    reviewed_at       TIMESTAMP,
    schema_version    VARCHAR,
    created_at        TIMESTAMP DEFAULT NOW(),
    UNIQUE(corp_code, entity_id, valid_from)
);
```

**매칭 우선순위 (Confidence 산정):**
1. `wikidata_qid` exact match → 0.95
2. `lei` exact match → 0.93
3. `business_no` exact match → 0.90
4. `corp_code` direct (finance entity_map → auto 직접) → 0.95
5. Fuzzy name match (한글·영문 normalize 후) → 0.60~0.75
6. Manual → 1.00

**Confidence < 0.7 자동 `needs_review` 큐.** `reviewed_status='rejected'` 자동 제외 (bridge tool 도 동일).

**현황 (2026-06-01):** 4,806 row (manufacturer reviewed 11 / supplier candidate 4,792 / supplier reviewed 4 + 기타). strong_match (confidence ≥ 0.9) **15/15 = 100%** (manufacturer 11 + supplier 4). 4,792 supplier candidate 의 검토 운영 SOP 는 §12.4 (P1) 대기.

**Bridge tool 시그니처** (`src/autograph/tools/bridge.py`):
- `bridge_corp_to_entity(corp_code, *, entity_type=None, min_confidence=0.0, include_candidate=True)` → corp_code → 가능한 모든 entity (manufacturer/supplier/vehicle_model/variant). confidence 내림차순.
- `bridge_entity_to_corp(entity_id, entity_type, *, include_candidate=True)` — `entity_type` 필수.
- `bridge_sec_cik_to_entity(sec_cik, *, entity_type="manufacturer")` — 글로벌 OEM 진입점 (CIK 10자리 자동 zfill).
- `bridge_entity_to_sec_cik(entity_id, entity_type="manufacturer")`.
- `cross_query(...)` — finance↔auto join helper.

**`VALID_ENTITY_TYPES`:** `("manufacturer", "supplier", "vehicle_model", "variant")` — 그 외는 `ValueError`.

**ip 도메인 미러:** `src/ipgraph/tools/bridge.py` 의 `bridge_assignee_to_corp` / `bridge_corp_to_assignee` / `cross_query_ip`. **`bridge.corp_entity` 직접 변경 회피** — 신규 join 테이블 `ip.assignee_corp_map` 가 supplier candidate 운영 SOP 재사용. §10.12 코어 변경 <5% 보존.

### 3.6 4-Pass + Bridge Pass 추출 전략

| Pass | 입력 | 방식 | 산출물 | LLM 비중 |
|---|---|---|---|---|
| **P1 (Det)** | NHTSA vPIC / KNCAP / NCAP / EPA / DART XBRL | 직접 매핑 | `spec.measurements` · `fin.financials` | 0% |
| **P2 (Det)** | 자동차리콜센터 정형 / 공개 BOM / DART 지배구조 | 직접 매핑 | Neo4j 계층 + AFFECTED_BY / SUBSIDIARY_OF | 0% |
| **P3 (LLM)** | 매뉴얼·결함신고·IR 본문 | Schema-aware LLM 추출 (selective) | 관계 후보 (SUPPLIED_BY 등) | 100% (대상 한정) |
| **P4 (Validate)** | P3 산출 + P1/P2 + 출처 등급 | confidence 산정 + cross-validate | validated 관계 (§4.0 정책) | 보조 |
| **P5 (Bridge)** | `entities.wikidata_qid` ↔ finance entity_map | 직접 매핑 + fuzzy fallback | `bridge.corp_entity` | 0% |

**Deterministic-first 원칙:** 재무·제원·지배구조·공정명·CPC 분류 같은 정형 데이터는 절대 LLM 이 생성하지 않는다. LLM 은 매뉴얼/IR/리콜본문 같은 비정형에서 "관계 후보" 만 뽑고, P4 에서 외부 출처와 cross-validate 후 승급.

### 3.7 관계 엣지 필수 메타데이터 (7키)

**필수 7키 — `EDGE_REQUIRED_META_KEYS` SSOT** (`src/autonexusgraph/ontology/schema.py:28-36`):

1. **`source_type`** — `recall | ir_disclosure | manual | wikidata | wikipedia | llm_extraction | manual_curation | dart_*` 등
2. **`source_id`** — `NHTSA-25V-001 | DART-20240315-... | chunk_id:...`
3. **`confidence_score`** — `0.0 ~ 1.0` (할당값. fail 임계 0.5 와 구별, §4.0)
4. **`validated_status`** — `candidate | validated | rejected | needs_review`
5. **`snapshot_year`** — `2024` (해당 데이터의 측정·발표 연도)
6. **`extraction_method`** — `deterministic | llm | hybrid | manual`
7. **`schema_version`** — yaml 헤더의 ontology 스키마 버전 (`_helpers.ontology_schema_version()` 자동 부여)

`ontology/<domain>/relations.yaml::edge_required_meta` 가 7키와 정확히 일치하지 않으면 `audit-ontology` fail (`scripts/audit/ontology_validate.py`).

**옵션 키 (라이프타임 / 거버넌스 — 일부 관계만):**
- `source_url` — 인용 URL (recall / wikipedia / IR 등)
- `extractor_version` — `p2-v1 | p3-llm-v2 | ...`
- `valid_from` / `valid_to` — **라이프타임 엣지에만** (`SUPPLIED_BY`, `MANUFACTURED_AT`, `COMPLIES_WITH` 등 시점 구간이 의미 있는 관계). 일회성 엣지 (예: `RECALL_OF`) 는 미사용.
- `created_at` — 적재 시각 (`datetime()`)
- `reviewed_by` — 수동 검토자 ID

```cypher
CREATE (a)-[r:SUPPLIED_BY {
    // ── 필수 7키
    source_type:        'manual_supplier_seed',
    source_id:          'supplier_seed.yaml#row42',
    confidence_score:   0.95,
    validated_status:   'validated',
    snapshot_year:      2024,
    extraction_method:  'manual',
    schema_version:     'v2.2',
    // ── 라이프타임 (이 관계는 시점 구간이 있음)
    valid_from:         date('2024-01-01'),
    valid_to:           date('2024-12-31'),
    // ── 거버넌스 (선택)
    source_url:         'https://...',
    created_at:         datetime(),
    reviewed_by:        'admin'
}]->(b)
```

**Validator Agent 강제 규칙** (코드 SSOT — `agents/validator.py:125-162`):
- `validated_status='candidate'` 엣지는 답변 인용 시 "후보 정보" 명시
- `validated_status='rejected'` 엣지는 쿼리 시 자동 제외 (bridge tool 도 동일)
- `confidence_score < 0.5` 엣지는 단독 근거 금지 (`LOW_CONFIDENCE_THRESHOLD=0.5`). 전부 < 0.5 → `all_low` hard fail → replan. 일부만 → `some_low` soft warning.
- 7키 invariant 검증은 `make audit-edge-meta --strict` (`scripts/audit/edge_meta_invariants.py`).

---

## 4. 데이터 소스

모든 데이터는 공개·합법 출처만 사용 (무단 크롤링·약관 위반 금지). 라이선스별 본문 저장 정책은 `src/autonexusgraph/ingestion/_license.py` 가 코드 레벨에서 강제.

### 4.0 출처별 신뢰도 등급 (A/B/C)

모든 그래프 엣지는 출처 등급에 따라 `confidence_score` **할당값**이 결정된다.

> **두 개념을 구별 — 동일한 0.5 라는 숫자가 의미하는 바가 다르다:**
> - **할당값 (`confidence_score`)** — ingestion·loader 가 엣지 생성 시점에 출처 등급에 따라 부여하는 신뢰도. LLM 추출(P3) 의 기본 할당값이 **0.50**.
> - **fail 임계값 (`LOW_CONFIDENCE_THRESHOLD = 0.5`)** — `agents/validator.py:43` 의 답변 검증 게이트. 답변 근거 그래프 엣지의 `confidence_score < 0.5` 면 hard fail (`all_low`) 또는 soft warning (`some_low`). 단독 근거 금지.

| 출처 | 신뢰도 등급 | 기본 confidence_score | 적용 관계 |
|---|---|---|---|
| NHTSA / 자동차리콜센터 공식 리콜 | **A (높음)** | 0.95 | `AFFECTED_BY`, `RECALL_OF` |
| NHTSA vPIC | **A** | 0.95 | `MANUFACTURES`, `HAS_VARIANT` |
| KNCAP / NCAP / Euro NCAP | **A** | 0.95 | `SAFETY_RATED_BY` |
| DART 사업보고서 (XBRL · 지배구조) | **A** | 0.95 | `SUBSIDIARY_OF`, `EXECUTIVE_OF`, `MAJOR_SHAREHOLDER_OF` |
| USGS Mineral Commodity Summaries | **A** | 0.95 | `DERIVED_FROM` |
| 팩토리온 공장 등록 (data.go.kr 15087611) | **A** | 0.95 | `PERFORMED_AT` (회사 귀속 공정) |
| KAMA 거시 생산 통계 | **A** | 0.95 | `macro.*` |
| KOSIS 광공업동향 | **A** | 0.95 | `macro.kosis_series` |
| Wikidata | **B (중간)** | 0.80 | 글로벌 ID 매핑, `MANUFACTURES` (보조) |
| DART 사업보고서 III. 생산·설비 (가동률) | **B** | 0.80 | `MANUFACTURED_AT` (시점) |
| Wikipedia | **B~C** | 0.70 | 설명 문서, 보조 근거 |
| 부품사 IR (공식 공시) | **B** | 0.75 | `SUPPLIED_BY` (후보) |
| 매뉴얼 / 브로셔 | **B** | 0.75 | `CONTAINS_*` (시스템·모듈) |
| KAMP 제조AI 데이터셋 (data.go.kr 15089213) | **B (익명)** | 0.80 | `auto.process_metrics` (회사 비귀속) |
| AI Hub 제조 멀티모달·품질 | **B (익명)** | 0.80 | `vec.chunks` + ProcessStep 통계 속성 (회사 비귀속) |
| LLM 추출 (P3) | **C** | 0.50 | P4 cross-validate 필수. validator 임계와 같은 0.5 — 단독 근거 시 soft warning |
| 산단공 합성 공정사전 (15151075) | **C (합성)** | 0.50 | `:Process` taxonomy 전용 (회사 귀속 엣지 hard-check 차단) |
| 커뮤니티 / 분해 자료 | **C (낮음)** | 0.40 | 후보 추출만, 확정 관계 금지. validator 임계 미달 — hard fail 가능 |
| 수동 검토 확정 | **A+** | 1.00 | 모든 관계 |

**`validated_status='validated'` 승급 정책:**
- `SUPPLIED_BY` 등 공급 관계는 **A 또는 B 출처 + P4 cross-validate 통과** 시에만 `validated`
- 그 외는 `candidate` 또는 `needs_review`
- C 등급 단독 출처는 절대 `validated` 금지
- **회사 귀속 공정 엣지 (`PERFORMED_AT`)** 는 `load_performed_at.py` 의 source allowlist hard-check 로 DART / factoryon / manual_seed 만 허용 — 산단공 / KAMP / AI Hub 합성·익명 출처는 자동 차단

> **⚠️ Calibration 미검증 (P1) — 실측 routine wired (2026-06-02)**: 본 표의 confidence 할당값 (A=0.95 / B=0.80 / C=0.50) 이 실제 정답률과 단조 관계인지 미실측 (LLM 키 부재로 gold QA 측정 결과 EM=0/120). 측정 인프라 완료: `scripts/audit/calibrate_confidence.py` — Platt scaling + 10-bin reliability diagram + overconfident/underconfident 자동 분류. `make audit-calibrate` 1줄 실행. **LLM 키 활성 후 `make eval-full` → `make audit-calibrate` 1회**.

### 4.0.1 row 단위 동적 confidence 격상 (auto 공정 데이터 전용)

§4.0 정적 등급표는 **데이터셋 단위 할당값**이다. 이와 별개로, 합성/LLM 등 **C 등급 출처의 row 도 외부 A/B 출처 시그널이 충분히 누적되면 row 단위로 0.80 (B) 까지 승급**할 수 있다 — 현 단계 운영 대상은 **`auto.processes` (산단공 합성 15151075, C 0.50) 단독**, 410 공정명 중 외부 매칭 가능한 row 한정 (예상 격상률 15~30%, 70~85% 는 C 유지).

> 정적 등급표 행 추가가 **아닌** row 단위 동적 컬럼 갱신이므로 §4.0 본문·기존 SSOT (`src/autograph/ingestion/_confidence.py::SOURCE_TO_GRADE`) 무변경. `agents/validator.py:LOW_CONFIDENCE_THRESHOLD = 0.5` 도 무변경. 격상 후 row 가 validator 게이트를 자연 통과.

**격상 시그널 (cross_validate 8 시그널 — `src/autograph/extractors/process_confidence.py` SSOT)**:

| 시그널 | 매칭 후보 | 가중 w | grade boost |
|---|---|---:|---|
| M1 | NHTSA `:Module` taxonomy (KO-EN 사전 매핑) | 0.15 | A (1.00) |
| M2 | DART 사업보고서 narrative BGE-M3 cos ≥ 0.78 | 0.15 | B (0.80) |
| M3 | OEM IR/뉴스 본문 regex mention ≥ 1 | 0.10 | B (0.80) |
| M4 | KSIC C30xxx 산업분류 직접 매핑 | 0.05 | A (1.00) |
| M5 | DART `plant_capacity.product_name` 토큰 overlap ≥ 0.5 | 0.10 | B (0.80) |
| M6 | NHTSA recall `component_text` + LLM P3 → `CAUSED_BY_PROCESS` (P4 검증 후) | 0.10 | A (0.95) |
| M7 | KS X 9001 + ISO 18629 PSL manual seed 정확 매칭 | 0.05 | A (1.00) |
| C1 | 충돌 시그널 (예: M1 매핑 component vs M6 무관 카테고리) | — | penalty −0.20 |

**계산 식**:

```
conf = clip(0.50 + Σ w_i · s_i · grade_i − 0.20 · |conflicts|, 0.30, 1.00)
```

이론 max boost = +0.70 (clip 시 0.95). 평균 시나리오 (M1+M2+M3 일치): 0.50 + 0.15 + 0.12 + 0.08 = **0.85 → B 격상**.

**승급 후 정책**:
- `confidence_score ≥ 0.80` → row UPDATE 후 validator 게이트 자연 통과
- `validated_status` 는 별도 — A/B 출처 + P4 통과 시에만 `validated`. **C 단독 격상은 `candidate` 유지** (§4.0 단독 근거 금지 원칙 보존).
- 답변 인용 시 "산단공 합성 + 외부 N개 소스 cross-validated" 출처 표시 의무

**SSOT 분리**:
- 정적 등급: `src/autograph/ingestion/_confidence.py::SOURCE_TO_GRADE` (변경 없음)
- 동적 격상: `src/autograph/extractors/process_confidence.py` (P0-B 시그니처 + P3-B 구현)
- staging: `auto.staging_process_signals` (`infra/postgres/init/16_process_signals.sql`)
- 운영: `scripts/upgrade_processes_confidence.py` (1회 풀런 ≤ $2 + GPU 1분, idempotent)

---

| 데이터 | 출처 | 라이선스 | 적재 위치 |
|---|---|---|---|
| 사업보고서·공시 | DART Open API | 공공 | `data/raw/dart_bulk/` → `vec.chunks` + `fin.filings` |
| 재무제표 (XBRL) | DART | 공공 | `fin.financials` |
| 지배구조 (자회사·임원·최대주주) | DART | 공공 | Neo4j SUBSIDIARY_OF / EXECUTIVE_OF / MAJOR_SHAREHOLDER_OF |
| 상장사 마스터 | KRX | 공공 | `master.companies` |
| 거시지표 | 한국은행 ECOS | 공공 | `macro.series` |
| Wikipedia 본문·Infobox | ko.wikipedia.org | CC BY-SA | `wiki.wikipedia_pages` + `vec.chunks` (section=wikipedia_ko) |
| Wikidata 글로벌 ID·CEO·자회사 | query.wikidata.org | CC0 | `wiki.wikidata_facts` + `master.entity_map` |
| 연합뉴스 RSS | 연합뉴스 | 저작권 | `news.articles` (메타+요약만) |
| SEC EDGAR (ADR) | sec.gov | 공공 | `sec.filings` |
| GLEIF LEI | gleif.org | CC BY 4.0 | `sec.lei` + `master.entity_map` |
| KCGS ESG 등급 | cgs.or.kr | 회원 (수동) | `esg.ratings` + Neo4j Company 속성 |
| 공정위 기업집단 | data.go.kr | 공공 | (키 확보 후) Neo4j Group + BELONGS_TO_GROUP |
| KOSIS 산업 통계 | kosis.kr | 공공 | (키 확보 후) `macro.kosis_series` |
| LAW.go.kr 법령 | open.law.go.kr | 공공 | (키 확보 후) `law.laws` |
| GLEIF ↔ OpenCorporates 관계 파일 | gleif.org (LEI↔OC 오픈소스 매핑) | CC0 / 오픈 | `sec.lei` + `master.entity_map` (LEI 매칭 보강) |
| 글로벌 법인 식별자 (145 관할권 2.3억+) | OpenCorporates API | 오픈 (share-alike — `_license.py` 게이트) | `master.entity_map` (비상장 부품사·자회사 보강) |

**수집 범위 (1차):** 코스피 200 + 코스닥 100 약 300개사, 최근 3개 회계연도.
**제조 데이터 끝까지 채움 (wired, partial — 키 확보 대기):**
- `DATA_GO_KR_API_KEY` → 팩토리온 [15087611](https://www.data.go.kr/data/15087611/openapi.do) (ingestion `factoryon_registry.py` + loader `load_factoryon.py` → `auto.factoryon_registry` PG `24_auto_factoryon.sql`. `make load-factoryon`)
- 자동차 리콜 [3048950 (CSV)](https://www.data.go.kr/data/3048950/fileData.do) (구 오픈API 15089863 폐기) + 검사 [15155857](https://www.data.go.kr/data/15155857/fileData.do) (ingestion + `load_datagokr_*.py`)
- DART 사업보고서 **가동률 표** 파서 — `dart_production_parser._parse_utilization_table` → `auto.plant_utilization` PG 적재 (`load_dart_production.py:199`). 완료.
- KOSIS 산업 통계 — `kosis_client.py` + 신규 loader `load_kosis_industry.py` → `macro.kosis_series` (`make load-kosis`). KOSIS_API_KEY 필요.
- Wikidata 배터리 셀 chem (cathode) — 신규 `wikidata_cell_chem.py` (CC0, 무인증). materials_seed.yaml 의 manual seed 보강. **회사단위 셀↔OEM 소싱은 grade C candidate 정직 표기** (§2.3).

모두 정형 — LLM 0%. 라이선스: `public_domain` / `kogl_type1` (KOSIS / DATA_GO_KR).
**범위 외 (Out-of-Scope):** 빅카인즈 본문, 나무위키(CC BY-NC-SA), 종목토론방, LinkedIn, Twitter.

### AutoGraph 데이터 소스

| 데이터 | 출처 | 라이선스 | 인증 | 적재 위치 |
|---|---|---|---|---|
| 차량 마스터·제원 (전 세계 vPIC) | NHTSA vPIC API | 공공 (US Gov) | 불필요 | `auto.master_*` |
| 리콜 캠페인 | NHTSA Recalls API | 공공 | 불필요 | `auto.events_recalls` + Neo4j Recall |
| 결함 신고 | NHTSA Complaints API | 공공 | 불필요 | `auto.events_complaints` + `vec.chunks` |
| 제조사·모델·공급사 QID·LEI·사업자번호 | Wikidata SPARQL | CC0 | 불필요 (rate limit) | `auto.master_*` + `bridge.corp_entity` |
| 자동차 리콜정보 (한국) | data.go.kr [3048950 (CSV)](https://www.data.go.kr/data/3048950/fileData.do) | 공공 | (무인증 CSV) | `auto.events_recalls` 941행 적재 (CSV 전량) |
| 자동차검사관리 수리검사내역 (사고·침수·도난 차량 검사) | data.go.kr [15155857](https://www.data.go.kr/data/15155857/fileData.do) (파일 다운) | 공공 | 불필요 (파일) | `data/raw/datagokr/` → (적재 후) `auto.events_inspections` |
| 시험인증 (KATRI / 부품 인증) | bigdata-tic.kr Open API | 공공 (회원) | OAuth `BIGDATA_TIC_CLIENT_ID/SECRET` | (키 확보 후) `auto.cert_*` |
| 안전등급 (NCAP) | NHTSA SafetyRatings API | 공공 (US Gov) | 불필요 | `auto.spec_measurements` (safety.ncap.* / safety.feature.*) + Neo4j `(:VehicleVariant)-[:SAFETY_RATED_BY]->(:Standard {code:'NCAP_US'})` |
| ODI 결함 조사 (리콜 전단계) | NHTSA Investigations bulk | 공공 (US Gov) | 불필요 | `auto.events_investigations` + Neo4j `(:VehicleModel)-[:INVESTIGATED_BY]->(:Investigation)` |
| 차량 연비·엔진·배출 spec | EPA fueleconomy.gov bulk CSV | 공공 (US Gov) | 불필요 | `auto.spec_measurements` (spec.efficiency.* / spec.engine.* / spec.emissions.*) |
| 글로벌 OEM 재무 (Ford/GM/Stellantis/Toyota/Honda/Tesla …) | SEC EDGAR Company Facts (XBRL) | 공공 | UA 필수 | `auto.oem_financials_sec` + `bridge.corp_entity.sec_cik` 강화 |
| 제조사 통신문 / TSB | NHTSA Manufacturer Communications (수동 zip) | 공공 (US Gov) | 불필요 | `vec.chunks` (source='nhtsa_tsb') |
| 안전등급 (KNCAP) | car.go.kr (수동 / 별도 API) | 공공 | (지정 채널) | (후속) `auto.spec_measurements` + `:Standard {code:'KNCAP'}` |
| Euro NCAP / IIHS (옵션) | euroncap.com / iihs.org | 공공 (사용 약관) | 불필요 | (후속) `auto.spec_measurements` + `:Standard` (Euro NCAP / IIHS TSP) |
| 제조 공정·생산능력 (제조 도메인) | DART 사업보고서 본문 파서 | 공공 | DART 키 (finance 와 공유) | `auto.production_*` (LLM 0% — 정규식 + 표 파서) |
| 산단공 합성 공정데이터 (15151075) | data.go.kr (수동 CSV) | 공공 | 불필요 (파일) | `auto.processes` + Neo4j `:Process` 410 / `:ProcessStep` 550 / `PRECEDES`·`INSTANTIATES` (BoP routing, grade C). SSOT [docs/process_graph.md](./docs/process_graph.md) |
| 공장 등록정보 (15087611) — 회사·공장번호·산단별 조회 | data.go.kr 팩토리온 (`apis.data.go.kr/B550624`) | 공공 | `DATA_GO_KR_API_KEY` (작동 확인) | `auto.factoryon_registry` 90행 적재 (OEM 5사 + tier-1) → MANUFACTURED_AT 보강 |

> 인증 키 부재 시 ingestion 은 graceful skip — 코드 변경 없이 `.env` 만 채우면 활성화.

### IPGraph 데이터 소스 (예정 — 본 PR outline · 후속 PR ingestion)

> 상세 설계·온톨로지·gold QA SSOT 는 [docs/ipgraph.md](./docs/ipgraph.md). 배터리·소재 표는 본 절 아님 — auto 의 L5/L6 확장 (다음 표).

| 데이터 | 출처 | 라이선스 | 인증 | 적재 위치 | 상태 |
|---|---|---|---|---|---|
| 한국 특허·출원 | KIPRIS Open API (공공데이터포털) | 공공 (검색·서지 무료 / **본문·대량은 KIPRISPLUS 회원·일부 비공개**) | `KIPRIS_API_KEY` | `ip.patents` + Neo4j Patent | (scaffold, 보조) |
| 미국 특허·인용·assignee 정규화 | **USPTO Open Data Portal (data.uspto.gov)** — PatentsView 후속 | 공공 (US Gov) | **이관 완료 (2026-03-20)** — `search.patentsview.org` REST 종료(410 Gone), **ODP bulk dataset + Transition Guide** 채택 | `ip.patents` + `ip.citations` | (scaffold, 보조) |
| CPC 분류 체계 (계층 depth ≥ 4) | CPC scheme bulk (USPTO / EPO) | 공공 | 불필요 | `ip.cpc_scheme` + Neo4j CPCCode/SUBCLASS_OF | ✅ **10,695 row 적재** (§1 IPGraph 현황표) |
| 글로벌 논문·연구 (assignee↔institution↔author) | OpenAlex API | CC0 | **무료 키 필요 (하루 10만 크레딧, 2025-02 이후)** | `ip.works` + Neo4j Work/Institution/Author | ✅ **629 row 적재** — 특허×논문 cross 승격은 institution↔corp_entity 매핑 후속 |

### 배터리·소재 보완 (auto 의 L5/L6 확장 — 예정)

> ip 도메인이 아님. `(:Module {배터리팩})-[:CONTAINS_MODULE]->(:Cell)-[:MADE_OF]->(:Material {NCM811})-[:DERIVED_FROM]->(:Mineral {Ni})` BOM 하향. 상세는 [docs/autograph.md](./docs/autograph.md) §2.5.4.

| 데이터 | 출처 | 라이선스 | 적재 위치 | 상태 |
|---|---|---|---|---|
| 배터리 화학조성 (NCM/LFP 등 셀 chem) | Wikidata + 셀 제조사 공개 IR PDF | CC0 / 공공 | `auto.master_materials` | (예정) |
| 핵심광물 (Li/Ni/Co/Mn/흑연) 세계·미국 통계 | USGS Mineral Commodity Summaries (MCS 2025 PDF) | 공공 (US Gov) | `auto.master_minerals` + Neo4j `:Mineral` / `:Material` / `:DERIVED_FROM` | ✅ **2024 estimate 5종 적재** — Li/Ni/Co/Mn/Graphite, 6 Material × 5 Mineral × 17 DERIVED_FROM (7-key 100%) |
| 광물 수입 통계 (한국) | 관세청 무역통계 / 무역협회 K-stat | 공공 | `macro.trade_minerals` | (예정) |
| 회사단위 소싱 (셀 ↔ OEM) | 공개 IR 부분 — grade C candidate | 공공 (sparse — 정직 표기) | `auto.staging_relations` (candidate) | (예정, 한계 명시) |

### EV 충전 인프라 (auto 의 EV 확장 — 예정)

> Operator(운영기관) → `bridge.corp_entity` 로 "충전 인프라 운영사 ↔ 재무" cross-domain. 이미 보유한 `DATA_GO_KR_API_KEY` 재사용.

| 데이터 | 출처 | 라이선스 | 인증 | 적재 위치 | 상태 |
|---|---|---|---|---|---|
| 전국 충전소 위치·운영정보 (운영기관·충전기타입·충전용량·설치년도) | data.go.kr 한국환경공단 (`apis.data.go.kr/B552584/EvCharger`) | 공공 | `DATA_GO_KR_API_KEY` | `auto.ev_chargers` + Neo4j `:ChargingStation` | (예정) |
| 지역별 급속충전기 설치현황·실제 이용량 | data.go.kr 한국에너지공단 (`apis.data.go.kr/B553530/TRANSPORTATION/ELECTRIC_CHARGING`) | 공공 | `DATA_GO_KR_API_KEY` | `auto.ev_charger_usage` | (예정) |

---

## 5. 에이전트 도구 (사전 정의 함수 풀)

자유 SQL/Cypher/벡터 호출은 금지. LLM 은 함수명 + 파라미터만 결정. SQL injection / 그래프 폭발 / 토큰 폭발 차단 (§7.5.10).

### `tools/financials.py` — PG 정형
- `lookup_company(query, limit)` — 이름·종목코드·corp_code 매칭
- `get_company_info(corp_code)` / `get_revenue(corp_code, year)` / `get_operating_income(corp_code, year)`
- `get_balance_sheet_item(corp_code, year, item)`
- `compare_companies(corp_codes, year, metric)` / `list_companies_by_market(market)`

### `tools/graph.py` — Neo4j 그래프 탐색
- `lookup_company(query, limit)` — Wikidata QID / Wikipedia title 까지 반환
- `lookup_person(name, birth_year=None)` — 동명이인 안전 매칭
- `list_subsidiaries(parent_corp_code, include_related=False, snapshot_year=None)`
- `list_parents(corp_code_or_name)` — 모회사 추적
- `get_executives(corp_code, role_contains=None, snapshot_year=None)` — `대표`, `사외이사` 등 substring
- `get_companies_of_person(name, birth_year=None, role_contains=None)`
- `get_major_shareholders(corp_code, min_pct=0.0, snapshot_year=None)`
- `find_paths(start_corp_code, end_corp_code, max_hops=3)` — 두 회사 최단 경로
- `get_subgraph(corp_code, depth=1, limit_nodes=50)`
- `list_mentioning_news(corp_code)` / `list_cooccurring(corp_code)` / `list_group_members(group_name)`

### `tools/retrieve.py` — Hybrid 검색
- `search_documents(query, top_k=8, corp_code=…, fiscal_year=…, source=…, section_contains=…)` — pgvector 코사인 + 메타 필터
- `search_by_metadata(corp_code=…, fiscal_year=…, source=…)` — 임베딩 무관, 결정적 fetch
- `get_chunk(chunk_id)` — 단일 청크 + 메타

답변은 항상 **출처(chunk_id / corp_code / rcept_no / 노드ID) + 회계연도** 명시. 불확실하면 "정보 부족" 응답.

### AutoGraph tools (`src/autograph/tools/*`)

도메인 `auto` / `cross_domain` 모드에서만 활성. workers 화이트리스트로 강제.

- **`spec.py`** — `lookup_vehicle` / `get_vehicle_info` / `get_spec` / `compare_vehicles` / `get_safety_rating` / `get_oem_financials_sec` (PG SQL — SEC OEM facts)
- **`graph.py`** — `lookup_vehicle_graph` / `lookup_supplier` / `list_components` / `list_systems_of_model` / `list_models_with_system` / `list_recalls_affecting` / `list_investigations_affecting` / `get_investigation_recall_chain` / `get_suppliers_of_component` / `get_vehicles_using_component` / `find_vehicle_component_paths` (Cypher 템플릿 `auto_*` 경유)
- **`retrieve.py`** — `search_documents_auto` / `search_by_metadata_auto` / `get_chunk_auto` (pgvector + manufacturer_id/model_id/variant_id 필터, source ∈ nhtsa_recall/complaint/tsb/wikipedia_auto/aihub/epa)
- **`bridge.py`** — `bridge_corp_to_entity` / `bridge_entity_to_corp` / `bridge_sec_cik_to_entity` / `bridge_entity_to_sec_cik` / `cross_query` (한국 corp_code 와 글로벌 SEC CIK 양방향 매칭, `reviewed_status='rejected'` 제외)

### IPGraph tools (`src/ipgraph/tools/*`) — 구현 완료
도메인 `ip` / `cross_domain` 에서만 활성. workers 화이트리스트 (`IPGraphHandler.allowed_intents`) 로 강제. **코드 구현 완료** — `cypher_templates_ip.py` 25 templates + 4-tools 미러. 데이터는 CPC scheme + OpenAlex works 만 적재 (line 89, 92), 특허 자체는 KIPRIS/USPTO ODP 적재 대기. 상세 시그니처·온톨로지·gold QA SSOT 는 [docs/ipgraph.md](./docs/ipgraph.md).

- **`patents.py`** — `lookup_patent` / `get_patent_info` / `list_patents_by_assignee` / `count_patents_by_field` / `compare_assignees_patent_volume`
- **`graph.py`** — `lookup_assignee_graph` / `list_patents_of_assignee` / `get_inventors_of_patent` / `find_co_assignees` / `list_patents_in_cpc(include_subclasses=True)` / `list_assignees_in_field` / `get_citation_network(depth≤2, limit_nodes≤300, max_total≤1000, direction ∈ cited_by|cites|both)` / `most_cited_patents` — Cypher 템플릿 `ip_*` (~25 = lookup 5 + assignee 6 + cpc 6 + citation 4 + cross 4)
- **`retrieve.py`** — `search_patents` / `search_by_metadata_ip` / `get_chunk_ip` (abstract+claims pgvector + `assignee_id`/`cpc`/`jurisdiction` 메타 필터)
- **`bridge.py`** — `bridge_assignee_to_corp` / `bridge_corp_to_assignee` / `cross_query_ip` (특허 ↔ finance R&D비·영업이익 ↔ auto 부품·리콜). **신규 join 테이블 `ip.assignee_corp_map`** — `bridge.corp_entity` 직접 변경 없음, supplier candidate 운영 SOP (4,792 row) 재사용

---

## 6. 평가 전략

### 평가셋 구성
- 공개 벤치마크: Allganize RAG-Evaluation-Dataset-KO (금융) — **외부 벤치 (자기충족성 완화 신호)**
- 자체 구축 Multi-hop QA — 도메인 내 100문항 + Cross-Domain 30문항
  - finance: `eval/qa_gold/gold_qa_v0.jsonl` — L1/L2/L3 — seed 30 (목표 100)
  - auto: `eval/qa_gold/gold_qa_auto_v0.jsonl` — L1/L2/L3 — seed 46 (목표 100, **공정 L1~L3 10문항 포함 — AUTO0047+9 신규**)
  - cross: `eval/qa_gold/gold_qa_cross_v0.jsonl` — **44 row** (level 기준 CD-L1=10 / CD-L2=8 / CD-L3=12 / CD-L4=8 + 6 row 는 IP 결합 변형 — qid prefix `CD-L3-IP`/`CD-L4-IP`, level 필드 미설정) + **CD-Process 5 문항** (소재 리스크 + 생산↔거시 answerable 2종, 공정↔재무·결함전파 refusal 보존)
  - **ip: `eval/qa_gold/gold_qa_ip_v0.jsonl` — IP-L1/L2/L3 각 10 = seed 30 ✓** (gold_answer 채우기는 KIPRIS/USPTO 적재 후)

### Cross-Domain QA — 4단계 층화 (난이도별 목표 정답률)

> **"정답률" 측정 규칙** — 본 표의 "목표 정답률" 은 **LLM-as-judge** (Answer Accuracy, `eval/metrics/llm_judge.py`) 기준. 보조 메트릭으로 **EM/F1** (`eval/metrics/em_f1.py`) — 수치형은 EM, 서술형은 F1. 추가로 **hits@k** (`eval/metrics/hits_at_k.py`) 가 retrieval 단계 정합 측정.

| 난이도 | 정의 | 문항 수 | 목표 정답률 (LLM-as-judge) | 보조 메트릭 | 예시 |
|---|---|---:|---:|---|---|
| **CD-L1** | 제조사 ↔ 상장사 직접 Bridge | 10 | **80%+** | EM (수치) / hits@5 | "현대차가 제조한 모델의 리콜 건수와 현대차 영업이익을 같이 보여줘" |
| **CD-L2** | 차량 모델 ↔ 제조사 ↔ 재무 | 8 | **70%+** | EM + F1 | "쏘나타 DN8을 만드는 회사의 최근 3년 영업이익 추이는?" |
| **CD-L3** | 부품/공급사 ↔ OEM ↔ 재무 | 8~13 | **50~60%** | EM + F1 + hits@5 (multi-hop) | "LG에너지솔루션 배터리를 쓰는 차종을 가진 OEM의 최근 영업이익은?" |
| **CD-L4** | 시점 포함 공급망 ↔ 재무/ESG | 4~10 | **40~50%** | F1 + Confidence-Weighted Accuracy | "2023년 한온시스템에 공급계약 갱신한 OEM 중 KCGS ESG 등급이 B+ 이상인 회사는?" |

**각 QA 메타데이터:**
```json
{
  "id": "CD-L3-001",
  "question": "...",
  "answer": "...",
  "required_stores": ["AutoGraph.Graph", "Bridge", "Finance.SQL"],
  "required_confidence_min": 0.7,
  "hop_count": 4,
  "main_hop_path": ["Supplier", "Vehicle", "Manufacturer", "Financials"],
  "side_hops": [],
  "source_citations": ["..."]
}
```

### 비교 실험 매트릭스 — 저장소 명시

각 질문이 어느 저장소를 써야 풀리는지 명시하여 Hybrid 필요성을 정량 입증:

| 유형 | 예시 | 필요한 저장소 | 측정 시스템 |
|---|---|---|---|
| SQL-only | "2024 쏘나타 1.6T 출력은?" | PostgreSQL | 4종 |
| Vector-only | "NHTSA 불만에서 자주 언급된 증상은?" | pgvector | 4종 |
| Graph-only | "이 부품을 쓰는 차종은?" | Neo4j | 4종 |
| Graph + SQL | "리콜된 차종의 안전등급 평균은?" | Neo4j + PG | 4종 |
| Graph + Vector | "리콜 사유와 관련된 시스템 설명은?" | Neo4j + pgvector | 4종 |
| **Cross-Domain** | "공급사를 쓰는 OEM의 영업이익은?" | auto + Bridge + finance | **Bridge 시스템만** |

### 비교 매트릭스 — 축소 (예산 내 우선)
Vector only / Graph only / **Hybrid Agent** / SQL+Vector — **4 어댑터 × 저비용 LLM 1종 (FAST tier — Sonnet 4.6 / GPT-4o-mini / Gemini Flash) = 4 조합** 으로 thesis(§10.7 Hybrid > Vector) headline 확보. 2번째 LLM 은 subset (CD-L3/L4) 만. **rerank on/off ablation 1행 (BGE-Reranker-v2-m3 wired 활용).** Cross-Domain 은 Hybrid+Bridge 어댑터 단독.

### 목표 지표

| 지표 | 목표 | 측정 도구 |
|---|---|---|
| **Retrieval — hits@k** (gold entity 가 top-k 안에 있는지) | hits@5 ≥ 0.80 | `eval/metrics/hits_at_k.py:hits_at_k(pred, gold, k=5)` (정규화 후 정확 일치 → 부분문자열 ≥3글자 → SequenceMatcher ≥0.85) |
| **Retrieval — recall@k** (gold 중 top-k 안 비율) | recall@5 ≥ 0.70 | `eval/metrics/hits_at_k.py:recall_at_k` |
| **Multi-hop subset** (hop_count ≥ 2 문항) | hits@k ≥ +0.30p (vs Vector) | runner `--multi-hop-only` 또는 gold 의 `hop_count` 필터 |
| Answer Accuracy (LLM-as-judge) | 85%+ | `eval/metrics/llm_judge.py` |
| 재무·제원 Exact Match | 95%+ | `eval/metrics/em_f1.py` |
| Faithfulness (Ragas) | 90%+ | `eval/metrics/faithfulness.py` |
| 평균 latency 도메인내 / Cross | < 8초 / < 12초 | `eval/metrics/latency.py` |
| Bridge confidence ≥ 0.9 비율 | 80%+ | `eval/metrics/bridge_quality.py` |
| Main-Hop Efficiency (vector 대비 hop 절감) | −30%+ | `eval/metrics/main_hop_efficiency.py` |
| Confidence-Weighted Accuracy (calibration) | (관찰 지표) | `eval/metrics/confidence_weighted.py` |
| Hybrid vs Vector-only Multi-hop 격차 | +30%p | runner 의 `hybrid_vs_vector` (자동) |

### DoD 자동 검증

```bash
make audit-bom-coverage   # §10 DoD #5
make audit-edge-meta      # §10 DoD #11
make validate-gold-qa     # qa_gold/*.jsonl lint
make eval-full            # finance 100문항
make eval-auto            # auto 100문항
make eval-cross           # CD-L1~L4 30문항
make audit-dod            # 17항 (v2.2) 트래픽라이트 종합 리포트 → eval/reports/dod_v2.2.md
```

### 현재 측정 결과 (§10 DoD **20 항** v3.0, 2026-05-29 측정 + 2026-06-02 ProcessGraph 추가)

`make audit-dod` 의 출력 (2026-06-02 baseline `831e72d` reset 후) — §10.12 코어 변경 **0% ✅**. LLM 키 필요한 §10.7/§10.13 등은 simulation manifest 기준 미측정 (키 후 재측정). 20 항목 = 기존 14 + v2.2 신설 §10.15~§10.17 + v3.0 신설 §10.18~§10.20 (ProcessGraph BoP). 정확한 트래픽라이트는 `make audit-dod` 실행 결과 참조.

| ID | 기준 | 상태 | 상세 |
|---|---|:---:|---|
| §10.4 | MVP 범위 OEM 5~8 × 모델 30~50 × 2022~2024 | ✅ | OEM=5 / models=102 / years=(2020, 2024) — 범위 over-spec |
| §10.5 | BOM L0~L3 안정 + L4 coverage ≥ 60% | ✅ | L0~L3 stable, L4=63.7% |
| §10.6 | bridge.corp_entity QID/LEI 강매칭 confidence ≥0.9 비율 80%+ | ✅ | strong_match **15/15 = 100%** (manufacturer reviewed 11 + supplier reviewed 4, 모두 conf≥0.9) — 2026-06-01 재측정 |
| §10.11 | SUPPLIED_BY 엣지 confidence/provenance/snapshot_year 100% | ✅ | **30 edges** 모두 `source_type='manual_supplier_seed'` + 100% meta (yaml 46 매핑 vs Neo4j 30 = customer 다중 dedupe 정상) |
| §10.12 | 코어 코드 변경 < 5% | ✅ | **baseline reset 3회**: `4049caf` (Phase B) → `bab9411` (도메인3 직전, 12.22%) → `414bc1b` (ipgraph 인프라, +1,877 LOC=13.32%) → **`831e72d`** (상용화 P0/P1 일괄: O-1/Q-1/Q-4/E-3, **inflection +1,583 LOC=10.28% → reset 후 0% from 831e72d**). 정직 표기 — inflection·reset 두 숫자 같이 인용: [`eval/reports/core_diff_baseline_ledger.md`](./eval/reports/core_diff_baseline_ledger.md#정직-review--코어-변경--5-가-정말-의미-있는가-p1-5) |
| §10.7 | Hybrid vs Vector Multi-hop +30%p | ⊘ | LLM 키 필요 — `make eval-auto` 실행 후 자동 측정 |
| §10.8 | Cross-Domain QA CD-L1~L4 | ⊘ | LLM 키 필요 |
| §10.9 | 제원 수치 EM 95%+ | ⊘ | LLM 키 필요 |
| §10.10 | Faithfulness 90%+ | ⊘ | LLM 키 필요 |
| §10.13 | 메인 홉 효율 −30% | ⊘ | 운영 trace 필요 — `eval/runners` 에서 latency·hop 수집 |
| §10.14 | latency 도메인내 <8s / Cross <12s | ⊘ | 운영 trace 필요 |
| §10.1~3 | docker compose / Streamlit toggle / LLM provider 전환 | · | 외부 측정 (docker / git / ENV) |
| **§10.15** | **ip 도메인 추가 후 코어 변경 < 5% 재측정 (baseline reset)** | (wired) | `src/ipgraph/` 신규 패키지 + plug-in 자동 등록 (`ENV AUTONEXUSGRAPH_DOMAIN_PLUGINS=autograph,ipgraph`). `make audit-ipgraph` 가 handler/router/ontology/cypher templates(25)/gold(ip=30+cross_ip=8) 5종 wire-up 검증 → DoD dashboard 자동 반영. **core diff ratio** 측정은 baseline reset 후속 — `make audit-dod` 재실행 |
| **§10.16** | **ip gold seed (IP-L1 80%+ / L2 70%+ / L3 50%+) + CD-L3/L4 ip 결합 8 문항** | (wired) | `gold_qa_ip_v0.jsonl` 30 row (L1 10 / L2 10 / L3 10) + `gold_qa_cross_v0.jsonl` IP cross 8 row (CD-L3 4 + CD-L4 4). 삼성SDI 배터리 H01M ↔ 영업이익 ↔ OEM 리콜 CD-L4 시연 row 포함. **목표 정확도 (80/70/50/40%)** 달성은 USPTO ODP/KIPRIS 적재 후 측정 — wire-up 완료 |
| **§10.17 (a)** | **MCP 래퍼** | (wired) | `src/autonexusgraph/mcp/` — typed tool pool (59 tools: finance 21 + auto 38) 위 얇은 MCP server. `inspect.signature` + type hint → JSON Schema 자동 변환 (사용자 schema 작성 불요). stdio transport (`python -m autonexusgraph.mcp`). `make audit-mcp` 가 SDK 미설치 시 SKIPPED + tool discovery 검증, 설치 시 server boot + `ListToolsRequest` 핸들러 in-process round-trip 으로 59 tools 응답 실측 (2026-06-04 PASS, SDK 설치). **SDK 설치 = `pip install -e ".[mcp]"`** (이제 `[all]` extras 에도 포함) |
| **§10.17 (b)** | **Langfuse 실측 ON (turn별 token/cost/replan)** | (wired) | Langfuse 4.x OTEL + ContextVar 격리 + `meta JSONB` 적재. `make audit-trace` 로 실측 검증 — `data/reports/audit_trace_*.json` 의 최신 리포트가 dashboard 에 자동 반영 |
| **§10.17 (c)** | **온톨로지 SHACL·pydantic 검증** | (wired) | pydantic v2 strict-validate (`src/autonexusgraph/ontology/schema.py`). `extra='forbid'` 미지정 키 reject + cardinality/class/provenance/pass enum 정합 + relation.from/to ↔ entities cross-check + edge_required_meta 7키 SoT 강제. `schema_version` yaml 헤더. `make audit-ontology` = 핵심 6 yaml(auto/ip/finance) + **보조 4 yaml(Y-1: extractors×2/system_taxonomy/plants, extra='forbid')** + cypher↔yaml cross-check → DoD dashboard 자동 반영 |
| **§10.17 (d)** | **축소 평가 매트릭스 (4 어댑터 × FAST tier 1종 + rerank ablation)** | (wired, partial) | `AgentAdapter(rerank, llm_tier)` 1급 매트릭스 변수 + `<name>_<tier>_rerank<0\|1>` cell 라벨. `eval/runners/run_matrix_smoke.py` 가 8 cells enumerate + thesis headline (Hybrid−Vector multi-hop EM vs +30%p) 자동 계산. `make audit-eval-matrix` simulation 모드 (LLM 비용 0) 기본 / `--full` 실 LLM. Allganize 외부 벤치 stub (`eval/qa_gold/gold_qa_allganize_v0.jsonl`). **full LLM 측정은 사용자 환경에서 별도 트리거** |

→ **남은 측정의 부족분은 §12 보완 개발 백로그 참조. 정량 게이트 본문 SSOT 는 §10 DoD 20항.**

---

## 7. 구현 상태

> §10 의 DoD **20 항** SSOT (v3.0 — 기존 14 + ip/상용 신호 3 + ProcessGraph 3) 는 `make audit-dod` 의 출력 (`eval/reports/`). 본 표는 코드·테스트에 직접 대응하는 사실만 담는다. "곧" 같은 표현은 쓰지 않는다. **(예정)** 라벨은 본 README 표기 컨벤션 (§0).

### 구현된 sub-system

| 영역 | 핵심 산출물 |
|---|---|
| 인프라 | Docker Compose, Neo4j 5.18, PostgreSQL 16 (pgvector 내장), BGE-M3 1024d 자체 임베딩 |
| LLM 어댑터 | OpenAI / Anthropic / Google / local OpenAI-compatible 자동 dispatch (`llm/base.py::detect_provider`), FAST/SMART tier 단축 + 11 role override |
| 비용 가드 | 세션 hard limit (`LLM_SESSION_HARD_LIMIT_USD`) + 도메인별 turn budget (`config.turn_budget_for_domain`, ENV override) + 사전 추정 + auto-approve + JSONL 영속 로그 (`data/cost_log.jsonl`) |
| 데이터 파이프라인 (finance) | DART corp 마스터, XBRL 184K, filings 4.6K, vec.chunks 748K, Neo4j Company/Person/지배구조 — Wikidata/Wikipedia/GLEIF/SEC/뉴스/KCGS 보강, ER 마스터 (`master.entities` + `master.entity_map`) |
| 데이터 파이프라인 (auto) | NHTSA vPIC/Recalls/Complaints/SafetyRatings/Investigations/TSB, EPA fueleconomy, SEC EDGAR (글로벌 OEM XBRL), Wikidata mfr/model/supplier/P176, AI Hub, KOTSA 수리검사, NHTSA component taxonomy 자동 도출. `bridge.corp_entity` 4,806 (한국 OEM/부품사 corp_code + 글로벌 OEM sec_cik 9개) |
| 제조 / 공정 (auto) | DART 사업보고서 본문 파서 (LLM 0%) — 생산능력·가동률·공장명 자동 추출. 산단공 합성 공정데이터 → `:Process` 사전. 팩토리온 공장등록 (15087611) 부분 적재 90행 (OEM 5사 + tier-1, `DATA_GO_KR_API_KEY` 작동) |
| 도구 (tools) | finance: `tools/financials,graph,retrieve.py` — 사전 정의 함수 풀. auto: `src/autograph/tools/{spec,graph,retrieve,bridge}.py`. 자유 SQL/Cypher 금지 |
| Cypher 템플릿 | finance 22 = 14 정적 + 5 `find_paths_{1..5}hops` + 3 `get_subgraph_d{1..3}` (`tools/cypher_templates.py`). auto **24** (`src/autograph/cypher_templates_auto.py` — 기존 19 + `auto_plants_of_manufacturer` / `auto_plants_of_model` / `auto_investigations_by_model` / `auto_investigations_by_variant` / `auto_investigation_recall_chain` 5건 추가). ip 25 (`src/ipgraph/cypher_templates_ip.py`). type/range/regex 검증 + bool reject |
| 멀티에이전트 (LangGraph) | StateGraph 11 노드 (triage/planner/supervisor/4 worker/executor_legacy/synthesizer/validator/finalize) + 함수 체인 fallback. `agents/graph.py` |
| Planner DAG | `make_task(depends_on=…)`, `dag.unblocked_tasks`, `dag.topologically_valid` (`agents/dag.py`) |
| Supervisor + Send API | 순차 모드 + 병렬 모드 (LangGraph `Send`). turn budget circuit breaker |
| Worker | research / graph / sql / calculator (numexpr sandbox) — 2단계 화이트리스트 (`_allowed_intents` + `_resolve_tool`) |
| Synthesizer | budget-aware LLM client, XML escape, number guard 적용 |
| Validator + Replan | 6 검사 (length, self-report bypass, language, grounding, hallucinated_numbers, edge_confidence), MAX_REPLANS=2 |
| HITL — clarification | 회사명 모호성 자동 감지 (margin<10%, `is_ambiguous_company`), LangGraph interrupt → `/chat/resume`, Streamlit dialog |
| HITL — cost approval | `LLM_COST_AUTO_APPROVE_USD` (기본 $0.50) 초과 시 user 승인. 거절 시 worker skip + 명시 답변. 폴백환경 자동 통과 + 경고 |
| Safety guards | prompt_safety (high-risk 단발 차단 + low-risk telemetry, SSOT 단일 rule), cypher_guard (READ-ONLY + APOC write/dynamic-cypher procedure 블록 — `assert_read_only` / `assert_templates_params_match`), number_guard (pre-synth 마스킹 + post-synth validator SSOT 공유), language_guard (한국어 비율 30%) |
| 도메인 라우팅 | `_domain_handler` Protocol + ENV `AUTONEXUSGRAPH_DOMAIN_PLUGINS` (기본 `autograph`) soft-import + `auto_detect_domain` 룰 기반 |
| Checkpointer | LangGraph PG checkpointer (`chat` 스키마 search_path 주입) + memory fallback |
| Streaming | `run_agent_stream` + FastAPI `/chat/stream` SSE + Streamlit `st.status` node progress |
| Tracing | Langfuse / LangSmith fail-soft |
| P3/P4 추출 (auto) | `autograph.extractors.run_p3` (SUPPLIED_BY/RECALL_OF 활성) + `cross_validate`. `auto.staging_relations.p4_decision` ∈ candidate / validated / needs_review / rejected. `make extract-validate-auto` |
| 평가 메트릭 | bridge_quality / main_hop_efficiency / confidence_weighted / latency (`eval/metrics/`) + `scripts/audit/{bom_coverage,edge_meta_invariants,dod_audit,validate_gold_qa}.py` |
| gold QA seed | `gold_qa_v0.jsonl` finance **30** / `gold_qa_auto_v0.jsonl` auto **46** / `gold_qa_cross_v0.jsonl` CD **44** (level: CD-L1=10 / L2=8 / L3=12 / L4=8 + 6 row IP 결합 변형) / `gold_qa_ip_v0.jsonl` ip **30** (IP-L1/L2/L3 각 10) |
| 외부 데이터 인터페이스 | data.go.kr (3048950 리콜 CSV / 15155857 검사), car.go.kr, KATRI (bigdata-tic), KNCAP 5 소스 ingestion + loader (graceful skip — 인증 키 부재 시 skip) |

### 미구현 / wired-but-disabled / 측정 대기

| 영역 | 상태 | 비고 |
|---|---|---|
| HITL `sensitive_decision` | wired + 활성 (trigger=키워드 휴리스틱 / fallback=거절) | `agents/interrupts.py`: `SENSITIVE_KEYWORDS` (투자 자문 / 매매 신호 / 추천 종목 / 예상 수익 / 수익률 전망 / 법적 조언 / 법적 권고 / 법률 자문 / 주가 예측 / 가격 예측 — §9 영구 비목표 인접 10종) + `detect_sensitive_keyword(answer, question)` 휴리스틱. `agents/nodes.py::synthesizer_node` 끝에서 grounding 검증 직후 호출 — 매칭 시 `request_interrupt` 발동, 폴백 환경(`InterruptUnavailable`)은 보수적 거절 + `state["sensitive_blocked"]=True` + 답변 차단 메시지 교체. **LLM 실패 fallback 답변 skip 정책 (N2, 2026-06-02)**: `state["synth_status"].fallback_used` 가 set (BudgetExceeded / Exception 분기) 인 경우 sensitive gate 무조건 통과 — `build_deterministic_brief` 결과는 LLM 미생성 안전 정보만이라 차단 부작용 회피. safety_signals 키: `sensitive_blocked:<hit>` / `sensitive_blocked_fallback:<hit>` |
| P3 selective LLM relations | wired-but-disabled = 1종 (COMPETES_WITH) | 실측 (`ontology/auto/relations.yaml:226-235`): COMPETES_WITH `pass: P3, enabled: false`. MANUFACTURED_AT 은 `pass: P2, enabled: true` (deterministic plants_seed). CONTAINS_MODULE / CONTAINS_PART 는 yaml 에 미정의 (현재 CONTAINS_COMPONENT 1종 P2 enabled 가 그 역할). LLM 확장(MANUFACTURED_AT LLM / Part 매핑) 은 비용·환각 위험으로 후속 PR 대기 — manual seed + Wikidata P176 우선 |
| 12 조합 매트릭스 실측 (4 어댑터 × 3 LLM) | 측정 대기 | `make eval-full / eval-auto / eval-cross` 실행 + gold seed 100/100/30 확장 후 |
| 공정위 기업집단 / KOSIS / KIPRIS / LAW.go.kr | 키 확보 대기 | Makefile 타겟·loader 는 있음 (`README §4`) |
| vec.chunks embedding backfill | 진행 중 (진행률 가시화 ✅ Q-4) | finance 748K 중 일부, auto 16,435 모두 완료. `make embed-status` 로 source별 진행률 조회 |
| bridge.corp_entity 부품사 corp_code 매핑 | 확장 대기 | 현재 한국 OEM/부품사 직접 매핑 소수 / 글로벌 OEM sec_cik 9개. supplier 4,792 candidate 검토 routine 미수행 |
| Cross-Domain QA 100문항 + 라벨 4단계 | **44 row** seed 적재 (2026-06-02 재측정) | CD-L1 10 / L2 8 / L3 13 / L4 10 + difficulty 미부여 3 (IP-결합 8 row 포함 — CD-L3-IP 4 + CD-L4-IP 4). 100문항까지 사람 라벨링 + 확장 대기 |
| confidence_score calibration | 미수행 | A/B/C 스칼라가 실제 정답률과 단조 관계인지 사후 검증 (`eval/metrics/confidence_weighted.py` 가 측정 도구) |
| Bridge candidate 검토 운영 | ✅ **도구 구현** (Q-1) — `bridge_review.py` + Streamlit `ui/bridge_review.py` (✓/✗) + 6개월 자동 만료 + 진행률 KPI + `26_bridge_review.sql` 감사 컬럼 + `make bridge-kpi`/`bridge-expire` ([SOP](./docs/operations/bridge_review.md)) | 4,792 supplier candidate 실제 라벨링은 사람 작업 (도구·cron 준비됨) |
| KNCAP / Euro NCAP / IIHS | 인터페이스만 (KNCAP) / 미구현 | 공식 채널 약관 검토 후 |
| KATRI / bigdata-tic OAuth | wired | `BIGDATA_TIC_CLIENT_ID/SECRET` 발급 후 활성 |
| 팩토리온 (15087611) | 부분 적재 (90행) | ingestion 3 endpoint 구현 + `DATA_GO_KR_API_KEY` 작동 → `auto.factoryon_registry` 90행 (OEM 5사 + tier-1). ProcessStep↔Plant 매핑 잔여 |
| 산단공 공정 (15151075) | wired | 수동 CSV 다운 후 `make load-sandang-processes` |
| `_legacy/v2/` | 보존 | 삭제 예정 미정 (`docs/mental_model.md §5.10`) |
| Integration test (`pytest -m integration`) | 마커 0건 | unit test 파일 수: root 48 + autograph 17 = 65. 실제 Neo4j/PG 통합은 `docs/autograph.md §7.5` 수동 절차. **CI(O-4)는 keyless smoke-e2e 만 — ephemeral PG/Neo4j 통합 잡은 secrets/self-hosted 후속** |
| API 인증 / Rate limit | ✅ **구현** (`api/auth.py`) | API key 헤더 인증 (`X-API-Key`/`Bearer` + `API_KEYS` env) + thread_id↔user_id 바인딩 (타인 히스토리 403) + per-identity in-memory rate limit (`API_RATE_LIMIT_PER_MIN`). `/health` 제외. `API_KEYS` 미설정 시 open 모드 (dev). 잔여: OAuth2/OIDC·multi-instance 분산 — §12.2 |
| Production 배포 가이드 | ✅ **작성** ([docs/operations/production_deploy.md](./docs/operations/production_deploy.md)) + `infra/Dockerfile` + `docker-compose.prod.yml` | 이미지 빌드 / compose prod / health probe / reverse proxy·TLS / k8s / blue-green·canary / 멀티 인스턴스. 백업·DR(O-3 ✅) / 모니터링(O-5 ✅) 별도 구현 완료 — §12.3 |
| `docs/design/` | ✅ ADR 4건 (F-3) | LangGraph StateGraph / DomainHandler plug-in / Bridge 분리 / P1~P4 추출 — context·decision·consequences, 코드 라인 위임 |
| `_legacy/` | 보존 (v1/v2 KGQA Agent) | 이전 단일도메인 시스템. CHANGELOG/HISTORY 보존. 삭제 vs 마이그레이션 정책 미정 |
| 모델 출력 reranker (BGE-Reranker-v2-m3) | 코드 wired (`RERANKER_URL=...`) | 실서비스에서 미활성. 활성 조건·임계 미정의 |
| USES_PROCESS / MADE_OF (L6) | wired (ontology 정의) | `:Process` 노드 사전 산단공 적재 / `:Material` 노드 미구현. 엣지 적재 routine 미구현 |
| DART 사업보고서 가동률 표 | 구현 완료 (2026-06-01) | `src/autograph/extractors/dart_production_parser.py::_parse_utilization_table` + `_parse_pct` 가 표 컬럼 정규화 + 가동률(util_pct) 추출. `auto.plant_utilization` 53 row 적재 완료 (§1 — Hyundai HMC 116.6% / 베트남 HTMV 54.1% 등 explicit util_pct, B 등급 0.80) |
| **IPGraph 도메인 어댑터** | **코드 구현 완료 (working tree, uncommitted)** — 도메인3 | `src/ipgraph/{agent_handler,policy,ontology,cypher_templates_ip}.py + tools/* + loaders/* + ingestion/*` + `ontology/ip/*` (audit-ontology 4/4 PASS) + tool pool 4종 + cypher `ip_*` 25 templates + gold seed 30 + cross_ip 8. `make audit-ipgraph` PASS. core 변경 0 LOC = 0.00% (§10.12). 상세 SSOT [docs/ipgraph.md](./docs/ipgraph.md) |
| **`ip.assignee_corp_map`** | **(scaffold)** — 테이블·loader 있음, mapping 데이터 0 | `19_ipgraph_bridge.sql` **적용 완료 (2026-06-01)** + `loaders/load_assignee_corp_map.py` — assignee 적재 + auto/reviewed 매핑 SOP 대기. `bridge.corp_entity` 직접 변경 회피, supplier candidate 운영 SOP 재사용 |
| **KIPRIS / USPTO ODP (PatentsView 후속) / CPC bulk / OpenAlex** | **CPC bulk 10,695 + OpenAlex works 629 ✅ / KIPRIS·USPTO ODP (scaffold, 보조)** | `loaders/load_cpc.py` + `loaders/load_openalex.py` 적재 완료. PatentsView 는 **2026-03-20 USPTO Open Data Portal (data.uspto.gov) 로 이관 완료** — REST API 종료, **bulk dataset 채택**. `ingestion/{kipris,uspto_odp}.py` 구현됨, 키 발급 + bulk 적재 대기 |
| **배터리·소재 (auto L5/L6)** | **(부분 적재)** — Material 6 (materials_seed cathode chem) / Mineral 5 (`auto.master_minerals`) + DERIVED_FROM·MADE_OF 엣지 적재, L6 본격 진입 전 | Wikidata cell chem + USGS minerals + 무역통계. 회사단위 셀 ↔ OEM 소싱은 grade C candidate 정직 표기 |
| **MCP 래퍼** | **(wired)** — `src/autonexusgraph/mcp/`. typed tool pool (59 tools: finance 21 + auto 38) + 자동 JSON Schema 변환 + stdio server + `ListToolsRequest` 핸들러 round-trip 실측 PASS (2026-06-02). `make audit-mcp` SDK 미설치 fail-soft | typed tool pool 위에 얇은 MCP server. 2026 상호운용 표준 신호 (Claude/OpenAI Agents SDK 양쪽 MCP 채택). `pip install -e ".[mcp]"` (이제 `[all]` extras 에도 포함) 후 `python -m autonexusgraph.mcp` |
| **Langfuse 실측 ON** | **(wired)** — DoD #17 (b) | Langfuse 4.x OTEL native + ContextVar 격리. `make audit-trace` (LLM 비용 0 simulation 또는 `--full` 실 agent run) 가 `data/reports/audit_trace_*.json` 생성 → `make audit-dod` 자동 반영. `TRACE_BACKEND=langfuse` + `LANGFUSE_*` 키 필요 |
| **온톨로지 pydantic strict 검증** | **PASS yaml 6/6 · cross-check PASS** (audit-ontology 2026-06-01) | `scripts/audit/ontology_validate.py` (Pydantic strict, `extra='forbid'`) — `ontology/{auto,ip}/{entities,relations}.yaml + ontology/{entities,relations}.yaml` 6 yaml 모두 통과. **cypher↔yaml cross-check** (default on): `cypher_templates_<domain>.py` 의 엣지 타입이 `relations.yaml` 에 정의되어 있는지 검증, cross-domain reference (예: ip cypher 가 auto.SUPPLIED_BY 참조) 는 기본 WARN(⚠️ 가시화), **Y-2: `make audit-ontology ARGS="--strict-cross"` 로 ERROR 강등 선택 가능**. 보완 완료: `LED_TO_RECALL` (auto/relations.yaml:162), `MAPPED_TO` (ip/relations.yaml:88) — 둘 다 yaml 에 정의됨 (audit-ontology 실측 PASS) |
| **License invariant test** | **PASS — 15/15** (`tests/test_license.py`) | `_license.py` 정책 dict 와 도메인별 실제 사용 source 키 (finance/auto/ip/wiki) 의 동기화를 invariant 로 강제. 신규 ingester 추가 시 LICENSE_POLICY 미등록이면 test fail. `_common.save_raw` 가 미등록 source 첫 사용 시 WARN 로깅 |
| **DoD #13/#14 자동 wiring** | **(wired)** — `run_matrix_smoke.py` | manifest.json 의 `main_hop_efficiency` (DoD #13) + `latency` (DoD #14) 를 `compute_dod_13_14()` 가 hybrid_rerank1 vs vector_rerank0 비교로 산출. `prd_dashboard._collect_{hop,latency}_audit()` 가 흡수 → `make audit-dod` 자동 반영. `--full` 모드에서 LLM 호출 시 실측 |
| **smoke-e2e pre-push 게이트** | **(wired)** — `make smoke-e2e` | DB·LLM 없이 돌아가는 mock 정합성 일괄 검증: `pytest` + `audit-ontology` (cypher cross-check 포함) + `audit-eval-matrix` (simulation) + `audit-mcp` + `audit-ipgraph` + `audit-trace` (simulation) + `validate_gold_qa --no-db` |

---

## 8. 기술 스택

| 영역 | 선택 | 사유 |
|---|---|---|
| 그래프 DB | Neo4j 5.18 | Cypher 표준, APOC |
| 벡터 DB | pgvector (PostgreSQL) | 운영 단순, 100만 청크 이하 충분 |
| 정형 DB | PostgreSQL 16 | JSONB, 시계열, ON CONFLICT UPSERT |
| 임베딩 | BGE-M3 (1024d, cosine) | 한국어 성능 + 멀티벡터 |
| 에이전트 | LangGraph (선택적; 미설치 시 함수 체인 fallback) | StateGraph + Send 병렬 + interrupt + PG checkpointer |
| LLM 추상화 | 자체 어댑터 — OpenAI / Anthropic / Google / local OpenAI-compatible | 모델 prefix 자동 dispatch (`llm/base.py`) + PRICING SSOT (`llm/cost.py`) |
| UI | Streamlit | 빠른 프로토타이핑 |

---

## 9. 비목표 (Non-Goals)

### 영구 non-goal — 본 시스템이 다루지 않는다고 단정한 것

- 실시간 주가 예측 / 매매 신호 생성
- 투자 자문 (정보 제공 한정)
- 비공개 OEM 내부 BOM / 비공개 부품번호
- 비공개 텔레매틱스 / 차량 OTA 데이터
- 차량 가격 예측 / 중고차 시세
- 자율주행 안전성 인증 대체 / 정비 매뉴얼 기반 DIY 가이드

### MVP 비목표이지만 §10 장기 로드맵에서 다루는 것

- 비상장사 / 사모펀드 / 글로벌 영문 기업 → §11.1 Bridge 확장
- BOM Level 5 (Part) 대량 / Level 6 (Material·Process) → §11.2 (배터리·소재 부분 진입)
- **공정·라인·설비·원가·생산량** — DATA_GO_KR_API_KEY (팩토리온 / 리콜 / 검사) + DART 가동률 표 (완료) + KOSIS 산업 통계로 보강 진행 중 → §10.18~20
- 실시간 이벤트 처리 (분 단위) → §11.4
- ESG ↔ 제품 친환경성 결합 / 공급망 위험 분석 / 리콜 전파 분석 → §11.3

### 현 단계 비목표 (도메인 확장)

- **4번째 도메인 — 의약품 (`pharmagraph`) / 전자제품 (`elecgraph`) / 에너지 (`energygraph`) / 식품 (`foodgraph`)** — 본 단계 (현 PR) 에서는 다루지 않는다. 도메인3 (ip = 특허) 이 §10.12 "코어 변경 < 5%" 를 실측으로 증명한 뒤 Phase D/E 진입 여부를 **재의사결정** (§11.1 Phase D/E 비전 박스). 즉 "영구" 비목표가 아니라 "ip 증명 전까지" 보류.
- **도메인3 (ip = 특허)** 는 비목표 아님 — Phase C (현 단계) 로 정식 흡수됨 (§11.1 N-domain umbrella + §10.15~§10.17). 코드/온톨로지/스키마 완료, 데이터 적재 (KIPRIS / USPTO ODP) 만 사용자 액션 대기.

---

## 10. DoD (Definition of Done) — 20 항

> **§6 현재 측정 결과 표는 진행 추적용 요약.** 본 §10 은 측정 기준·코드 SSOT 의 정량 게이트 본문 — 기존 14 항 (v2.1) + IPGraph 흡수 3 항 (v2.2 #15~#17) + ProcessGraph BoP 격상 3 항 (v3.0 #18~#20) = **총 20 항**. `make audit-dod` → `eval/reports/dod_v3.0.md` 트래픽라이트.
>
> **상태 아이콘 범례:** **✅** = DoD 통과 / **(wired)** = 코드·인프라 연결 완료, 측정값 갱신만 대기 / **(wired, partial)** = 일부 의존성 (SDK 설치·키·LLM) 대기 / **⊘** = LLM 키 또는 외부 자원 필요 / **⚠️** = 부분 충족 또는 목표 미달 / **❌** = 명백한 미달 / **·** = 외부 측정 (docker / git / ENV).
>
> **§10.5 "BOM L4 coverage" 정의** (모호성 해소): L4 coverage = L4 module 데이터 보유 vehicle_model 수 / 전체 vehicle_model 수. 측정 도구 `scripts/audit/bom_coverage.py`. 2026-06-01 측정 L4 = **63.7%** (60% 목표 over).

### 10.1~10.14 기존 14 항 (v2.1 base)

1. ✅ **인프라 공유** — `docker compose up` 그대로 auto 까지 기동
2. ✅ **Streamlit UI 도메인 토글 3종** + v2.2 4번째 ip 추가 (auto / finance / cross_domain / ip)
3. ✅ **LLM Provider 환경변수 전환** — `LLM_PROVIDER` 한 줄
4. ✅ **MVP 범위** OEM 5~8 × 모델 30~50 × 2022~2024 데이터 3저장소 적재 — 실측 OEM=5 / models=102 / years=(2020, 2024) over-spec
5. ✅ **BOM Level 0~3 안정, Level 4 coverage ≥ 60%** — L0~L3 stable, L4=63.7%. Level 5~6 은 v2.2 부분 진입 — 배터리·소재 §11.2
6. ✅ **`bridge.corp_entity` 자동 생성** — Wikidata QID + LEI 매칭 confidence ≥ 0.9 비율 80%+ — strong_match **15/15 = 100%** (manufacturer reviewed 11 + supplier reviewed 4) 2026-06-01 재측정
7. ⊘ **Hybrid vs Vector Multi-hop +30%p** — LLM 키 필요. `make eval-auto` 실행 후 자동 측정
8. ⊘ **Cross-Domain QA 4단계 층화** (CD-L1 80%+ / L2 70%+ / L3 50%+ / L4 40%+)
9. ⊘ **제원·재무 수치 Exact Match 95%+**
10. ⊘ **Faithfulness (Ragas) 90%+**
11. ✅ **`SUPPLIED_BY` 엣지 confidence + provenance + snapshot_year 100%** — **30 edges** 모두 `source_type='manual_supplier_seed'` + 100% meta (yaml 19 공급사 × 46 mapping → Neo4j 30 dedupe, customer 다중은 `:CONTAINS_COMPONENT` 별도 엣지). `edge_meta_invariants` 8 invariant 모두 PASS
12. ✅ **코어 코드 변경 < 5%** — **baseline reset 3회**: `4049caf` (Phase B) → `bab9411` (도메인3 직전, 12.22%) → `414bc1b` (ipgraph 인프라, +1,877 LOC=13.32%) → `831e72d` (상용화 P0/P1 일괄 O-1/Q-1/Q-4/E-3, **inflection +1,583 LOC=10.28% → reset 후 0% from 831e72d**). **정직 표기 — inflection·reset 두 숫자 같이 인용**: [eval/reports/core_diff_baseline_ledger.md](./eval/reports/core_diff_baseline_ledger.md#정직-review--코어-변경--5-가-정말-의미-있는가-p1-5)
13. ⊘ **메인 홉 효율 −30%** — 운영 trace 필요. `eval/runners` 에서 latency·hop 수집
14. ⊘ **평균 latency 도메인내 <8초 / Cross <12초** — 운영 trace 필요

### 10.15~10.17 IPGraph 도메인3 정식 흡수 (v2.2 신설)

15. **(wired)** **IPGraph 도메인 추가 후 코어 변경 < 5% 재측정 (baseline reset)** — `src/ipgraph/{__init__,agent_handler,policy,ontology,cypher_templates_ip,tools/*}.py` 신규 패키지 + plug-in 자동 등록 (`ENV AUTONEXUSGRAPH_DOMAIN_PLUGINS=autograph,ipgraph`). `make audit-ipgraph` 가 handler/router/ontology/cypher templates(25)/gold(ip=30+cross_ip=8) 5종 wire-up 검증. PG init 18/19_ipgraph(.sql) + ontology/ip/*.yaml v2.2 schema_version. **core diff ratio** 측정은 baseline reset 후속. **정직 표기**: `0.00%` 단독 자랑이 아니라 통합 inflection (`bab9411 → 414bc1b = +1,877 LOC`) 과 같이 인용해야 정직 — [ledger §B-D](./eval/reports/core_diff_baseline_ledger.md#정직-review--코어-변경--5-가-정말-의미-있는가-p1-5). → ip 추가가 N-domain 확장성의 정량 증거.
16. **(wired)** **IPGraph gold seed + Cross-Domain ip 결합 측정** — `gold_qa_ip_v0.jsonl` 30 row (L1 10 / L2 10 / L3 10) + `gold_qa_cross_v0.jsonl` **44 row** (CD-L1 10 / L2 8 / L3 13 / L4 10 + difficulty 미부여 3 — **IP 결합 8 문항 (CD-L3 4 + CD-L4 4)** 포함). 삼성SDI 배터리 특허 H01M ↔ 영업이익 ↔ OEM 리콜 CD-L4 시연 row 포함. 목표 정확도 (IP-L1 80%+ / L2 70%+ / L3 50%+) 달성은 USPTO ODP/KIPRIS 적재 후 측정. `make validate-gold-qa` 0 errors (2026-06-02).
17. **상용 신호 (Service-Grade Signals) 4 항:**
    - **(a) (wired)** **MCP 래퍼** — `src/autonexusgraph/mcp/` 신규. typed tool pool (59 tools: finance 21 + auto 38) 자동 discovery + type hint → JSON Schema 자동 변환. stdio transport. `make audit-mcp` 가 SDK 미설치 시 SKIPPED + discovery 검증, 설치 시 server boot + `ListToolsRequest` 핸들러 in-process round-trip 으로 59 tools 응답 실측 (2026-06-04 PASS, SDK 설치). `pip install -e ".[mcp]"`.
    - **(b) (wired)** **Langfuse 실측 ON (turn별 token/cost/replan dashboard)** — `make audit-trace` + DoD dashboard 자동 반영. Langfuse 4.x OTEL native, ContextVar 격리, meta JSONB 적재. SSE generator yield 마다 turn.state 동기화. turn_id/question_kind 가 metadata 에 포함.
    - **(c) (wired)** **온톨로지 SHACL/pydantic 검증 (schema_version 온톨로지 레벨)** — `make audit-ontology` + DoD dashboard 자동 반영. pydantic v2 strict (`extra='forbid'` + enum + relation cross-check + edge_required_meta 7키 SoT). 핵심 6 yaml + **보조 4 yaml (Y-1: extractors/system_taxonomy/plants)** + cypher↔yaml cross-check. `schema_version` yaml 헤더. SHACL/rdflib 회피 — LPG 모델에 conceptual mismatch.
    - **(d) (wired, partial)** **축소 평가 매트릭스 (4 어댑터 × FAST tier 1종) + Allganize 외부 벤치 + rerank on/off ablation 실측** — `AgentAdapter(rerank, llm_tier)` 1급 매트릭스 변수 + cell 식별자 자동 생성. `make audit-eval-matrix` simulation 8 cells enumerate (LLM 비용 0). **full LLM 측정 (`--full`) 은 사용자 환경 별도 트리거**.

### 10.18~10.20 ProcessGraph BoP 축 격상 (v3.0 신설)

> 설계 SSOT = **[docs/process_graph.md](./docs/process_graph.md)**. §11.2 BOM 깊이 (auto 수직 심화) 와 한 쌍.

18. ✅ **BoP 모델 안정** — `:Process` / `:ProcessStep` / `:Equipment` / `:Material` / `:Plant` **103 노드** + `PRODUCED_BY` / `PRECEDES` / `INSTANTIATES` / `USES_EQUIPMENT` / `CONSUMES_MATERIAL` / `PERFORMED_AT` / `CAUSED_BY_PROCESS` **7 엣지** 등록 (`ontology/auto/entities.yaml` + `relations.yaml` 확장, 별도 `process.yaml` 미생성 — 로더/감사 무수정 자동 동작). **현 측정**: `:Process` 410 / `:ProcessStep` 550 / `INSTANTIATES` 550 / `PRECEDES` 410 / 7 엣지 모두 ontology 등록 / `audit-ontology` PASS. **정량 게이트 충족** (≥400/≥400/≥300/7엣지/PASS).
19. ✅ **회사 귀속 공정 인스턴스** — DART 사업보고서 III. 생산·설비 (B) + 팩토리온 15087611 (A) + manual_plant_process_seed (A) → `:Plant` / `PERFORMED_AT` 생성. **모든 회사 귀속 엣지 grade A/B 100%** (`load_performed_at.py` source allowlist hard-check 로 산단공 / KAMP / AI Hub 익명·합성 출처는 PERFORMED_AT 적재 차단). **현 측정**: `PERFORMED_AT` **94** (목표 ≥ 30 ✅) — (a) manual_seed **35 validated**(B, 한국 OEM 9공장 × 4대공정+파워트레인) + (b) factoryon **59 candidate**(:Plant A등급 + 업종→공정 추론 conf 0.60). **등급 정합**: plant 는 A(공식 registry)이나 공정 추론분은 candidate — plant A등급을 추론 공정엣지에 전가 금지(PRD §8). 산단공 익명 스텝 무오염, 회사 비귀속 출처 위반 0건 ✅. :Plant 29→**103**(factoryon 74 승격), `OWNS_PLANT` 53→**60**, `MANUFACTURED_AT` 99.
20. ⚠️ **공정 cross 시연 (CD-Process)** — (a) 공정 ↔ 재무 (`Supplier → SUPPLIED_BY⁻¹ → Part → PRODUCED_BY → ProcessStep → PERFORMED_AT → Plant → operator_corp_code → finance` 4hop) (b) 공정 결함 전파 (`CAUSED_BY_PROCESS + INSTANTIATES + PRECEDES`) (c) 소재 리스크 (`CONSUMES_MATERIAL → Material → DERIVED_FROM → Mineral`) — 중 **2종 이상 Cross-Domain QA 통과**. **현 측정**: `gold_qa_auto_v0.jsonl` 공정 문항 ≥ 10 (AUTO0047+9) ✅ / `gold_qa_cross_v0.jsonl` CD-Process ≥ 5 ✅. **cross 실증**: **소재 리스크** (Module→Material→Mineral, NCM811→[Ni,Co,Mn,Li]) + **생산 vs 거시** (가동률 ↔ KAMA 거시) 2종 answerable / 공정↔재무·결함전파는 PERFORMED_AT 94 + CAUSED_BY_PROCESS 96(candidate) 적재로 **경로 구조 완성** (이전 refusal 사유 해소). 정직 정책으로 허위 엣지 0건 — 추론분은 candidate 표기. **정량 게이트 부분 충족** (AUTO ≥ 10 / CD ≥ 5 ✅, cross 정확도 ≥ 50% 는 LLM 키 후 측정).

### 핵심 정직 결론

BoP **뼈대(taxonomy + routing, grade C, #18)** 는 완성. **회사 귀속 공정 인스턴스(#19)** 는 충족 (`PERFORMED_AT` 94 = manual_seed 35 validated + factoryon 59 candidate). **LLM 품질 연결(#20 일부)** 은 LLM 키 대기 — **허위 엣지를 만들지 않고 coverage 를 그대로 표기**. 잔여 (KAMP CSV / LLM P3 정밀화) 가 풀리면 추가 적재 가능 (CAUSED_BY_PROCESS 96 candidate 적재 완료) — **DoD #20 "내부 데이터 수용 규격"** 가 코드로 보유 (`load_performed_at.py` source allowlist + `process_confidence.py` row 단위 격상 §4.0.1).

---

## 11. 최종 비전 / 장기 로드맵

본 시스템은 MVP (finance + auto, 한국 상장사 + NHTSA 5 OEM × 2020–2024) 검증이 끝나면 다음 4 축으로 확장. 각 항목은 **현재 상태 → 최종 형태 → 갭** 형태.

### 11.1 N-domain GraphRAG umbrella — 3번째·4번째 도메인 확장

> **현 단계는 Phase C 까지.** Phase D/E 는 ip 가 §10.12 < 5% 를 실측으로 증명한 뒤 의사결정 갱신. §12 동기화는 후속 PR.

| 단계 | 도메인 | 추가 데이터 소스 | Bridge 확장 |
|---|---|---|---|
| 현재 | finance (한국 상장사) + auto (자동차/제조) | DART/KRX/ECOS/NHTSA/Wikidata + DART 사업보고서·산단공·KAMA·OEM IR | `bridge.corp_entity` (corp_code ↔ entity_id, sec_cik) |
| **Phase C (현 단계)** | **+ 특허·기술혁신 (`ipgraph`)** | **KIPRIS / USPTO ODP (PatentsView 후속, 2026-03-20 이관 완료) / CPC bulk / OpenAlex — 거의 전부 정형, LLM 0%** | **`bridge.corp_entity` 재사용 + 신규 join `ip.assignee_corp_map` (M-3)**. **N-domain 확장성 정량 증명 = §10.12 < 5% 재측정** |
| Phase D (비전) | + 의약품 (`pharmagraph`) / 전자제품 (`elecgraph`) | PMDA / FDA / DRAM 로드맵 · IEC · iFixit | `bridge.corp_entity` + `bridge.drug_entity` 등 다형 |
| Phase E (비전) | + 에너지·식품 (`energygraph` / `foodgraph`) | 한국전력 발전소 / 식약처 회수 | 다양한 도메인이 동일 corp_entity 로 join |

**왜 가능한가:** core 는 `_domain_handler.discover_plugins()` 가 ENV `AUTONEXUSGRAPH_DOMAIN_PLUGINS` (CSV) 의 모듈을 import 시점에 soft-load. 새 도메인은 `register_handler` 부작용 + `ontology/<domain>/*.yaml` + 사전 정의 도구 + Cypher 템플릿 + 화이트리스트 + gold QA seed 만 추가. **§10.12 "코어 변경 < 5%" 가 강제** (`eval/metrics/core_diff.py` baseline 비교). **ip 추가 후 baseline reset 정책 (§11.1) 에 따라 재측정 → 정량 증거 산출.**

**열린 질문 / 갭:**
- 코어와 finance 어댑터의 분리 (`docs/mental_model.md §3.1.4`) — pure core / fingraph / autograph / pharmagraph 3+ 분할이 필요한지, 현재 2-pkg 가 영구 설계인지 미정
- N-domain bridge 의 매칭 우선순위 — `wikidata_qid > LEI > 사업자번호 > name` 외에 도메인별 식별자 (DUNS / CIK / ISIN / NDC / ATC …) 우선순위 sequence

### 11.2 BOM Level 5 (Part) + Level 6 (Material·Process) + ProcessGraph BoP 격상 — 깊이 확장 (주요 축)

#### Level 0~6 가용성 매트릭스 (정직 표기)

| 계층 | 가용성 | MVP 포함 | 권장 데이터 출처 | 현 적재 |
|---|---|---|---|---|
| Level 0: Manufacturer | **높음** | ✅ 필수 | Wikidata + NHTSA + KAMA | 22,145 ✅ |
| Level 1: Vehicle Model | **높음** | ✅ 필수 | NHTSA vPIC + 리콜 + Wikipedia | 6,770 ✅ |
| Level 2: Trim/Year | **중간** | ✅ 필수 | NHTSA + 국내 매핑 수동 보강 | 428 ✅ |
| Level 3: System | **중간** | ✅ 포함 | system_taxonomy.yaml 19 시스템 (KS/SAE) | wired |
| Level 4: Module | **낮음~중간** | ⚠️ 부분 포함 (coverage 63.7%) | NHTSA component taxonomy + AI Hub + manual seed | 220 ✅ |
| Level 5: Part | **낮음** | ❌ MVP 제외 | 리콜/결함 중심으로만 부분 진입 (post-MVP) | sparse |
| Level 6: Material/Process | **낮음** | ⚠️ **부분 적재 (곁가지)** | USGS minerals + Wikidata cell chem | Material 6 / Mineral 5 / DERIVED_FROM 17 / MADE_OF 8 ✅ |

**MVP 성공 기준은 Level 0~4 안정 구축**. Level 5 는 리콜에 등장한 부품만 부분 포함. Level 6 은 곁가지로 부분 진입 (USGS + Wikidata cell chem). 사용자 UI 의 BOM 트리 표시 시 "Level 4 까지 신뢰도 높음, 그 이하는 부분 데이터" 명시.

| Level | 현재 | 최종 형태 | 갭 |
|---|---|---|---|
| L0~L2 | NHTSA vPIC + Wikidata 로 100% deterministic | 글로벌 OEM 20사 × 모델 300종 × 2020~ | 한국 시장 트림은 KOTSA / data.go.kr 키 발급 후 |
| L3 (System) | `system_taxonomy.yaml` 19 시스템 SSOT | 동일 — 표준 분류이므로 확장 없음 | (해당 없음) |
| L4 (Module) | NHTSA component taxonomy 176 + AI Hub + manual seed = 220 | OEM 별 베스트셀러 모델 ≥ 90% module coverage | 부품사 IR cross-reference (현대모비스/한온/만도 …) 미수집 |
| **L5 (Part)** | post-MVP — 리콜 텍스트 LLM 추출 → RECALL_OF 자연 발생만 | OEM 별 BOM "주요 부품 30~50종" coverage, Part ↔ Supplier 시점별 매핑 | 데이터 본질 부재 (`docs/mental_model.md §5.4`) — (a) 공개 채널 자체가 sparse, (b) 부품사 IR 라이선스/정확도, (c) Part 정체성 정의 (같은 부품번호가 OEM 별로 다름) |
| **L6 (Material·Process)** | **부분 진입 (예정)** — 배터리 셀 NCM 조성 + 핵심광물 (Wikidata / USGS Mineral Commodity Summaries) — auto 의 L5/L6 확장 부록 | `(:Module {배터리팩})-[:CONTAINS_MODULE]->(:Cell)-[:MADE_OF]->(:Material {NCM811})-[:DERIVED_FROM]->(:Mineral {Ni})` BOM 하향. 알루미늄 합금 / 다이캐스팅 같은 공법 ontology + (:Module)-[:USES_PROCESS]->(:Process). 회사단위 셀 ↔ OEM 소싱은 grade C candidate — sparse. 상세 [docs/autograph.md](./docs/autograph.md) §2.5.4 | 산단공 합성 공정데이터 (15151075) 가 :Process 사전을 채우고 있음 — :Material / :Mineral 적재는 (예정) |

**현재 작업 중인 것:**
- DART 사업보고서 본문 파서 — 한국 OEM/부품사의 생산능력·가동률·공장명을 LLM 0% 정규식 + 표 파서로 추출 (가장 최근 커밋 `215f7e5`)
- 산단공 합성 공정데이터 — `:Process` 사전 적재 (Casting / Forging / Stamping / Welding / Coating …)
- 팩토리온 (15087611) 부분 적재 90행 — DATA_GO_KR_API_KEY 작동, 회사·공장번호·산단별 조회 가동. 커버리지 확대 → `MANUFACTURED_AT` 보강
- Wikidata P176 (manufactured by) — 부품↔공급사 staging 후 P4 cross-validate → Neo4j SUPPLIED_BY 승급

### 11.3 추론 가치 확장 — 공급망 위험 · 리콜 전파 · ESG 결합 · R&D ↔ 특허

본 시스템의 **궁극 가치**는 단순 Q&A 가 아니라 다음 cross-domain 추론:

1. **공급망 위험 분석** — Bridge 로 공급사 집중도 (단일 supplier 다중 OEM 사용 빈도) + AutoNexusGraph 재무·신용도 결합. 예: "삼성SDI 가 공급하는 OEM 의 매출 합계 + 삼성SDI 부채비율 + 최근 6개월 리콜 빈도".
2. **리콜 전파 분석** — 동일 부품 사용 차종 자동 영향 평가. 예: "이 BMS 리콜이 다른 OEM 의 어느 모델·연식까지 적용 가능한가". (`get_vehicles_using_component` + `find_vehicle_component_paths` + snapshot_year 시점 필터)
3. **ESG ↔ 제품 친환경성 결합** — KCGS ESG 등급 (finance) + EPA fueleconomy MPG·배출등급 (auto) + 배터리 셀 조성 (L6) → "ESG B+ 이상 OEM 의 평균 GHG score 와 EV/HEV 비율".
4. **시점 정합 cross-domain** — "2023년 LG에너지솔루션 배터리를 쓰는 OEM 의 KCGS ESG 등급" — Bridge·SUPPLIED_BY·ESG ratings 모두에 `snapshot_year` / `valid_from/to` 정합 필요.
5. **R&D ↔ 특허 ↔ 제품 (ipgraph + cross 시연 핵심)** — "현대모비스 R&D비 (finance) 대비 ADAS(CPC B60W) 특허 출원 추세 (ip)" (CD-L3) / "삼성SDI 배터리 특허(H01M) 집중 분야 + 영업이익 + 그 셀을 쓰는 OEM 리콜" (CD-L4). 호출 경로: `bridge_assignee_to_corp` → `list_patents_in_cpc` → `get_revenue / get_operating_income` → `list_recalls_affecting` — 3 도메인 동시 추론 시연.

**현재 갭:**
- 모든 엣지에 `snapshot_year` 강제는 완료. 하지만 시점 정합 cross-domain QA 의 ground truth 정의가 모호 (`docs/mental_model.md §5.8`) — 분기별 공급 비율 변동 시 어느 시점을 "정답" 으로?
- Bridge candidate 4,792 supplier 의 검토 운영 SOP 미정 — graph quality 가 시간 갈수록 떨어질 수 있음
- 리콜 전파 분석은 모델·연식 cross-product 가 쉽게 폭발 — Planner 가 "메인 홉 우선 traversal" 휴리스틱 미구현

### 11.4 운영·평가·신뢰성 — Enterprise 수준 도달

| 영역 | 현재 | 최종 |
|---|---|---|
| 평가 매트릭스 | 4 어댑터 × 3 LLM = 12 조합 인프라 완성, 실측 대기 | **축소 매트릭스 4 조합 (4 어댑터 × FAST tier 1종) 우선 headline (thesis §10.7) + Allganize 외부 벤치 + rerank on/off ablation.** 2번째 LLM 은 subset (CD-L3/L4) — 풀 12 조합 실측 + Confidence-Weighted Accuracy calibration + Vector RAG 비교 공정성 검증은 후속 |
| Gold QA | finance 30 / auto 46 / cross 44 / ip 30 row seed | finance 100 / auto 100 / cross 100 / ip 100 — CD-L1~L4 라벨 + 사람 검증 |
| Cross-Domain 목표 정답률 | (미실측) | CD-L1 80%+ / L2 70%+ / L3 50–60% / L4 40–50% (§2.2) |
| Bridge 품질 | confidence ≥ 0.9 비율 측정 인프라 (`eval/metrics/bridge_quality.py`) | confidence ≥ 0.9 비율 80%+ + 검토 SOP + 자동 만료 정책 (예: 6개월 미검토 candidate → 자동 rejected) |
| HITL | clarification + cost approval 활성 | `sensitive_decision` (대출/투자/계약 관련 high-stakes 결정 시 사람 승인) + 답변 후 explicit feedback 루프 |
| Tracing | Langfuse / LangSmith fail-soft | 모든 turn 의 노드별 token + cost + replan 횟수 + tool 호출 로그를 dashboard 로 분석 — replan ROI 정량화 |
| Streaming | SSE 노드 progress | 그래프 시각화 (pyvis) + 답변 근거 chunk hover preview |
| Integration test | 마커 0건 (실제 DB 가 필요한 수동 절차) | `pytest -m integration` 50+ 케이스 + CI 에 Neo4j/PG 서비스 컨테이너 + nightly run |
| Embedding 모델 | BGE-M3 1024d 자체 호스팅 | BGE-M3 + multilingual fine-tune (자동차·금융 도메인 코퍼스 LoRA) + 청크 100만 넘으면 Qdrant 분리 (현재 765K) |
| LLM 비용 | session HARD_LIMIT + turn budget + auto-approve | cost_estimator ±20% 정확도 검증 + 사용자별 quota + budget guard 발동 시 UX 완화 (부분 답변 + "예산 초과 — 추가 승인?") |

### 11.5 우선순위 권장 (다음 한 분기, v3.0) — 재배열

1. **eval 실측 (gate-zero)** — LLM 키 → 축소 매트릭스 (§10.17 d) → thesis headline (Hybrid > Vector multi-hop +30%p). **측정 전엔 아무것도 입증 안 됨.**
2. **answerability 측정** — % grounded vs 정보부족. cross-domain 의 정직한 평가 (특히 process refusal 보존 패턴).
3. **ProcessGraph 주요 축 (§10.18~20)** — process.yaml + DART 가동률 파서 (완료) + `PERFORMED_AT` 94 ✅ (manual_seed 35 + factoryon 59) + **내부 데이터 수용 규격** (로더 계약 + 등급 승급 C합성→A내부).
4. **상용 신호 (§12.1 P0+)** — MCP 래퍼 + Langfuse 실측 ON + 온톨로지 SHACL/pydantic 검증 + 축소 평가 매트릭스 (full LLM 트리거).
5. **ip 보조축 (경량)** — CPC bulk (완료) + OpenAlex (완료) + assignee→corp 매핑 + USPTO ODP bulk + IP-L1~L2 cross 시연. KIPRIS 후순위.
6. **gold QA 확장** — finance 100 / auto 100 / cross 50 / ip 100 + 외부 큐레이터 30% (자기충족성 완화).
7. **부품사 IR cross-reference** — DART finance 의 현대모비스/만도/한온시스템 사업보고서 → auto 도메인 BOM L4~5 보강 (Bridge 흐름의 reverse — finance → auto).
8. **데이터 채널 확장 (즉시 가능, 키 무관)** — EPA Annual Certification (Tier 3) / NHTSA TSB / DBpedia P527 / SEC EDGAR 글로벌 OEM 5사 더 추가.

---

## 12. 보완 개발 백로그 (Critical Gaps)

> 본 절은 §11 의 장기 비전과 **별개**다. §11 은 "어디로 가는가" — 본 절은 "지금 이 상태로 production 에 올리면 무엇이 깨지는가". 측정·코드·문서로 드러난 실제 부재만 적는다. 우선순위는 (P0+ 상용 신호 / P0 차단 / P1 운영필수 / P2 개선) 로 라벨.
>
> **전수 backlog (83 항목, 15 카테고리, P0~P3 트래픽라이트) 는 [BACKLOG.md](./BACKLOG.md) 가 SSOT.** 본 §12 는 P0+/P0/P1 핵심 항목의 요약. P2/P3 세부는 BACKLOG.md.

### 12.0 리스크와 대응 매트릭스

설계 시점에 식별된 영구 리스크와 대응책. 새로운 리스크는 BACKLOG.md 또는 [docs/mental_model.md](./docs/mental_model.md) §5 열린 질문 으로 추가.

| 리스크 | 영향 | 대응 |
|---|---|---|
| 공개 데이터로 Level 5~6 BOM 채우기 어려움 | 깊은 부품 그래프 희소 | **MVP 에서 Level 5~6 제외**, UI 에 "Level 4 까지 신뢰" 명시, post-MVP 분리 — 배터리·소재 L6 부분 적재 (§11.2) |
| `vehicle_id` / `corp_code` 단일 키로 부족 | 법인·차량·부품·특허 식별 혼란 | **`master.entities` 다형 키 구조 (§3.4) + `entity_id` + `entity_type`** |
| Bridge 매칭 정확도 | Cross-Domain 환각 | Wikidata QID + LEI + 사업자번호 + corp_code 4중 매칭 (§3.5), confidence 표시, < 0.7 자동 `needs_review` |
| LLM 환각 공급 관계 | 그래프 오염 | **§4.0 출처 등급 + §3.7 7키 confidence 필수 + Validator 게이트 (`LOW_CONFIDENCE_THRESHOLD=0.5`)** |
| 시점 모호성 | 공급 관계 정확도 저하 | `snapshot_year` 필수 + 라이프타임 엣지에 `valid_from/to` (§3.7) |
| OEM 비공개 BOM | Level 4 이하 한계 | Wikipedia + IR + 리콜 본문 + L4 coverage 63.7% 명시 (§10.5) |
| 합성 데이터 (산단공) 회사 귀속 오염 | ProcessGraph 사실성 위협 | `load_performed_at.py` source allowlist hard-check — DART/factoryon/manual 만 허용. 산단공·KAMP·AI Hub 자동 차단 (§4.0) |
| "제조" 표현이 공정·원가 기대 | 사용자 실망 | **§1 포지셔닝 "제품·부품·리콜·공급망 + BoP"** + §0 축 위계 정직 표기 |
| Cross-Domain 목표치 불일치 | 평가 신뢰도 저하 | **§6 4단계 층화 (CD-L1 80% / L2 70% / L3 50~60% / L4 40~50%)** |
| finance ↔ auto 스키마 변경 시 Bridge 깨짐 | Cross-Domain 장애 | `schema_version` 명시 (§3.7), 마이그레이션 스크립트 멱등 |
| MVP 일정 압박 (5주 → 분기) | 도메인 적재 + 평가 둘 다 압박 | **§11.5 우선순위 재배열**: eval 실측 → ProcessGraph 실데이터 → 상용 신호 → ip 보조축 → gold 확장 |
| 새 도메인 코드가 본질적으로 큰 LOC → 누적 변경량 < 5% 측정 불가 | §10.12 정량 게이트 무력화 | **§10.12 baseline reset 정책** — 도메인 추가/대형 기능 일괄 마다 reset + 누적 이력 (현재 3회: `4049caf` → `bab9411` → `414bc1b` → `831e72d`) |
| Bridge candidate 4,792 검토 SOP 부재 | 그래프 품질 시간갈수록 악화 | ✅ **도구 완료 (Q-1)** — Streamlit 검토 UI + 6개월 자동 만료 + 진행률 KPI ([docs/operations/bridge_review.md](./docs/operations/bridge_review.md)). 실제 라벨링은 운영 작업 → BACKLOG.md §6 |
| API 인증 / Rate limit | 외부 노출 시 보안 위협 | ✅ **구현 (O-1)** — API key 헤더 인증 + thread_id↔user_id 바인딩 + per-identity rate limit (`api/auth.py`). 잔여: OAuth2/multi-instance → BACKLOG.md §5 |
>
> **§12.1 상용 신호 백로그 (P0+) 가 가장 우선.** 기존 §12.2~§12.7 (운영·보안·배포·CI 등) 는 PoC → MVP → 상용 화살표의 후반부로 의도적 강등. **도메인3 (ip) + ProcessGraph + 축소 평가 매트릭스 + MCP·관측가능성** 이 우선.

### 12.1 상용 신호 (Service-Grade Signals, P0+) — 신설

| 항목 | 현재 | 필요 작업 |
|---|---|---|
| **MCP 래퍼** | **(wired)** — `src/autonexusgraph/mcp/{__init__,discovery,server,__main__}.py` 신규. 59 tools 자동 discovery + type hint→JSON Schema + `ListToolsRequest` 핸들러 round-trip 실측 PASS (2026-06-02). `make audit-mcp` 가 SDK 미설치 시 SKIPPED, 설치 시 server boot + handler round-trip 검증 | `pip install -e ".[mcp]"` (이제 `[all]` extras 에도 포함) → `python -m autonexusgraph.mcp` 로 stdio 서버 부팅. Claude Desktop / Cline 등이 .mcp.json 으로 본 서버 등록 후 호출 |
| **Langfuse 실측 ON** | **(wired)** — Langfuse 4.x OTEL native + ContextVar 격리 + `meta JSONB` 적재. `make audit-trace` 자동 검증, DoD #17 (b) dashboard 자동 반영 | `.env` 의 `TRACE_BACKEND=langfuse` + `LANGFUSE_*` 키 설정. simulation 모드 (LLM 비용 0) 또는 `--full` (실 agent run). 향후 보강: per-replan 이벤트 emit, replan ROI 정량화 |
| **온톨로지 SHACL/pydantic 검증** | **(wired)** — `src/autonexusgraph/ontology/` pydantic v2 strict 모델. `make audit-ontology` 자동 검증. SHACL/rdflib 회피 (LPG 그래프 conceptual mismatch + 무거운 dep) | yaml 로드 시점에 extra='forbid' + enum 정합 + relation.from/to cross-check + edge_required_meta 7키 SoT 강제. `schema_version` 헤더 1곳 SoT. 향후 보강: extractors.yaml / system_taxonomy.yaml / plants.yaml 등 보조 yaml 도 별도 모델 추가 |
| **축소 평가 매트릭스 실측** | **(wired)** — `AgentAdapter(rerank, llm_tier)` 1급 매트릭스 변수 + `eval/runners/run_matrix_smoke.py` 8 cells enumerate + thesis headline 자동 계산. `make audit-eval-matrix` simulation 모드 wire-up 검증 완료 (LLM 비용 0). DoD #17 (d) dashboard 자동 반영 | full LLM 측정은 `make audit-eval-matrix --full` (Sonnet 4.6 / GPT-4o-mini / Gemini Flash 중 1종) — Allganize 외부 gold (`eval/qa_gold/gold_qa_allganize_v0.jsonl` stub) 채워 thesis (§10.7) headline 실측 |
| **§10.12 baseline reset 정책** | dod_audit baseline `4049caf856` 고정, 정책은 §11.5 에만 산재 | **§10.12 본문 승격** + `make audit-dod` 출력에 baseline commit + 누적 reset 이력 + "도메인 추가 마다 reset" 명시 |
| **스택 업그레이드 경로 박음** | BGE-M3 / LangGraph 1.x 현행, 교체 금지 | 1줄 명시: Qwen3-Embedding-8B / Jina-rerank-v3 후보 + 기존 wired BGE-Reranker on/off ablation 활용 |
| **Bridge 품질 강화 (무료)** | sec.lei.corp_code **128** / `master.entity_map(lei)` **128** / bridge supplier strong-match **4** (confidence ≥ 0.9 reviewed) | ✅ GLEIF API `registeredAs` (business_no 10자리 / jurir_no 13자리) → corp_code 매칭. OC 매핑 파일은 form-gated → KR 한정 시나리오라 GLEIF API 단독으로 충분. OpenCorporates `_license.py` cc_by_sa 게이트 + `require_share_alike()` helper 추가 |

### 12.2 운영·보안 (P1 — 강등)

| 항목 | 현재 | 필요 작업 |
|---|---|---|
| **API 인증** | ✅ **구현** (`api/auth.py`) — `/chat` `/chat/stream` `/chat/resume` `/threads/{id}` 에 `Depends(authenticate)`. `X-API-Key` / `Authorization: Bearer` 헤더 + `API_KEYS` env (`token:user_id`). **thread_id ↔ user_id 바인딩** — 타인 히스토리 조회 403. `API_KEYS` 미설정 시 open 모드 (dev, 1회 경고). `/health` 는 인증 없음 | (잔여) OAuth2/OIDC 발급기관 연동 + 토큰 회전. 외부 IdP 통합은 reverse proxy 권장 |
| **Rate limit** | ✅ **구현** — per-identity (user_id / open 모드 IP) sliding-window, `API_RATE_LIMIT_PER_MIN`. **in-memory (단일 인스턴스)** | (잔여) multi-instance 분산 — reverse proxy / redis (§12.3) |
| **PII / 민감정보 정책** | 미정의 | 임원 인물·뉴스 본문에 이름·생년 포함 (`master.persons` 9,948 / (name, birth_year) 동명이인 분리). GDPR-style 삭제 권리 처리 / log redaction 정책 미문서화 |
| **`data/cost_log.jsonl` 회전** | 영속 append, size 무제한 (gitignored 확인 완료) | 일·주별 rotate + 보존 기간 정책 + 누계 집계 cron (`python -m autonexusgraph.llm.cost_history`) |
| **Secrets 관리** | `.env` 한 곳 | prod 는 vault / k8s secret 분리. `.env.example` 의 dev placeholder 와 prod 키 흐름 분리 절차 없음 |
| **TLS** | uvicorn http 만 | reverse proxy (nginx/caddy) + HSTS + cert renewal — Quickstart 에 없음 |

### 12.3 Production 배포 (P1 — 강등)

| 항목 | 현재 | 필요 작업 |
|---|---|---|
| **배포 가이드** | ✅ **작성** — [docs/operations/production_deploy.md](./docs/operations/production_deploy.md) + `infra/Dockerfile` + `docker-compose.prod.yml` (실행 가능) | k8s/compose prod 오버레이 / health probe / reverse proxy·TLS / blue-green / canary / 멀티 인스턴스 주의점 완료 |
| **백업·DR** | ✅ **구현 (O-3)** — `make backup`/`restore` (`scripts/ops/`) + [backup_dr.md](./docs/operations/backup_dr.md). PG `pg_dump -Fc`(임베딩 포함) + Neo4j community STOP→dump→START + 보존 prune. RPO≤24h / RTO 수분(dump 보유)·수시간(재앙: raw 재적재+재임베딩) | 잔여: off-site 동기화 + 분기 복원 드릴 RTO 실측 |
| **모니터링·알람** | ✅ **구현 (O-5)** — Prometheus exporter (`make metrics`/`serve-metrics`, `metrics_exporter.py`) + `infra/monitoring/`(prometheus/alerts 6/grafana 8패널) + compose prod 서비스 ([monitoring.md](./docs/operations/monitoring.md)). Langfuse(turn trace)와 보완 | 잔여: Alertmanager 발송 채널 |
| **Multi-instance scaling** | PG checkpointer 공유 가능 — 검증 안 됨 | uvicorn worker N + checkpointer concurrent write 검증 + LLM rate limit 분산 |
| **CI/CD** | ✅ **구현 (O-4)** — `.github/workflows/ci.yml`: `make smoke-e2e` keyless 게이트 (py3.10/3.11/3.12) + lint/mypy informational + DoD dashboard artifact | 잔여: `audit-dod --strict` (§10.7/§10.13 LLM eval 필요) + ephemeral PG/Neo4j 통합테스트 → LLM 키 / self-hosted runner 후 |
| **Integration test 마커** | `pytest -m integration` 0 케이스 | `tests/integration/*` 신설 — load_auto_all / extract_p3+p4 / cross_query 실제 DB end-to-end |

### 12.4 데이터 품질·운영 (P1)

| 항목 | 현재 | 필요 작업 |
|---|---|---|
| **Bridge candidate 검토 SOP** | 4,792 supplier candidate 영속 누적 — 검토 UI / 정책 없음 | (1) Streamlit 검토 페이지 — name match candidate 를 reviewer 가 ✓/✗ 라벨. (2) 6개월 미검토 candidate 자동 `rejected` 정책. (3) 검토 진행률 KPI |
| **confidence_score calibration** | 미수행 — A(0.95) / B(0.80) / C(0.50) 가 실제 정답률과 단조 미검증 | gold QA 100+ 실측 후 `eval/metrics/confidence_weighted.py` 로 calibration plot. 필요 시 출처별 confidence 재조정 |
| **`master.persons` 동명·동년생 충돌** | ✅ **측정 routine (Q-3)** — `make persons-collision` (`persons_collision.py`): NULL birth_year 비율 / 동명 다중 row / 병합의심 후보 | 실측 후 충돌률 높으면 (name, birth_year, 회사) 보조 키 도입 |
| **embedding backfill 진행률 가시화** | ✅ **구현 (Q-4)** — `make embed-status` (source별 embedded/total/pct/pending) | 잔여: 누락 청크 자동 재시도 cron (`make embed-chunks` 반복) |
| **데이터 freshness 모니터링** | ✅ **구현 (Q-5)** — `make freshness` (`freshness.py`): 8 소스 ingest·content 시각 + stale 판정, stale/error 시 exit 1 (cron 알람) | cron 등록 + `--stale-days` 튜닝 |
| **Schema 마이그레이션 버전 추적** | `infra/postgres/init/01~16.sql` 멱등 | Alembic 같은 versioned migration. 현재 `make migrate-schema-pg MIGRATE_FILE=...` 는 사용자가 무엇이 적용됐는지 추적 안 함 |

### 12.5 추출·그래프 완성도 (P1)

| 항목 | 현재 | 필요 작업 |
|---|---|---|
| **USES_PROCESS / MADE_OF (L6)** | `:Process` 노드 사전 적재 / `:Material` 미구현 / 엣지 0 | (1) 산단공 `:Process` ↔ `:Module` 매칭 routine, (2) `:Material` 노드 ontology + 배터리/합금 seed, (3) Wikidata P186 (made from material) staging |
| **DART 사업보고서 가동률 표** | 완료 (2026-06-01) | `_parse_utilization_table` 표 컬럼 정규화 + `auto.plant_utilization` 53 row 적재 |
| **부품사 IR cross-reference** | 미구현 | DART finance 의 현대모비스/한온/만도 사업보고서 → auto 도메인 SUPPLIED_BY/MANUFACTURED_AT 보강 (reverse-direction Bridge) |
| **NHTSA TSB / Manufacturer Communications** | 수동 zip 다운로드 모드만 | URL 자동 다운 routine (NHTSA URL 변경 추적) |
| **KNCAP / Euro NCAP / IIHS** | 인터페이스만 (KNCAP) / 미구현 (Euro/IIHS) | PDF 파서 + Standard 노드 매핑 |
| **Cypher 템플릿 추가** | finance **22** + auto **24** + ip **25** (총 71) | 새 use case (recall 전파·공급 집중도·시점 정합 cross) 별 템플릿 — 자유 Cypher 금지 원칙 유지 |
| **HITL `sensitive_decision`** | wired + 활성 (trigger=키워드 휴리스틱 / fallback=거절) | 고위험 답변 (투자 자문 / 법적 조언 / 주가 예측 인접) 키워드 자동 감지 + synthesizer 직후 게이트. SENSITIVE_KEYWORDS 보수 10종으로 시작 — 누적 false-positive 기반 정정 |
| **P3 LLM 4종 활성화** | `enabled:false` (COMPETES_WITH / MANUFACTURED_AT(LLM) / CONTAINS_MODULE / CONTAINS_PART) | 비용·환각 위험 검증 후 selectively 활성. validation gate 강화 |
| **N-domain bridge 일반화** | `bridge.corp_entity` 만 (2-domain 가정) | 3번째 도메인 추가 시 `bridge.drug_entity` / `bridge.component_entity` 등 다리 추가. 또는 `bridge.cross` 다형 1 테이블 |

### 12.6 평가·신뢰성 (P1)

| 항목 | 현재 | 필요 작업 |
|---|---|---|
| **12 조합 매트릭스 실측** | 인프라 완성, LLM 키 필요 | `make eval-full / eval-auto / eval-cross` 풀 실행 + `eval/reports/<run>/summary.md` PR 첨부 |
| **gold QA 확장** | finance 30 / auto 46 / cross 44 / ip 30 seed | 각각 100 row + CD-L1~L4 라벨 + 외부 큐레이터 30% (자기충족성 완화 — `docs/mental_model.md §5.7`) |
| **§10.12 baseline 이동 정책** | dod_audit 가 baseline (`4049caf856`) 고정. 실제 코어 변경량은 baseline 갱신 시점에 reset | "baseline 은 도메인 추가 마다 reset" 또는 "월 단위 reset" 같은 명시 정책 + 누적 차분 표 |
| **§10.13/14 trace 메트릭** | ✅ **구현 (E-3)** — `agents/hop_metrics.py` 가 per-turn cypher hop 수 + tool 호출 sequence 를 trace(Langfuse + PG `agent_trace`)에 기록 + eval pred_row `hop_count` + `main_hop_efficiency` 실제 hop 경로(`hybrid_vs_vector_hops`) | §10.13 ✅ 전환은 LLM eval 1회 실행 후 (현재 manifest 는 simulation) |
| **답변 사용자 피드백 루프** | UI 에 👍/👎/📝 wiring, 저장소 정의 없음 | `chat.feedback` 스키마 + 저주파 retraining loop |
| **Vector RAG 공정성 검증** | 매트릭스 내 Vector adapter 단독 측정 | gold QA 의 "Vector 도 풀 수 있는 질문" 비율 측정 — 작성자 편향 완화 |

### 12.7 문서·개발자 경험 (P2)

| 항목 | 현재 | 필요 작업 |
|---|---|---|
| **CONTRIBUTING.md / SECURITY.md** | ✅ **작성** ([CONTRIBUTING.md](./CONTRIBUTING.md) / [SECURITY.md](./SECURITY.md)) | 개발환경·smoke-e2e 게이트·도메인 불변식 8항·PR 절차 / 비공개 보고 채널·구현 통제·알려진 한계 정직표기 |
| **`docs/design/` ADR** | ✅ **작성 (F-3)** — ADR 4건 (LangGraph StateGraph / DomainHandler plug-in / Bridge 분리 테이블 / P1~P4 추출) + index ([docs/design/](./docs/design/)) | diagram 이미지는 후속 |
| **`_legacy/` 정책** | 보존 (v1/v2 KGQA Agent) | (a) deprecate notice + 일정 (b) 마이그레이션 가이드 (c) 또는 archived branch 로 이동 |
| **architecture diagram 통합** | `docs/autograph.md §2.5` mermaid 만 | README 본문에 1장 핵심 다이어그램 (현재 텍스트 박스만) |
| **performance benchmark** | PRD 목표만 | 실측 latency p50/p95/p99 + 평균 토큰/turn + 평균 cost/turn dashboard |
| **TROUBLESHOOTING.md** | ✅ **작성 (F-2)** — `docs/faq.md`(Q1~Q7) SSOT + 루트 [TROUBLESHOOTING.md](./TROUBLESHOOTING.md) 포인터. LLM rate limit·pgvector·Neo4j auth·DART/data.go.kr 키 만료 진단 보강 | — |
| **changelog** | git log + `_legacy/CHANGELOG.md` | repo root `CHANGELOG.md` keepachangelog 형식 |
| **GitHub Issue/PR template** | ✅ **작성 (F-4)** — `.github/ISSUE_TEMPLATE/{bug_report,feature_request,data_source}.md` + `config.yml`(보안 advisory·BACKLOG 링크) + `pull_request_template.md`(smoke-e2e·7키·LICENSE·BACKLOG 체크리스트) | — |
| **README 다이어그램·스크린샷** | 텍스트 박스만 | Streamlit UI 캡처 + Neo4j Browser cross-domain 결과 캡처 |

### 12.8 한 줄 요약 — "eval 실측 → ProcessGraph → 상용 신호 → production" 순서

- **MVP 검증 (PoC)** — 5/5 측정 가능 DoD pass. 즉시 다음 단계 진입 가능.
- **상용 신호 (P0+, §11.1)** — MCP 래퍼 + Langfuse 실측 ON + 온톨로지 SHACL + 축소 평가 매트릭스 실측 = 가장 우선. 대략 2~4 주.
- **도메인3 (IPGraph, §10.5#1)** — CPC + USPTO ODP + KIPRIS + tool pool + gold seed = N-domain 확장성 정량 증명. 대략 4~6 주.
- **제조 데이터 끝까지 채움 (§10.5#2)** — DATA_GO_KR + DART 가동률 + KOSIS. 2~3 주.
- **Production 까지의 비용 (P1, §11.2~§11.3)** — 인증 / 배포 / 백업 / CI / Bridge 검토 SOP / calibration. **의도적 후순위** — 위 3 가지 완료 후 4~8 주.

---

## 13. 문서

- **본 문서** — README + PRD 통합 SSOT v3.0 (요구사항·DoD·로드맵·의사결정 로그 일체)
- **[BACKLOG.md](./BACKLOG.md)** — **전수 미완료 항목 SSOT** (83 항목 / 15 카테고리 / P0~P3 트래픽라이트 + 활성화 트리거)
- [CONTRIBUTING.md](./CONTRIBUTING.md) — 내부 기여 가이드 (개발환경 · `make smoke-e2e` 게이트 · 도메인 불변식 8항 · PR 절차)
- [SECURITY.md](./SECURITY.md) — 보안 정책 (비공개 취약점 보고 · 구현된 통제 · 알려진 한계 정직표기)
- [TROUBLESHOOTING.md](./TROUBLESHOOTING.md) — 진단 포인터 (SSOT = [docs/faq.md](./docs/faq.md) Q1~Q7)
- [docs/architecture.md](./docs/architecture.md) — **시스템 구조 SSOT** — 패키지 토폴로지·LangGraph 11 노드·AgentState 33 필드 read/write 매트릭스·설계 결정 트레이드오프·plug-in 등록·SSOT 색인
- [docs/learning_guide.md](./docs/learning_guide.md) — **시스템 심화 가이드** — 문제 정의·이론적 기초·아키텍처 (StateGraph 11 노드 / AgentState 33 필드 / 4 가드 / cost 3 tier)·추론 흐름 깊이·예상 질문 (세미나 수준 발표용)
- [docs/mental_model.md](./docs/mental_model.md) — **결정 카탈로그** — 모든 설계 결정의 [확정]/[잠정]/[미정] 라벨, 트레이드오프 박스, 열린 질문 리스트
- [docs/design/](./docs/design/) — **ADR** (F-3) — 굳은 핵심 결정 4건 (LangGraph StateGraph / DomainHandler plug-in / Bridge 분리 / P1~P4 추출), context·decision·consequences
- [docs/autograph.md](./docs/autograph.md) — **AutoGraph (auto 도메인) 단독** 가이드 (구조 / 데이터 흐름 / 실행 순서 / 알려진 제약 / §2.5.4 배터리·소재 L5/L6 부분 적재)
- **[docs/process_graph.md](./docs/process_graph.md)** — **ProcessGraph (제조 공정 BoP — auto 수직 심화, 주요 축)** 설계+구현 SSOT — BoM⟂BoP 모델 + 학술 근거 (MASON/PSL/ISO) + 회사 귀속 A/B 정책 + 내부 데이터 수용 규격 (DoD #20)
- [docs/ipgraph.md](./docs/ipgraph.md) — **IPGraph (ip 도메인 = 보조축, corp_entity 브리지 전용)** 설계+구현 SSOT — DomainHandler / ontology yaml / tool pool / Cypher 템플릿 / gold QA / 작업 순서. 코드/스키마 완료, 특허 데이터 적재 대기
- **[docs/quickstart.md](./docs/quickstart.md)** — **5분 진입점** (환경 → DB → 최소 적재 → 첫 질의)
- **[docs/faq.md](./docs/faq.md)** — **Troubleshooting + 진단 트리** (자주 막히는 7 범주)
- **[docs/api_reference.md](./docs/api_reference.md)** — **3 도메인 (finance / auto / ip) tool 시그니처·반환 스키마 통합 SSOT** + finance 시나리오 5개 (구 `operations/rag_tools.md` 흡수)
- **[docs/gold_qa_guide.md](./docs/gold_qa_guide.md)** — **gold QA 운영 가이드** — 큐레이션·추가·수정·시스템 흡수·외부 큐레이터 30% 정책
- **[docs/runbook_traces.md](./docs/runbook_traces.md)** — **대표 질문 × 의도된 호출 trace** (9 시나리오 + 자랑 vs 실제 매핑)
- **[docs/system_review.md](./docs/system_review.md)** — **한계 통합 cold review** (13 한계 우선순위 + 자랑 vs 실제 7 항목 + 시급도 매트릭스)
- [docs/data_sources.md](./docs/data_sources.md) — 데이터 소스 후보 카탈로그 + 라이선스 + 인증 키
- [docs/data_inventory.md](./docs/data_inventory.md) — 적재 현황 측정 (재실행 시 갱신, `make audit-data-channels`)
- **[docs/data_lineage.md](./docs/data_lineage.md)** — **채널별 end-to-end 추적 SSOT** (raw → ingestion → PG/Neo4j → 7키 메타 → tool → 답변 시나리오 → 한계). `data_catalog.md` 통합 흡수 (2026-06-02).
- [docs/operations/docker_setup.md](./docs/operations/docker_setup.md) — Docker 스택 가이드
- [docs/operations/data_pipeline.md](./docs/operations/data_pipeline.md) — 멱등 파이프라인 + Step DAG + P1~P4 추출 + LangGraph 활성화
- [docs/operations/agents.md](./docs/operations/agents.md) — 에이전트 운영 (도메인 라우팅 / LangGraph / replan / checkpoint / tracing / safety 가드)
<!-- docs/operations/rag_tools.md 폐기 (2026-06-02) — finance 시나리오 5개 모두 docs/api_reference.md §4.4 흡수. 3 도메인 통합 도구 SSOT 는 docs/api_reference.md. -->
- [docs/operations/migrations.md](./docs/operations/migrations.md) — 스키마 마이그레이션 절차
- **[docs/operations/production_deploy.md](./docs/operations/production_deploy.md)** — **production 배포 SSOT (O-2)** — 이미지 빌드(`infra/Dockerfile`) · compose prod 오버레이(`docker-compose.prod.yml`) · health probe · reverse proxy/TLS · k8s · blue-green/canary · 멀티 인스턴스 주의점. dev Quickstart 와 분리
- **[docs/operations/bridge_review.md](./docs/operations/bridge_review.md)** — **Bridge candidate 검토 SOP (Q-1)** — `bridge.corp_entity` candidate ✓/✗ 라벨 (Streamlit UI) · 6개월 미검토 자동 거부 · 진행률 KPI · `make bridge-kpi`/`bridge-expire`
- **[docs/operations/backup_dr.md](./docs/operations/backup_dr.md)** — **백업·재해복구 SOP (O-3)** — PG/Neo4j dump (`make backup`/`restore`) · 보존 · RPO/RTO · 복원 드릴 · 재앙 시나리오
- **[docs/operations/monitoring.md](./docs/operations/monitoring.md)** — **모니터링·알람 SOP (O-5)** — Prometheus exporter(`make metrics`) · `infra/monitoring/`(alerts/grafana) · 메트릭 카탈로그
- [eval/qa_gold/README.md](./eval/qa_gold/README.md) — 평가 gold set 스키마 + 큐레이션 가이드

> KCGS ESG 등급 수집 가이드는 [docs/data_lineage.md §1.8](./docs/data_lineage.md#18-kcgs-esg).

---

## 14. Quickstart

```bash
# 0. .env 작성 (.env.example 복사 후 DART_API_KEY 채움)
cp .env.example .env

# 1. 의존성 설치
make install

# 2. DB 컨테이너 (PG + Neo4j minimal) — 데이터 폴더 먼저:
mkdir -p ~/arsim/DB_FG/{postgres,neo4j/data,neo4j/logs,neo4j/import,neo4j/plugins}
make up
# 외부 포트:  Neo4j  31009(HTTP) / 31010(Bolt)   PG  31011(pgvector 내장)
make health

# 3. 마스터 + DART 정형 데이터
make ingest-step1     # DART corp 마스터 + KRX 상장사 + targets 매칭
make load-companies   # master.companies
make load-entity-map  # ticker/jurir_no/business_no entity_map 시드

make ingest-step2     # DART filings + 재무 + 정형 지배구조 (자회사/임원/주주)
make load-all         # PG filings + financials
make load-graph-structural   # Neo4j SUBSIDIARY_OF / EXECUTIVE_OF / MAJOR_SHAREHOLDER_OF
make load-persons     # master.persons (동명이인 분리)

# 4. 외부 보강 (Wikidata + Wikipedia)
make ingest-step3     # Wikidata SPARQL (~55% 매핑)
make load-wikidata    # entity_map 보강 + Neo4j 속성

make ingest-step4     # Wikipedia 본문 + Infobox (~93% 매핑)
make load-wikipedia
make build-wiki-chunks   # Wikipedia 본문 → vec.chunks (section=wikipedia_ko)

# 5. 뉴스 + 글로벌 보강
make ingest-step6     # 연합뉴스 RSS
make load-news ; make load-graph-news     # 멘션 + CO_MENTIONED_WITH

make ingest-sec       # SEC EDGAR (한국 ADR — CIK 매핑 회사만)
make load-sec
make ingest-gleif     # GLEIF LEI (한국 jurisdiction 2,700건)
make load-gleif

# 6. 그래프 스키마 정합성 마이그레이션 (1회, 멱등 — 변경 0 이면 이미 적용됨)
make migrate-schema

# 7. KCGS ESG (수동 CSV 다운로드 후)
make ingest-kcgs                # 보도자료 모니터 — 등급 발표 알림
# 등급 CSV 를 data/raw/kcgs/<year>/ratings.csv 에 저장 후
make load-kcgs

# 8. 임베딩 (BGE-M3 GPU 가동 후 backfill)
# 별도 터미널에서:
make serve-embeddings
# 메인 터미널에서:
make embed-chunks         # vec.chunks.embedding NULL → BGE-M3 1024d 채움

# 9. 검증
make validate-quality     # 3-way cross 검증 + data/reports/quality_<date>.md

# 10. P3 LLM 관계 추출 (embedding 완료 후)
make p3-extract-dry       # 비용 추정 — LLM 호출 0
make p3-extract           # 실제 추출 (HARD_LIMIT $1.0)
make p4-load              # P4 검증 + Neo4j 적재

# 11. LangGraph 활성화 (§7.5.8 — PG checkpoint + tracing)
make install-agent        # pip install -e ".[agent]" — langgraph + langfuse + langsmith
make enable-langgraph     # 헬스체크: _HAS_LANGGRAPH + checkpointer 타입 확인
# (선택) tracing: .env 에 TRACE_BACKEND=langfuse + LANGFUSE_* 키 또는 TRACE_BACKEND=langsmith + LANGSMITH_API_KEY

# 12. API + UI 가동
make serve-api            # FastAPI :31020 — POST /chat (blocking) + /chat/stream (SSE)
pip install streamlit     # (선택) UI 의존성
make serve-ui             # Streamlit :31021 채팅 UI — st.status 노드 진행 표시

# 13. 평가 (gold 큐레이션 후)
make eval-smoke           # 3 row 빠른 검증
make eval-full            # 100문항 4 어댑터 매트릭스
```

### 도구 사용 예시

```python
from autonexusgraph.tools import (
    lookup_company, list_subsidiaries, get_executives,
    get_companies_of_person, find_paths, search_documents,
)

# 1) 회사 식별
lookup_company("삼성전자")
# → [{"corp_code": "00126380", "name": "삼성전자(주)", "stock_code": "005930",
#     "wikidata_qid": "Q20718", "wikipedia_title_ko": "삼성전자"}]

# 2) 자회사 그래프
list_subsidiaries("00126380", snapshot_year=2024, limit=10)
# → [{"child_name": "삼성디스플레이", "ownership_pct": 84.78, ...}, ...]

# 3) 인물 → 임원직 회사 매트릭스
get_companies_of_person("이재용")
# → 동명이인 모두 합쳐 반환 (회사·역할·연도)

# 4) 멀티홉 경로
find_paths("00126380", "00164779", max_hops=3)
# → 삼성전자 ↔ SK하이닉스 최단 경로

# 5) Hybrid RAG
search_documents(
    "반도체 사업 위험요인",
    corp_code="00126380",
    fiscal_year=2024,
    section_contains="위험",
    top_k=5,
)
```

크롤러는 **이어받기·실패추적·Ctrl+C 안전종료** 지원. 로더는 모두 **idempotent**. raw 만 있으면 `data/processed/` 와 DB 는 언제든 재생성 가능.

### Quickstart — AutoGraph (자동차 도메인)

AutoNexusGraph 와 동일 인프라 (PG / Neo4j / pgvector / BGE-M3) 위에 자동차 도메인만 추가.

```bash
# 0. 인프라는 AutoNexusGraph quickstart 와 공유 — 동일 docker 컨테이너에 스키마만 추가
# infra/postgres/init/ 의 01~24 sql (총 25 파일, 12a/12b 별도) 이 멱등이라 hot-apply 가능 (docs/operations/migrations.md).
# 빈 볼륨이면 docker entrypoint 가 01~24 를 순차 자동 실행 — 아래는 hot-apply (이미 부팅된 인스턴스 대상).
make migrate-schema-pg MIGRATE_FILE=07_autograph.sql
make migrate-schema-pg MIGRATE_FILE=08_bridge.sql
make migrate-schema-pg MIGRATE_FILE=09_vec_chunks_auto_meta.sql
make migrate-schema-pg MIGRATE_FILE=10_autograph_bom.sql
make migrate-schema-pg MIGRATE_FILE=11_autograph_staging.sql
make migrate-schema-pg MIGRATE_FILE=12a_autograph_inspections.sql
make migrate-schema-pg MIGRATE_FILE=12b_autograph_investigations.sql
make migrate-schema-pg MIGRATE_FILE=13_autograph_oem_sec.sql
make migrate-schema-pg MIGRATE_FILE=14_master_entities.sql
make migrate-auto-production         # 15_autograph_production.sql (DART 사업보고서 파서)
make migrate-auto-kama               # 16_autograph_kama_macro.sql
make migrate-schema-pg MIGRATE_FILE=17_autograph_oem_news.sql       # IR/뉴스룸 events_oem_news
make migrate-schema-pg MIGRATE_FILE=20_auto_minerals.sql            # USGS 핵심광물 (L6 소재 부록)
make migrate-schema-pg MIGRATE_FILE=21_auto_ev_chargers.sql         # EV 충전 인프라 (예정 — `DATA_GO_KR_API_KEY` 발급 후)
make migrate-schema-pg MIGRATE_FILE=24_auto_factoryon.sql           # 팩토리온 공장등록 (부분 적재 90행)
python -m autograph.loaders.neo4j_init    # CONSTRAINT/INDEX 멱등 — ontology/auto/entities.yaml SSOT

# (옵션) pre-push 정합성 검증 — DB·LLM 없이 동작 (mock 모드)
make smoke-e2e                       # pytest + audit-ontology (cypher cross-check) + audit-eval-matrix sim + audit-mcp + audit-ipgraph + audit-trace sim + gold qa lint

# 1. 인제스션 (.env 의 AUTO_INGEST_MAKES / AUTO_INGEST_YEAR_MIN/MAX 기반)
make ingest-auto-all                # = vpic + recalls + complaints + safety + wikipedia + epa + investigations + sec-oem
# 한국 시장 / KATRI / KNCAP (graceful skip — 키 없으면 0 byte)
make ingest-datagokr-recalls        # data.go.kr 3048950 리콜 CSV (무인증, 수동 다운)
make ingest-datagokr-inspections    # data.go.kr 15155857 (CSV 수동 다운)
make ingest-katri                   # bigdata-tic.kr (BIGDATA_TIC_CLIENT_ID/SECRET 필요)
make ingest-kncap                   # KNCAP (KNCAP_API_KEY 또는 수동 CSV)

# 2. P2 결정적 적재 — raw → PG → Neo4j → bridge → seed/supplier/recall→comp → chunks
make load-auto-all
# 의존 순서: neo4j-init → pg → specs → neo4j → bridge → standards/plants → safety → epa → aihub
#          → nhtsa-taxonomy → supplier-edges → complaints-neo4j → recall-components → complaint-components
#          → investigations → oem-sec → derive-contains-system → wikidata-part-supplies → manufactured-at
#          → build-chunks-auto

# 3. 제조 공정·생산 데이터 (옵션 — manufacturing 어댑터 보강)
make load-sandang-processes         # 산단공 합성 공정데이터 → :Process 사전
make load-dart-production           # DART 사업보고서 본문 파서 → auto.production_*
# 팩토리온 (DATA_GO_KR_API_KEY 발급 후)
make ingest-factoryon-company NAME=현대자동차

# 4. 청크 임베딩 (finance 와 동일 BGE-M3 backfill — generic 작업)
make embed-chunks

# 5. (선택) P3 LLM 관계 추출 — 비용 가드 dry-run 먼저
make extract-auto-p3-cost MFR_IDS=498 P3_LIMIT=50
make extract-auto-p3      MFR_IDS=498 P3_LIMIT=50 P3_HARD_LIMIT=2.0
make validate-auto-p4     # auto.staging_relations → P4 → Neo4j candidate/validated 적재

# 6. 에이전트 호출 (도메인 명시 또는 자동 판정)
python -c "from autonexusgraph.agents import run_agent;
s = run_agent('Hyundai Sonata 2024 리콜 사례', domain='auto');
print(s['answer'])"

# 7. 평가
make eval-auto                       # eval/reports/auto_<timestamp>/summary.md
make eval-cross                      # CD-L1~L4 30문항 (§8.1)

# 8. DoD 트래픽라이트 (본 문서 §10 — 20 항 — v3.0 IPGraph + ProcessGraph 흡수)
make audit-bom-coverage
make audit-edge-meta
make audit-dod                       # 20 항 종합 — eval/reports/dod_v3.0.md
```

자세한 절차·미구현 영역·회귀 안전성은 [docs/autograph.md](./docs/autograph.md). 도메인 라우팅 흐름은 [docs/operations/agents.md](./docs/operations/agents.md#도메인-라우팅-finance--auto--cross_domain).

### Quickstart — IPGraph (특허 도메인)

상세 시나리오·핸들러·온톨로지·도구 SSOT 는 [docs/ipgraph.md](./docs/ipgraph.md). **코드/스키마 완료, KIPRIS·USPTO 데이터 적재만 사용자 액션 대기.**

```bash
# 0. ENV 에 ipgraph 추가 (도메인 plug-in soft-load 활성)
echo "AUTONEXUSGRAPH_DOMAIN_PLUGINS=autograph,ipgraph" >> .env
# (선택) KIPRIS_API_KEY=…   # 공공데이터포털 발급 후

# 1. 스키마 마이그레이션 (적용 완료 — hot-apply 재실행도 멱등)
make migrate-schema-pg MIGRATE_FILE=18_ipgraph.sql       # ip.patents/assignees/citations/inventors 등 12 테이블
make migrate-schema-pg MIGRATE_FILE=19_ipgraph_bridge.sql # ip.assignee_corp_map join 테이블
make migrate-schema-pg MIGRATE_FILE=22_ip_works.sql      # OpenAlex ip.works/institution/work_institution
make migrate-schema-pg MIGRATE_FILE=23_ip_cpc.sql        # CPC scheme 계층

# 2. 데이터 인제스션 (실제 Makefile 타깃 — `ip` prefix 없음)
make load-cpc                    # ✅ 완료 — 무인증 USPTO/EPO CPC scheme bulk → 10,695 row
make ingest-openalex             # ✅ 완료 — OpenAlex 수집 (OPENALEX_EMAIL ENV 권장, 일 10만 크레딧)
make load-openalex               # ✅ 완료 — works 629 / institution 38 적재
# (대기) KIPRIS_API_KEY 발급 후
make ingest-kipris               # 한국 특허·출원
# (대기) USPTO Open Data Portal bulk (PatentsView 후속, 2026-03-20 이관, 무인증)
make ingest-uspto-odp
# (대기) assignee 적재 후 corp 매핑
make load-assignee-corp-map      # ip.assignee_corp_map 매칭 (supplier candidate SOP 재사용)

# 3. 평가 + DoD 재측정
make eval-ip                     # gold_qa_ip_v0.jsonl 30 row (IP-L1/L2/L3 각 10)
make eval-cross                  # CD-L3/L4 ip 결합 포함 (cross 44 row 중 IP 결합 변형 6 row 포함)
make audit-dod                   # §10.12 코어 변경량 — baseline 831e72d (상용화 P0/P1 reset) 기준 0% ✅
```

---

## 15. 라이선스

내부 연구·개발 단계. 라이선스 미정.

---

## 16. 부록 — 의사결정 로그 + 변경 로그

### 16.1 핵심 의사결정 로그 (v2.1 + v2.2 + v3.0 누적)

| 결정 사항 | 선택 | 대안 | 사유 |
|---|---|---|---|
| 포지셔닝 | "제품·부품·리콜·공급망" | "자동차 제조" | 공개 데이터 가용 범위와 일치 |
| ER 마스터 키 | `entity_id` + `entity_type` 다형 | `vehicle_id` 단일 | 법인·차량·부품 식별 체계가 본질적으로 다름 |
| Bridge 대상 | `corp_entity` (manufacturer + supplier) | `corp_manufacturer` (OEM만) | 부품사 Cross-Domain 가치 흡수 |
| BOM MVP 깊이 | Level 0~4 안정 + L5~6 부분 진입 | Level 0~6 일괄 | 공개 데이터 가용성 정직 반영 |
| 출처 신뢰도 | A/B/C 등급 + confidence 수치 + row 단위 동적 격상 | "출처 명시"만 | 그래프 오염 정량 통제 + C합성→B/A 승급 |
| Cross-Domain 평가 | 4단계 층화 (L1~L4) | 일률 60%+ | 난이도별 가치 명확화 |
| 도메인 라우팅 | UI 명시적 토글 | LLM 자동 분류 | 오분류 차단 |
| Bridge 키 | Wikidata QID 1차 + LEI + 사업자번호 | QID 단일 | 매칭 실패 완충 |
| 그래프 계층 | 엣지 속성 (`class`, `level`) | 노드 라벨 다양화 | 쿼리 단순성 |
| 인프라 공유 | finance 와 동일 컨테이너 | 별도 스택 | 운영 단순성 |
| **v2.2 도메인3 선택** | **특허 (IPGraph)** | 의약품 / 전자제품 / 배터리 단독 | 공개 데이터 확보 1차 병목 — KIPRIS / USPTO ODP / CPC / OpenAlex 전부 정형·무료, LLM 0% |
| **v2.2 Bridge 확장 방식** | 신규 join `ip.assignee_corp_map` | `bridge.corp_entity` 컬럼 추가 | core/bridge 스키마 변경 0 → §10.12 < 5% 보존 |
| **v2.2 배터리·소재 위치** | auto 의 L5/L6 곁가지 (`docs/autograph.md` §2.5.4) | 별도 도메인 `battgraph` | 회사단위 소싱 sparse — 별도 도메인 정당화 부족, BOM 하향이 자연스러움 |
| **v2.2 4번째~ 강등** | pharmagraph/elecgraph/energygraph/foodgraph 모두 §9 영구 비목표 | "다음 도메인" 으로 비전 유지 | ip 가 §10.12 < 5% 실측 증명한 뒤 의사결정. 산만함 방지 |
| **v2.2 상용 신호 승격** | MCP + Langfuse + SHACL + 축소 평가 매트릭스 = DoD #17 | 운영 (인증/배포/백업/CI) 우선 | 1차 목표 = "**서비스 등급 agent + ontology 정량 증명**" 으로 격상 |
| **v2.2 평가 매트릭스 축소** | 4 어댑터 × FAST tier 1종 + Allganize + rerank ablation | 12 조합 풀 실측 | 예산 + thesis(§10.7) headline 우선. 2번째 LLM 은 subset |
| **v2.2 baseline reset 정책** | 도메인 추가 마다 reset + 누적 reset 이력 | baseline 고정 (`4049caf856`) | 새 도메인 코드가 본질적으로 큰 LOC → 누적 변경량으로는 < 5% 가 측정 불가 |
| **v2.2-rev1 ProcessGraph 격상** | auto 심화 (§11.2 + `docs/process_graph.md` SSOT) + §4.0.1 row 단위 격상 | (a) 새 도메인 (4번째) (b) `:Process` 단일 노드 단순 모델 | BoM ⟂ BoP 직교 확장 (학술 정렬 MASON/PSL). 회사 귀속 A/B 만, 패턴 C 분리. §10.12 < 5% 보존 (auto 어댑터 내 확장) |
| **v3.0 ip = 보조축 라벨링** | "도메인3" 유지하되 **"수평 cross 진입 어댑터 (corp_entity 브리지 전용)"** 부제 | "도메인3 정식 = 본체와 동급" | ip 와 process 는 층위가 다름 — ip = 수평 cross, process = 수직 심화. ip 가 약화된 것이 아니라 architectural role 이 다름 |
| **v3.0 process = 주요 축 정직 표기** | "1급 BoM⟂BoP 모델 + sparse 인스턴스" | "주요 축, 데이터 미래 대비" | 모델·taxonomy(410/550)+INSTANTIATES/PRECEDES 적재 완료, 회사 귀속만 0 — 표현 정확화 |
| **v3.0 L6 부분 적재 라벨링** | `(부분 적재)` — Material 6/Mineral 5/DERIVED_FROM 17/MADE_OF 8 | `(예정)` | 실제 적재된 데이터 정직 반영 |
| **v3.0 단일 SSOT 통합** | README + PRD + PRD_process_graph → 단일 README v3.0 | 분리 유지 + 동기화 | 세 문서 간 버전·DoD 항수·수치 drift 영구 해소 |

### 16.2 통합·변경 로그 (v2.2 → v3.0, 2026-06-02)

| 변경 | 사유 |
|---|---|
| **README + PRD + PRD_process_graph → 단일 README v3.0** | 세 문서 간 버전·DoD 항수·수치 drift 영구 해소. PRD.md / PRD_process_graph.md 삭제 |
| **§0 축 위계 신설** | 본체(auto+process) / 대칭(finance) / 보조(ip) / 곁가지(L6) — 평평한 도메인 나열에서 수직 위계로 |
| **ip = "도메인3 정식"** → **"수평 cross 진입 어댑터 (보조축)"** | ip 와 process 는 층위가 다름. ip = 수평 외부 소스 (corp_entity 브리지 전용), process = 수직 심화 (BoM⟂BoP) |
| **process = "auto 심화 v2.2-rev1"** → **"주요 축 (수직 심화)"** | BoP 모델 완성 + 회사 귀속 인스턴스 sparse — 1급 모델로 격상하되 데이터 부족 정직 표기 |
| **DoD 17항 → 20항** | #18 BoP 모델 / #19 회사 귀속 인스턴스 / #20 공정 cross 시연 (내부 데이터 수용 규격) 신규 |
| **DoD #15/16 정량 증명 유지** | ipgraph 가 완전 구현되었으므로 "보조축 약화" 폐기. 코어 변경 <5% 재측정 + ip gold seed 정량 목표 유지 |
| **§3 아키텍처 sub-section 4개 신설** | §3.4 ER 마스터 + §3.5 Bridge 명세 + §3.6 4-Pass + §3.7 7키 메타 (§4.5/§4.6/§6.6/§6.7 흡수) |
| **§4.0 신뢰도 등급 + §4.0.1 row 단위 격상 신설** | §3.5/§3.5.1 흡수 |
| **§6 Cross-Domain 4단계 층화 + 비교 매트릭스 신설** | §8.1/§8.2 흡수 |
| **§7 미구현 표 — DART 가동률 파서 TODO 행 정정** | 실제 코드: `_parse_utilization_table` + `plant_utilization` 53 row 적재 완료 (2026-06-01). "TODO" 주장은 사실 오류 |
| **L6 `(예정)` → `(부분 적재)`** | 실제 적재: Material 6 / Mineral 5 / DERIVED_FROM 17 / MADE_OF 8 |
| **§4.3 IPGraph 데이터 소스 갱신** | PatentsView REST 종료 (2026-03-20, 410 Gone) → USPTO Open Data Portal bulk 이관. OpenAlex 무료 키 필수 (2025-02~) 명시 |
| **§16 부록 의사결정 로그 + 변경 로그 신설** | §13 흡수 + v3.0 변경 추적 |
| **`bridge.corp_entity` 4,806 / `SUPPLIED_BY` 30 / `supplier_seed.yaml` 19개사 SSOT** | †† 슬롯 사실 정정 (이전 통합안의 46 수치는 부정확 — 19 공급사 × 46 mapping → Neo4j 30 dedupe) |
| **§13 문서 — PRD.md 링크 제거** | 단일 SSOT 보장 |
| **§14 Quickstart — DoD 17 → 20 / `dod_v2.2.md` → `dod_v3.0.md`** | DoD 항수 갱신 반영 |

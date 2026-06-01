# AutoNexusGraph

> **자동차 제품·부품·리콜·공급망 (auto) + 한국 상장사 공시·재무 (finance) 두 도메인을 그래프·정형·벡터 하이브리드로 추론하고, `bridge.corp_entity` 로 Cross-Domain 까지 한 turn 안에 묶는 멀티도메인 GraphRAG 에이전트. 단일 도메인이 아닌, 도메인 어댑터를 plug-in 으로 추가하는 N-domain GraphRAG umbrella 가 최종 형태.**

자동차 OEM/부품사 ↔ 재무 데이터를 한 질문으로 추적 (예: "현대모비스 매출과 모비스가 공급하는 차종의 최근 리콜은?", "LG에너지솔루션 배터리를 쓰는 OEM 의 영업이익과 KCGS ESG 등급은?"). Vector 단독 RAG 가 풀지 못하는 멀티홉 / Cross-Domain / 시점 포함 공급망 추론을 Graph(Neo4j) + SQL(PostgreSQL) + Vector(pgvector) 하이브리드로 해결. Azure 종속 제거, LLM Provider(OpenAI / Anthropic / Google / 로컬) 환경변수 교체 가능. 도메인 모드는 사용자 hint 또는 키워드 자동 라우팅 — `auto` / `finance` / `cross_domain`.

상세 요구사항은 [PRD.md](./PRD.md) (v2.1) · AutoGraph(자동차) 전용 가이드는 [docs/autograph.md](./docs/autograph.md) · 결정·트레이드오프·열린 질문은 [docs/mental_model.md](./docs/mental_model.md) · 최종 비전 / 장기 로드맵은 본 README §10 참조.

> **구성 요약:**
> - **Core** (`src/autonexusgraph/`) — LangGraph multi-agent (StateGraph 11 노드 + 함수 체인 fallback), LLM 어댑터 (OpenAI/Anthropic/Google/local 자동 dispatch), 4 가드 (prompt_safety / cypher_guard / number_guard / language_guard), 비용 가드 3 tier (세션 hard limit + 도메인별 turn budget + auto-approve), DB·embedding·평가 harness 공유 인프라.
> - **현재 구현 범위:** Send API 병렬 worker · Validator + Replan loop (max 2) · HITL clarification + cost approval · 22 Cypher 템플릿 레지스트리 (finance) + 19 (auto) · Pre-synth number guard + post-synth validator cross-check · PG checkpointer · streaming (SSE) · tracing (Langfuse/LangSmith). 미구현 / wired-but-disabled 항목은 §7.
> - **Finance 도메인** (`src/autonexusgraph/tools/financials,graph,retrieve`) — DART 공시 / KRX 마스터 / ECOS / Wikidata / Wikipedia / SEC EDGAR / GLEIF / 연합뉴스 RSS / KCGS ESG → 코스피200+코스닥100.
> - **Auto 도메인** (`src/autograph/`) — NHTSA(vPIC/Recalls/Complaints/SafetyRatings/Investigations/TSB) + EPA fueleconomy + SEC EDGAR (글로벌 OEM) + Wikidata(manufacturers/models/suppliers, P176) + AI Hub(부품 결함 / 자율주행 진단) + KOTSA 수리검사 + DART 사업보고서 (제조 공정·생산) + 산단공 합성 공정 + 팩토리온(공장 등록) scaffold.
> - **Cross-Domain Bridge** — `bridge.corp_entity` 가 두 도메인을 wikidata_qid / LEI / sec_cik / 사업자번호 / 이름으로 매칭. 한국 OEM (현대차/기아/현대모비스/현대위아/한국타이어 …) + 글로벌 OEM (Ford/GM/Stellantis/Tesla …) 가 corp_code/sec_cik 와 직접 연결.
> - **확장성 (Domain plug-in)** — Core 는 외부 도메인 패키지를 직접 import 하지 않음. ENV `AUTONEXUSGRAPH_DOMAIN_PLUGINS` (기본 `autograph`) 의 모듈명을 import 시점에 soft-load → `register_handler` 부작용으로 활성. PRD §10.12 "코어 변경량 < 5%" 보존. 3번째 도메인 (의약품 · 전자제품 · 에너지 · 식품 등) 도 같은 패턴으로 추가 가능 — §10.1 참조.

---

## 1. 한눈에 보는 현황

> 이하 수치는 **2026-05-29 측정 시점** 기준. 갱신은 `data_inventory.md` + `eval/reports/prd_dashboard_latest.md` 참조. 모든 정량 수치는 ingestion 재실행 후 변동 가능 — SSOT 는 PG / Neo4j 직접 조회.

### Finance 도메인 (코스피200 + 코스닥100)

| 영역 | 적재량 | 비고 |
|---|---:|---|
| `master.companies` (코스피200+코스닥100) | 295 | 활성 회사 |
| `master.entity_map` (ticker/QID/LEI/CIK/ISIN/…) | 1,979 | 10 종 외부 ID |
| `master.persons` / 임원 이력 | 9,948 / 22,303 | (name, birth_year) 분리 |
| `fin.financials` (XBRL) / `fin.filings` | 184K / 4.6K | 3년치 |
| `news.articles` / 멘션 | 338 / 141 | 연합뉴스 RSS 3종 |
| `wiki.wikipedia_pages` / `wiki.wikidata_facts` | 276 / 466 | 93.6% / 55.6% 매핑 |
| `sec.filings` (한국 ADR) / `sec.lei` (GLEIF KR) | 1,857 / 2,700 | LEI 매칭 120 |
| `vec.chunks` (DART + Wikipedia) | 748,812 | embedding backfill 진행 중 |
| Neo4j Company / Person / NewsEvent | 12,914 / 14,536 / 85 | 동명이인 2,171 분리 |
| Neo4j SUBSIDIARY_OF / EXECUTIVE_OF / MAJOR_SHAREHOLDER_OF | 8,661 / 33,064 / 12,548 | 시점(snapshot) + source 부여 |

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
| `bridge.corp_entity` (suppliers 포함) | **4,806** | manufacturer reviewed 10 (sec_cik 9 + corp_code 1 + qid 1) / supplier candidate 4,792 / supplier reviewed 2 |
| Neo4j Manufacturer / Model / Variant / Recall | 22,145 / 6,770 / 428 / 493 | `AFFECTED_BY` 인덱스 매칭 |
| Neo4j Complaint / Investigation | 16,005 / 154 | NHTSA REPORTED_IN / INVESTIGATED_BY |
| Neo4j System / Module / Part | (load-auto-all 후) | Level 3 / 4 / 5 — `system_taxonomy.yaml` 19 시스템 (POWERTRAIN, BRAKE, ADAS, …) |
| Neo4j Supplier / SUPPLIED_BY | (manual seed 후) | `supplier_seed.yaml` 19 공급사 × 46 매핑 (LG에너지솔루션·삼성SDI·SK온·한온·만도·Bosch·Continental …) |
| Neo4j RECALL_OF / CONTAINS_COMPONENT | 601 RECALL_OF | NHTSA taxonomy 적재 후 recall→component 매칭율 100% |
| Neo4j Standard / Plant / Complaint | (seed 후) | `standards.yaml` 22 + `plants.yaml` 18 + `manufactured_at_seed.yaml` 46 모델↔공장 |
| `auto.staging_relations` (P3 LLM + Wikidata P176) | extract-auto-p3 후 | SUPPLIED_BY / RECALL_OF 후보 — P4 검증 후 그래프 적재 |
| `auto.processes` (산단공 합성 15151075) ⭐ 6/1 | (`make load-sandang-processes` 후) 550 row / 410 공정명 | C 등급 (0.50) — 공정명 정규형 사전. agent tool `search_processes` |
| `auto.plant_capacity` (DART III. 생산·설비) ⭐ 6/1 | (`make load-dart-production` 후) capacity ~50 / production ~70 | B 등급 (0.80) — 6 OEM × 사업보고서. agent tool `get_plant_capacity` / `get_oem_production` / `list_plants_by_oem` |
| `auto.macro_production_yearly` (KAMA 15051116) ⭐ 6/1 | (`make load-kama-macro` 후) 21 row | A 등급 (0.95) — 연 단위 한국·세계 생산량. agent tool `get_macro_production` |
| `auto.macro_industry_monthly` (KAMA 15051118) ⭐ 6/1 | 204 row | A 등급 — 월 단위 내수·수출·수출금액. agent tool `get_macro_industry` |
| Neo4j MANUFACTURED_AT (DART) ⭐ 6/1 | (load-dart-production 후) ~10 edges | `(Manufacturer)-[r:MANUFACTURED_AT {capa_units, actual_units, utilization_pct, source_type='dart_business_report', confidence_score=0.80}]->(Plant)`. plants.yaml 미등록 plant 는 skip |

---

## 2. 핵심 특징

- **멀티도메인** — `finance` + `auto` + `cross_domain` 3 모드. 도메인은 hint 또는 키워드 자동 라우팅 (`src/autograph/policy.py::route_domain`). 단일 에이전트가 두 도메인 + 둘의 교차 추론을 한 turn 안에 처리. core 는 외부 도메인 패키지를 직접 import 하지 않고 `_domain_handler.discover_plugins()` 가 ENV `AUTONEXUSGRAPH_DOMAIN_PLUGINS` (csv, 기본 `autograph`) 를 기반으로 첫 호출 시 1회 soft-import — finance-only 환경에서는 ENV 를 빈 값으로 두면 됨
- **금융 도메인** — DART 공시 / KRX 마스터 / ECOS / Wikidata / Wikipedia / SEC EDGAR / GLEIF / 연합뉴스 RSS / KCGS ESG → 코스피200+코스닥100 대상
- **자동차 도메인** — NHTSA vPIC/Recalls/Complaints / Wikidata (manufacturers/models/suppliers) / (옵션) car.go.kr / KATRI / KNCAP / 한국교통안전공단 수리검사. BOM Level 0~5 — Manufacturer → Model → Variant → System(L3) → Module(L4) → Part(L5, 리콜·LLM 출처에서 부분 커버). Level 6(소재·공법)은 PRD non-goal
- **3-Store 하이브리드** — Neo4j(관계) + PostgreSQL(수치·메타·벡터) + (옵션) Qdrant — 청크 100만 이하는 pgvector 통합 운영
- **Multi-Agent + Planning (LangGraph)** — Triage / Planner / Supervisor / Workers / Validator / Synthesizer 역할 분리 [PRD §7.5](./PRD.md#75-multi-agent--planning-상세-설계-langgraph)
- **채팅형 UI + 대화 히스토리** — thread 기반 multi-turn [PRD §7.6](./PRD.md#76-web-ui-채팅형--대화-히스토리-multi-turn)
- **Deterministic-first 추출** — XBRL 재무·지배구조는 정형 직매핑 (0% LLM), 서술형 관계만 selective LLM [PRD §6.5](./PRD.md#65-추출-전략-v1v2-혼합-deterministic-first--selective-llm)
- **LLM 어댑터 패턴** — `LLMClient` 단일 인터페이스, `LLM_PROVIDER` 한 줄로 백엔드 교체
- **한국어 자체 임베딩** — BGE-M3 + BGE-Reranker (GPU 자체 호스팅)
- **Entity Resolution 마스터** — corp_code 를 단일 키로 wikidata_qid / lei / cik / isin / business_no 등을 묶음. 동명이인 인물은 (name, birth_year) 분리
- **재실행 가능한 멱등 파이프라인** — raw → processed → DB. 모든 적재 `ON CONFLICT DO UPDATE` / `MERGE`. raw 만 있으면 언제든 재생성 가능
- **도메인 확장성 (N-domain plug-in)** — core 는 외부 도메인 패키지를 직접 import 하지 않음. `_domain_handler.discover_plugins()` 가 ENV `AUTONEXUSGRAPH_DOMAIN_PLUGINS` 의 모듈을 첫 호출 시 soft-import 하고, 도메인 패키지의 `register_handler()` 부작용으로 활성. PRD §10.12 "코어 변경 < 5%" 보존 — 3번째 도메인 (의약품·전자제품·에너지·식품) 도 동일 패턴
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
├─ Ingestion Workers : DART/KRX/ECOS/Wikidata/Wikipedia/News/SEC/GLEIF/KCGS 클라이언트
├─ Loaders            : PG/Neo4j 멱등 적재 (P1 deterministic / P2 deterministic / P3 LLM / P4 cross-validate)
├─ Tools              : 사전 정의 함수 풀 (financials/graph/retrieve) — 자유 SQL/Cypher 금지
├─ Safety             : prompt_safety (XML escape + injection 감지 + high-risk 단발 차단) · cypher_guard (READ-ONLY + APOC write/dynamic-cypher procedure 블록) · language_guard
├─ Agents (LangGraph) : Triage → Planner(DAG) → Supervisor ↔ Workers(병렬: research/graph/sql/calculator)
│                       → Synthesizer → Validator (replan ≤ 2, tasks/result 자동 리셋)
│                       · Send API 병렬 디스패치 · 세션 메모리 (thread별 TTL/LRU)
│                       · checkpoint (chat.checkpoints) · streaming (SSE / st.status)
│                       · tracing (Langfuse/LangSmith)
└─ API / UI           : FastAPI 5 엔드포인트 (`POST /chat` · `POST /chat/stream` (SSE) · `POST /chat/resume` (HITL 재개) · `GET /threads/{id}` (히스토리) · `GET /health` (PG/Neo4j ping)). Streamlit 채팅 (node progress · 👍/👎/📝). **인증 없음 — 외부 노출 시 reverse proxy + auth gateway 필요 (§11.1)**

[외부 의존성]
└─ LLM Provider : OpenAI / Anthropic / 로컬 (환경변수 전환)
```

상세는 [docs/operations/agents.md](./docs/operations/agents.md) 참조.

### 저장소 역할 분리 원칙

| 저장소 | 책임 | 예시 질의 |
|---|---|---|
| Neo4j | **관계·구조** | "현대차 자회사 중 매출 1조 이상은?" |
| PostgreSQL | **정확한 수치 + 메타** | "삼성전자 2023년 매출은?" |
| pgvector / Qdrant | **의미·서술** | "삼성전자의 주요 사업 위험 요인은?" |

> 재무 수치는 절대 LLM 이 생성하지 않는다 — 반드시 PostgreSQL 조회 결과만 사용.

---

## 4. 데이터 소스

모든 데이터는 공개·합법 출처만 사용 (무단 크롤링·약관 위반 금지). 라이선스별 본문 저장 정책은 `src/autonexusgraph/ingestion/_license.py` 가 코드 레벨에서 강제.

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
| KIPRIS 특허 | kipris.or.kr | 공공 | (키 확보 후) `ip.patents` |
| LAW.go.kr 법령 | open.law.go.kr | 공공 | (키 확보 후) `law.laws` |

**수집 범위 (1차):** 코스피 200 + 코스닥 100 약 300개사, 최근 3개 회계연도.
**범위 외 (Out-of-Scope):** 빅카인즈 본문, 나무위키(CC BY-NC-SA), 종목토론방, LinkedIn, Twitter.

### AutoGraph 데이터 소스

| 데이터 | 출처 | 라이선스 | 인증 | 적재 위치 |
|---|---|---|---|---|
| 차량 마스터·제원 (전 세계 vPIC) | NHTSA vPIC API | 공공 (US Gov) | 불필요 | `auto.master_*` |
| 리콜 캠페인 | NHTSA Recalls API | 공공 | 불필요 | `auto.events_recalls` + Neo4j Recall |
| 결함 신고 | NHTSA Complaints API | 공공 | 불필요 | `auto.events_complaints` + `vec.chunks` |
| 제조사·모델·공급사 QID·LEI·사업자번호 | Wikidata SPARQL | CC0 | 불필요 (rate limit) | `auto.master_*` + `bridge.corp_entity` |
| 자동차 리콜정보 (한국) | data.go.kr [15089863](https://www.data.go.kr/data/15089863/openapi.do) | 공공 | `DATA_GO_KR_API_KEY` | (키 확보 후) `auto.events_recalls` |
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
| 산단공 합성 공정데이터 (15151075) | data.go.kr (수동 CSV) | 공공 | 불필요 (파일) | `auto.master_processes` + Neo4j `:Process` 사전 (USES_PROCESS 적재 base) |
| 공장 등록정보 (15087611) — 회사·공장번호·산단별 조회 | data.go.kr 팩토리온 (`apis.data.go.kr/B550624`) | 공공 | `DATA_GO_KR_API_KEY` | (키 확보 후) `auto.factory_registry` → MANUFACTURED_AT 보강 |

> 인증 키 부재 시 ingestion 은 graceful skip — 코드 변경 없이 `.env` 만 채우면 활성화.

---

## 5. 에이전트 도구 (사전 정의 함수 풀)

자유 SQL/Cypher/벡터 호출은 금지. LLM 은 함수명 + 파라미터만 결정. SQL injection / 그래프 폭발 / 토큰 폭발 차단 (PRD §7.5.10).

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

---

## 6. 평가 전략

### 평가셋 구성
- 공개 벤치마크: Allganize RAG-Evaluation-Dataset-KO (금융)
- 자체 구축 Multi-hop QA — 도메인 내 100문항 + Cross-Domain 30문항
  - finance: `eval/qa_gold/gold_qa_v0.jsonl` — L1/L2/L3 — seed 30 (목표 100)
  - auto: `eval/qa_gold/gold_qa_auto_v0.jsonl` — L1/L2/L3 — seed 42 (목표 100)
  - cross: `eval/qa_gold/gold_qa_cross_v0.jsonl` — CD-L1 10 / CD-L2 8 / CD-L3 8 / CD-L4 4

### 비교 매트릭스
Vector only / Graph only / **Hybrid Agent** / SQL+Vector — 4종 × LLM 3종 = 12조합
+ Cross-Domain 은 Hybrid+Bridge 어댑터 단독 (다른 어댑터는 Bridge 미사용).

### 목표 지표

| 지표 | 목표 | 측정 도구 |
|---|---|---|
| Answer Accuracy (LLM-as-judge) | 85%+ | `eval/metrics/llm_judge.py` |
| Multi-hop 정답률 (2-hop+) | 75%+ | runner 의 `multi_hop_em/f1` subset |
| Hybrid vs Vector-only Multi-hop 격차 | +30%p | runner 의 `hybrid_vs_vector` (자동) |
| 재무 수치 Exact Match | 95%+ | `eval/metrics/em_f1.py` |
| Faithfulness (Ragas) | 90%+ | `eval/metrics/faithfulness.py` |
| 평균 latency 도메인내 / Cross | < 8초 / < 12초 | `eval/metrics/latency.py` |
| Bridge confidence ≥ 0.9 비율 | 80%+ | `eval/metrics/bridge_quality.py` |
| Main-Hop Efficiency (vector 대비) | −30%+ | `eval/metrics/main_hop_efficiency.py` |
| Confidence-Weighted Accuracy | (관찰 지표) | `eval/metrics/confidence_weighted.py` |

### DoD 자동 검증

```bash
make audit-bom-coverage   # PRD §10 DoD #5
make audit-edge-meta      # PRD §10 DoD #11
make validate-gold-qa     # qa_gold/*.jsonl lint
make eval-full            # finance 100문항
make eval-auto            # auto 100문항
make eval-cross           # CD-L1~L4 30문항
make audit-dod            # 14항 트래픽라이트 종합 리포트 → eval/reports/dod_v2.1.md
```

### 현재 측정 결과 (PRD §10 DoD 14 항, 2026-05-29 측정)

`make audit-dod` 의 최신 출력 — **5 측정 가능 모두 pass / 6 LLM 키 필요 대기 / 3 외부 측정 영역**.

| ID | 기준 | 상태 | 상세 |
|---|---|:---:|---|
| §10.4 | MVP 범위 OEM 5~8 × 모델 30~50 × 2022~2024 | ✅ | OEM=5 / models=102 / years=(2020, 2024) — 범위 over-spec |
| §10.5 | BOM L0~L3 안정 + L4 coverage ≥ 60% | ✅ | L0~L3 stable, L4=63.7% |
| §10.6 | bridge.corp_entity QID/LEI 강매칭 confidence ≥0.9 비율 80%+ | ✅ | strong_match 12/12 = 100% |
| §10.11 | SUPPLIED_BY 엣지 confidence/provenance/snapshot_year 100% | ✅ | 30 edges 100% meta |
| §10.12 | 코어 코드 변경 < 5% | ✅ | baseline `4049caf856` → 0/12,786 LOC = 0.00% (baseline 이동 시 재측정 필요 — §11.5) |
| §10.7 | Hybrid vs Vector Multi-hop +30%p | ⊘ | LLM 키 필요 — `make eval-auto` 실행 후 자동 측정 |
| §10.8 | Cross-Domain QA CD-L1~L4 | ⊘ | LLM 키 필요 |
| §10.9 | 제원 수치 EM 95%+ | ⊘ | LLM 키 필요 |
| §10.10 | Faithfulness 90%+ | ⊘ | LLM 키 필요 |
| §10.13 | 메인 홉 효율 −30% | ⊘ | 운영 trace 필요 — `eval/runners` 에서 latency·hop 수집 |
| §10.14 | latency 도메인내 <8s / Cross <12s | ⊘ | 운영 trace 필요 |
| §10.1~3 | docker compose / Streamlit toggle / LLM provider 전환 | · | 외부 측정 (docker / git / ENV) |

→ **남은 측정의 부족분은 §11 보완 개발 백로그 참조.**

---

## 7. 구현 상태

> PRD §10 의 DoD 14항 SSOT 는 `make audit-dod` 의 출력 (`eval/reports/`). 본 표는 코드·테스트에 직접 대응하는 사실만 담는다. "곧", "예정" 같은 표현은 쓰지 않는다.

### 구현된 sub-system

| 영역 | 핵심 산출물 |
|---|---|
| 인프라 | Docker Compose, Neo4j 5.18, PostgreSQL 16 (pgvector 내장), BGE-M3 1024d 자체 임베딩 |
| LLM 어댑터 | OpenAI / Anthropic / Google / local OpenAI-compatible 자동 dispatch (`llm/base.py::detect_provider`), FAST/SMART tier 단축 + 11 role override |
| 비용 가드 | 세션 hard limit (`LLM_SESSION_HARD_LIMIT_USD`) + 도메인별 turn budget (`config.turn_budget_for_domain`, ENV override) + 사전 추정 + auto-approve + JSONL 영속 로그 (`data/cost_log.jsonl`) |
| 데이터 파이프라인 (finance) | DART corp 마스터, XBRL 184K, filings 4.6K, vec.chunks 748K, Neo4j Company/Person/지배구조 — Wikidata/Wikipedia/GLEIF/SEC/뉴스/KCGS 보강, ER 마스터 (`master.entities` + `master.entity_map`) |
| 데이터 파이프라인 (auto) | NHTSA vPIC/Recalls/Complaints/SafetyRatings/Investigations/TSB, EPA fueleconomy, SEC EDGAR (글로벌 OEM XBRL), Wikidata mfr/model/supplier/P176, AI Hub, KOTSA 수리검사, NHTSA component taxonomy 자동 도출. `bridge.corp_entity` 4,806 (한국 OEM/부품사 corp_code + 글로벌 OEM sec_cik 9개) |
| 제조 / 공정 (auto) | DART 사업보고서 본문 파서 (LLM 0%) — 생산능력·가동률·공장명 자동 추출. 산단공 합성 공정데이터 → `:Process` 사전. 팩토리온 공장등록 (15087611) scaffold (`DATA_GO_KR_API_KEY` 대기) |
| 도구 (tools) | finance: `tools/financials,graph,retrieve.py` — 사전 정의 함수 풀. auto: `src/autograph/tools/{spec,graph,retrieve,bridge}.py`. 자유 SQL/Cypher 금지 |
| Cypher 템플릿 | finance 22 = 14 정적 + 5 `find_paths_{1..5}hops` + 3 `get_subgraph_d{1..3}` (`tools/cypher_templates.py`). auto 19 (`src/autograph/cypher_templates_auto.py`). type/range/regex 검증 + bool reject |
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
| gold QA seed | `gold_qa_v0.jsonl` finance 30 / `gold_qa_auto_v0.jsonl` auto 42 / `gold_qa_cross_v0.jsonl` CD 30 (CD-L1 10 / L2 8 / L3 8 / L4 4) |
| 외부 데이터 인터페이스 | data.go.kr (15089863/15155857), car.go.kr, KATRI (bigdata-tic), KNCAP 5 소스 ingestion + loader (graceful skip — 인증 키 부재 시 skip) |

### 미구현 / wired-but-disabled / 측정 대기

| 영역 | 상태 | 비고 |
|---|---|---|
| HITL `sensitive_decision` | wired-but-disabled | `InterruptKind` Literal 에 선언, payload builder 없음 (`agents/interrupts.py:27-31`) |
| P3 selective LLM 4 종 (COMPETES_WITH / MANUFACTURED_AT(LLM) / CONTAINS_MODULE / CONTAINS_PART) | wired-but-disabled | `ontology/auto/relations.yaml` 의 `enabled: false` (비용/환각 위험 — manual seed + Wikidata P176 우선) |
| 12 조합 매트릭스 실측 (4 어댑터 × 3 LLM) | 측정 대기 | `make eval-full / eval-auto / eval-cross` 실행 + gold seed 100/100/30 확장 후 |
| 공정위 기업집단 / KOSIS / KIPRIS / LAW.go.kr | 키 확보 대기 | Makefile 타겟·loader 는 있음 (`README §4`) |
| vec.chunks embedding backfill | 진행 중 | finance 748K 중 일부, auto 16,435 모두 완료 |
| bridge.corp_entity 부품사 corp_code 매핑 | 확장 대기 | 현재 한국 OEM/부품사 직접 매핑 소수 / 글로벌 OEM sec_cik 9개. supplier 4,792 candidate 검토 routine 미수행 |
| Cross-Domain QA 100문항 + 라벨 4단계 | 30 row seed 적재 | CD-L1 10 / L2 8 / L3 8 / L4 4 — 사람 라벨링 + 확장 대기 |
| confidence_score calibration | 미수행 | A/B/C 스칼라가 실제 정답률과 단조 관계인지 사후 검증 (`eval/metrics/confidence_weighted.py` 가 측정 도구) |
| Bridge candidate 검토 운영 | UI/프로세스 미설계 | 4,792 supplier candidate 의 reviewed_status 승급/거부 운영 SOP 미정 |
| KNCAP / Euro NCAP / IIHS | 인터페이스만 (KNCAP) / 미구현 | 공식 채널 약관 검토 후 |
| KATRI / bigdata-tic OAuth | wired | `BIGDATA_TIC_CLIENT_ID/SECRET` 발급 후 활성 |
| 팩토리온 (15087611) | scaffold | ingestion 3 endpoint (회사/공장번호/산단별) 구현, `DATA_GO_KR_API_KEY` 발급 후 활성 |
| 산단공 공정 (15151075) | wired | 수동 CSV 다운 후 `make load-sandang-processes` |
| `_legacy/v2/` | 보존 | 삭제 예정 미정 (`docs/mental_model.md §5.10`) |
| Integration test (`pytest -m integration`) | 마커 0건 | unit test 파일 수: root 48 + autograph 17 = 65. 실제 Neo4j/PG 통합은 `docs/autograph.md §7.5` 수동 절차. CI 컨테이너 미설정 |
| API 인증 / Rate limit | **미구현** | FastAPI 5 엔드포인트 모두 open. 외부 노출 시 reverse proxy + auth gateway 필요 — §11.1 |
| Production 배포 가이드 | 미작성 | Quickstart 는 dev 한정. 백업/DR/모니터링/multi-instance scaling 절차 없음 — §11.2 |
| `docs/design/` | 빈 디렉토리 | 디자인 doc 자리만 있고 내용 없음 (PRD / mental_model / learning_guide 가 대체) |
| `_legacy/` | 보존 (v1/v2 KGQA Agent) | 이전 단일도메인 시스템. CHANGELOG/HISTORY 보존. 삭제 vs 마이그레이션 정책 미정 |
| 모델 출력 reranker (BGE-Reranker-v2-m3) | 코드 wired (`RERANKER_URL=...`) | 실서비스에서 미활성. 활성 조건·임계 미정의 |
| USES_PROCESS / MADE_OF (L6) | wired (ontology 정의) | `:Process` 노드 사전 산단공 적재 / `:Material` 노드 미구현. 엣지 적재 routine 미구현 |
| DART 사업보고서 가동률 표 | 코드 TODO (`extractors/dart_production_parser.py:316`) | capacity 만 추출. 가동률은 컬럼 구성이 다양해 별도 경로 필요 |

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

영구 non-goal — 본 시스템이 다루지 않는다고 단정한 것:

- 실시간 주가 예측 / 매매 신호 생성
- 투자 자문 (정보 제공 한정)
- 비공개 OEM 내부 BOM / 비공개 부품번호
- 비공개 텔레매틱스 / 차량 OTA 데이터
- 차량 가격 예측 / 중고차 시세
- 자율주행 안전성 인증 대체 / 정비 매뉴얼 기반 DIY 가이드

MVP 비목표이지만 §10 장기 로드맵에서 다루는 것:

- 비상장사 / 사모펀드 / 글로벌 영문 기업 → §10.1 (3번째 도메인 + N-domain bridge)
- BOM Level 5 (Part) 대량 / Level 6 (Material·Process) → §10.2
- 공정·라인·설비·원가·생산량 → §10.2 (DART 사업보고서 파서 + 산단공 + 팩토리온 으로 부분 진입)
- 실시간 이벤트 처리 (분 단위) → §10.4
- ESG ↔ 제품 친환경성 결합 / 공급망 위험 분석 / 리콜 전파 분석 → §10.3

---

## 10. 최종 비전 / 장기 로드맵

본 시스템은 MVP (finance + auto, 한국 상장사 + NHTSA 5 OEM × 2020–2024) 검증이 끝나면 다음 4 축으로 확장. 각 항목은 **현재 상태 → 최종 형태 → 갭** 형태.

### 10.1 N-domain GraphRAG umbrella — 3번째·4번째 도메인 확장

| 단계 | 도메인 | 추가 데이터 소스 | Bridge 확장 |
|---|---|---|---|
| 현재 | finance (한국 상장사) + auto (자동차) | DART/KRX/ECOS/NHTSA/Wikidata | `bridge.corp_entity` (corp_code ↔ entity_id, sec_cik) |
| Phase C (다음) | + **의약품** (`pharmagraph`) | PMDA / FDA 라벨 / 임상 시험 / DUR / 보험 EDI | `bridge.corp_entity` + `bridge.drug_entity` (다형) |
| Phase D | + **전자제품 / 반도체** (`elecgraph`) | DRAM/Logic 로드맵 · IEC 표준 · GHS-RoHS · iFixit 분해 | `bridge.corp_entity` + 부품·소재 매핑 |
| Phase E | + **에너지·식품** (`energygraph` / `foodgraph`) | 한국전력 발전소 / 식약처 회수 | 다양한 도메인이 동일 corp_entity 로 join |

**왜 가능한가:** core 는 `_domain_handler.discover_plugins()` 가 ENV `AUTONEXUSGRAPH_DOMAIN_PLUGINS` (CSV) 의 모듈을 import 시점에 soft-load. 새 도메인은 `register_handler` 부작용 + `ontology/<domain>/*.yaml` + 사전 정의 도구 + Cypher 템플릿 + 화이트리스트 + gold QA seed 만 추가. **PRD §10.12 "코어 변경 < 5%" 가 강제** (`scripts/audit/dod_audit.py` baseline 비교). 자동차 추가 시 4.47% 측정값 (`docs/mental_model.md §5.1`).

**열린 질문 / 갭:**
- 코어와 finance 어댑터의 분리 (`docs/mental_model.md §3.1.4`) — pure core / fingraph / autograph / pharmagraph 3+ 분할이 필요한지, 현재 2-pkg 가 영구 설계인지 미정
- N-domain bridge 의 매칭 우선순위 — `wikidata_qid > LEI > 사업자번호 > name` 외에 도메인별 식별자 (DUNS / CIK / ISIN / NDC / ATC …) 우선순위 sequence

### 10.2 BOM Level 5 (Part) + Level 6 (Material·Process) — 깊이 확장

| Level | 현재 | 최종 형태 | 갭 |
|---|---|---|---|
| L0~L2 | NHTSA vPIC + Wikidata 로 100% deterministic | 글로벌 OEM 20사 × 모델 300종 × 2020~ | 한국 시장 트림은 KOTSA / data.go.kr 키 발급 후 |
| L3 (System) | `system_taxonomy.yaml` 19 시스템 SSOT | 동일 — 표준 분류이므로 확장 없음 | (해당 없음) |
| L4 (Module) | NHTSA component taxonomy 176 + AI Hub + manual seed = 220 | OEM 별 베스트셀러 모델 ≥ 90% module coverage | 부품사 IR cross-reference (현대모비스/한온/만도 …) 미수집 |
| **L5 (Part)** | post-MVP — 리콜 텍스트 LLM 추출 → RECALL_OF 자연 발생만 | OEM 별 BOM "주요 부품 30~50종" coverage, Part ↔ Supplier 시점별 매핑 | 데이터 본질 부재 (`docs/mental_model.md §5.4`) — (a) 공개 채널 자체가 sparse, (b) 부품사 IR 라이선스/정확도, (c) Part 정체성 정의 (같은 부품번호가 OEM 별로 다름) |
| **L6 (Material·Process)** | PRD non-goal | 배터리 셀 NCM 조성 / 알루미늄 합금 / 다이캐스팅 같은 공법 ontology + (:Module)-[:MADE_OF]->(:Material) / [:USES_PROCESS]->(:Process) | 산단공 합성 공정데이터 (15151075) 가 :Process 사전을 채우고 있음 — :Material 은 미구현 |

**현재 작업 중인 것:**
- DART 사업보고서 본문 파서 — 한국 OEM/부품사의 생산능력·가동률·공장명을 LLM 0% 정규식 + 표 파서로 추출 (가장 최근 커밋 `215f7e5`)
- 산단공 합성 공정데이터 — `:Process` 사전 적재 (Casting / Forging / Stamping / Welding / Coating …)
- 팩토리온 (15087611) scaffold — DATA_GO_KR_API_KEY 발급 후 회사·공장번호·산단별 등록 공장 조회 → `MANUFACTURED_AT` 보강
- Wikidata P176 (manufactured by) — 부품↔공급사 staging 후 P4 cross-validate → Neo4j SUPPLIED_BY 승급

### 10.3 추론 가치 확장 — 공급망 위험 · 리콜 전파 · ESG 결합

본 시스템의 **궁극 가치**는 단순 Q&A 가 아니라 다음 cross-domain 추론:

1. **공급망 위험 분석** — Bridge 로 공급사 집중도 (단일 supplier 다중 OEM 사용 빈도) + AutoNexusGraph 재무·신용도 결합. 예: "삼성SDI 가 공급하는 OEM 의 매출 합계 + 삼성SDI 부채비율 + 최근 6개월 리콜 빈도".
2. **리콜 전파 분석** — 동일 부품 사용 차종 자동 영향 평가. 예: "이 BMS 리콜이 다른 OEM 의 어느 모델·연식까지 적용 가능한가". (`get_vehicles_using_component` + `find_vehicle_component_paths` + snapshot_year 시점 필터)
3. **ESG ↔ 제품 친환경성 결합** — KCGS ESG 등급 (finance) + EPA fueleconomy MPG·배출등급 (auto) + 배터리 셀 조성 (L6) → "ESG B+ 이상 OEM 의 평균 GHG score 와 EV/HEV 비율".
4. **시점 정합 cross-domain** — "2023년 LG에너지솔루션 배터리를 쓰는 OEM 의 KCGS ESG 등급" — Bridge·SUPPLIED_BY·ESG ratings 모두에 `snapshot_year` / `valid_from/to` 정합 필요.

**현재 갭:**
- 모든 엣지에 `snapshot_year` 강제는 완료. 하지만 시점 정합 cross-domain QA 의 ground truth 정의가 모호 (`docs/mental_model.md §5.8`) — 분기별 공급 비율 변동 시 어느 시점을 "정답" 으로?
- Bridge candidate 4,792 supplier 의 검토 운영 SOP 미정 — graph quality 가 시간 갈수록 떨어질 수 있음
- 리콜 전파 분석은 모델·연식 cross-product 가 쉽게 폭발 — Planner 가 "메인 홉 우선 traversal" 휴리스틱 미구현

### 10.4 운영·평가·신뢰성 — Enterprise 수준 도달

| 영역 | 현재 | 최종 |
|---|---|---|
| 평가 매트릭스 | 4 어댑터 × 3 LLM = 12 조합 인프라 완성, 실측 대기 | 12 조합 풀 실측 + Confidence-Weighted Accuracy calibration + Vector RAG 비교 공정성 검증 (외부 큐레이터 gold QA 도입) |
| Gold QA | finance 30 / auto 42 / cross 30 row seed | finance 100 / auto 100 / cross 100 — CD-L1~L4 라벨 + 사람 검증 |
| Cross-Domain 목표 정답률 | (미실측) | CD-L1 80%+ / L2 70%+ / L3 50–60% / L4 40–50% (PRD §2.2) |
| Bridge 품질 | confidence ≥ 0.9 비율 측정 인프라 (`eval/metrics/bridge_quality.py`) | confidence ≥ 0.9 비율 80%+ + 검토 SOP + 자동 만료 정책 (예: 6개월 미검토 candidate → 자동 rejected) |
| HITL | clarification + cost approval 활성 | `sensitive_decision` (대출/투자/계약 관련 high-stakes 결정 시 사람 승인) + 답변 후 explicit feedback 루프 |
| Tracing | Langfuse / LangSmith fail-soft | 모든 turn 의 노드별 token + cost + replan 횟수 + tool 호출 로그를 dashboard 로 분석 — replan ROI 정량화 |
| Streaming | SSE 노드 progress | 그래프 시각화 (pyvis) + 답변 근거 chunk hover preview |
| Integration test | 마커 0건 (실제 DB 가 필요한 수동 절차) | `pytest -m integration` 50+ 케이스 + CI 에 Neo4j/PG 서비스 컨테이너 + nightly run |
| Embedding 모델 | BGE-M3 1024d 자체 호스팅 | BGE-M3 + multilingual fine-tune (자동차·금융 도메인 코퍼스 LoRA) + 청크 100만 넘으면 Qdrant 분리 (현재 765K) |
| LLM 비용 | session HARD_LIMIT + turn budget + auto-approve | cost_estimator ±20% 정확도 검증 + 사용자별 quota + budget guard 발동 시 UX 완화 (부분 답변 + "예산 초과 — 추가 승인?") |

### 10.5 우선순위 권장 (다음 한 분기)

1. **데이터 채널 확장 (즉시 가능, 키 무관)** — EPA Annual Certification (Tier 3) / NHTSA TSB / DBpedia P527 / SEC EDGAR 글로벌 OEM 5사 더 추가 (`docs/data_sources.md §11`)
2. **gold QA 100/100/100 확장** — CD-L1~L4 라벨 + 외부 큐레이터 30%
3. **12 조합 매트릭스 실측** — `make eval-full / eval-auto / eval-cross` 풀 실행 + Confidence-Weighted Accuracy calibration
4. **부품사 IR cross-reference** — DART finance 측에 이미 있는 현대모비스/만도/한온시스템 사업보고서를 auto 도메인 BOM Level 4~5 보강에 활용 (Bridge 흐름의 reverse — finance → auto)
5. **3번째 도메인 PoC** — `pharmagraph` skeleton (DomainHandler 6 메서드 + ontology yaml 만 + gold QA 10 row) 으로 N-domain 확장성 정량 검증

---

## 11. 문서

- [PRD.md](./PRD.md) — 요구사항·아키텍처 SSOT (AutoGraph v2.1 통합)
- [docs/mental_model.md](./docs/mental_model.md) — **결정 카탈로그** — 모든 설계 결정의 [확정]/[잠정]/[미정] 라벨, 트레이드오프 박스, 열린 질문 리스트
- [docs/learning_guide.md](./docs/learning_guide.md) — **시스템 심화 가이드** — 문제 정의·이론적 기초·아키텍처 (StateGraph 11 노드 / AgentState 33 필드 / 4 가드 / cost 3 tier)·추론 흐름 깊이·예상 질문 (세미나 수준 발표용)
- [docs/autograph.md](./docs/autograph.md) — **AutoGraph (auto 도메인) 단독** 가이드 (구조 / 데이터 흐름 / 실행 순서 / 알려진 제약)
- [docs/data_sources.md](./docs/data_sources.md) — 데이터 소스 후보 카탈로그 + 라이선스 + 인증 키
- [docs/data_inventory.md](./docs/data_inventory.md) — 적재 현황 측정 (재실행 시 갱신, `make audit-data-channels`)
- [docs/data_catalog.md](./docs/data_catalog.md) — **구현된 채널 운영 가이드** (출처·등급·ingestion·loader·tool·한계 표준 9 항목 형식)
- [docs/operations/docker_setup.md](./docs/operations/docker_setup.md) — Docker 스택 가이드
- [docs/operations/data_pipeline.md](./docs/operations/data_pipeline.md) — 멱등 파이프라인 + Step DAG + P1~P4 추출 + LangGraph 활성화
- [docs/operations/agents.md](./docs/operations/agents.md) — 에이전트 운영 (도메인 라우팅 / LangGraph / replan / checkpoint / tracing / safety 가드)
- [docs/operations/rag_tools.md](./docs/operations/rag_tools.md) — 도구 카탈로그 + 시나리오
- [docs/operations/migrations.md](./docs/operations/migrations.md) — 스키마 마이그레이션 절차
- [docs/operations/kcgs_esg_guide.md](./docs/operations/kcgs_esg_guide.md) — KCGS ESG 등급 수집 가이드
- [eval/qa_gold/README.md](./eval/qa_gold/README.md) — 평가 gold set 스키마 + 큐레이션 가이드

---

## 12. Quickstart

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

# 11. LangGraph 활성화 (PRD §7.5.8 — PG checkpoint + tracing)
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
# infra/postgres/init/ 의 07~16 sql 이 멱등이라 hot-apply 가능 (docs/operations/migrations.md).
make migrate-schema-pg MIGRATE_FILE=07_autograph.sql
make migrate-schema-pg MIGRATE_FILE=08_bridge.sql
make migrate-schema-pg MIGRATE_FILE=09_vec_chunks_auto_meta.sql
make migrate-schema-pg MIGRATE_FILE=10_autograph_bom.sql
make migrate-schema-pg MIGRATE_FILE=11_autograph_staging.sql
make migrate-schema-pg MIGRATE_FILE=12_autograph_inspections.sql
make migrate-schema-pg MIGRATE_FILE=12_autograph_investigations.sql
make migrate-schema-pg MIGRATE_FILE=13_autograph_oem_sec.sql
make migrate-schema-pg MIGRATE_FILE=14_master_entities.sql
make migrate-auto-production         # 15_autograph_production.sql (DART 사업보고서 파서)
make migrate-auto-kama               # 16_autograph_kama_macro.sql
python -m autograph.loaders.neo4j_init    # CONSTRAINT/INDEX 멱등 — ontology/auto/entities.yaml SSOT

# 1. 인제스션 (.env 의 AUTO_INGEST_MAKES / AUTO_INGEST_YEAR_MIN/MAX 기반)
make ingest-auto-all                # = vpic + recalls + complaints + safety + wikipedia + epa + investigations + sec-oem
# 한국 시장 / KATRI / KNCAP (graceful skip — 키 없으면 0 byte)
make ingest-datagokr-recalls        # data.go.kr 15089863 (DATA_GO_KR_API_KEY 필요)
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
make eval-cross                      # CD-L1~L4 30문항 (PRD §8.1)

# 8. DoD 트래픽라이트 (PRD §10 14 항)
make audit-bom-coverage
make audit-edge-meta
make audit-dod                       # 14 항 종합 — eval/reports/dod_v2.1.md
```

자세한 절차·미구현 영역·회귀 안전성은 [docs/autograph.md](./docs/autograph.md). 도메인 라우팅 흐름은 [docs/operations/agents.md](./docs/operations/agents.md#도메인-라우팅-finance--auto--cross_domain).

---

## 13. 라이선스

내부 연구·개발 단계. 라이선스 미정.

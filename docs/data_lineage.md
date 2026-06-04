# Data Lineage — 채널별 end-to-end 추적 SSOT

> **본 문서의 위치**: 각 데이터 채널의 **raw URL → ingestion → PG/Neo4j 적재 → 7키 메타 → tool → 답변 시나리오 → 알려진 한계** 의 1 페이지 추적. 신규 합류자 / 외부 평가자 / 본인 회고가 한 채널을 이해할 때 다른 문서 점프 없이 끝낼 수 있도록.
>
> [docs/data_sources.md](data_sources.md) (수집 후보 카탈로그) + [docs/data_inventory.md](data_inventory.md) (실측 row 수) + [docs/autograph.md](autograph.md) + [docs/ipgraph.md](ipgraph.md) 의 정보를 **채널 단위로 통합**. (2026-06-02 — 기존 `data_catalog.md` 흡수 후 폐기 — 9 항목 운영 가이드 + raw 보존 정책 + 트래픽라이트 + 더 필요한 데이터 P0~P2 모두 본 문서 §1~§5.4 흡수.)
>
> 분량은 채널 수만큼 길어지지만, 사용자는 본인 관심 채널 한 개만 읽어도 됨.

---

## 0. 인덱스

3 도메인 × 채널 일람 (실측 기준 적재 완료 채널만 — 미적재는 [data_sources.md](data_sources.md) 참조):

### Finance 도메인 (9 채널)
- [§1.1 DART Open API — corp 마스터 + 사업보고서 + XBRL 재무](#11-dart-open-api)
- [§1.2 KRX 상장사 마스터](#12-krx-상장사-마스터)
- [§1.3 Wikidata SPARQL — QID/LEI/CIK 매핑](#13-wikidata-sparql)
- [§1.4 Wikipedia 본문·Infobox (한국어)](#14-wikipedia)
- [§1.5 SEC EDGAR (한국 ADR + 글로벌 OEM)](#15-sec-edgar)
- [§1.6 GLEIF LEI](#16-gleif-lei)
- [§1.7 연합뉴스 RSS](#17-연합뉴스-rss)
- [§1.8 KCGS ESG 등급](#18-kcgs-esg)
- [§1.9 ECOS 거시지표](#19-ecos)

### Auto 도메인 (16 채널)
- [§2.1 NHTSA vPIC — 차량 마스터](#21-nhtsa-vpic)
- [§2.2 NHTSA Recalls](#22-nhtsa-recalls)
- [§2.3 NHTSA Complaints](#23-nhtsa-complaints)
- [§2.4 NHTSA Investigations (ODI)](#24-nhtsa-investigations)
- [§2.5 NHTSA SafetyRatings (NCAP)](#25-nhtsa-safetyratings)
- [§2.6 EPA fueleconomy](#26-epa-fueleconomy)
- [§2.7 Wikidata mfr/model/supplier (P176)](#27-wikidata-auto)
- [§2.8 AI Hub 부품 결함](#28-ai-hub)
- [§2.9 KOTSA 수리검사](#29-kotsa-수리검사)
- [§2.10 DART 사업보고서 (제조)](#210-dart-사업보고서-제조)
- [§2.11 KAMA 매크로](#211-kama-매크로)
- [§2.12 USGS MCS (핵심광물)](#212-usgs-mcs)
- [§2.13 OEM IR / 뉴스룸](#213-oem-ir-뉴스룸)
- [§2.14 KAMP 제조AI 데이터셋 카탈로그 ✅](#214-kamp-카탈로그)
- [§2.15 NASA PCoE (Bearing/Battery/IGBT) ✅](#215-nasa-pcoe)
- [§2.16 EU Safety Gate (RAPEX) ✅](#216-eu-safety-gate)

### IP 도메인 (4 채널)
- [§3.1 CPC scheme bulk ✅](#31-cpc-scheme)
- [§3.2 OpenAlex (논문) ✅](#32-openalex)
- [§3.3 USPTO Open Data Portal (예정)](#33-uspto-odp)
- [§3.4 KIPRIS (예정)](#34-kipris)

### Bridge / Cross-Domain (2 채널)
- [§4.1 bridge.corp_entity (manufacturer + supplier 통합)](#41-bridge-corp-entity)
- [§4.2 Layer1 Bridge — DEFECT_MATCHES + MANIFESTS_AS + SUBJECT_TO ✅](#42-layer1-bridge)

---

## 1. Finance 도메인

### 1.1 DART Open API

| 항목 | 내용 |
|---|---|
| **출처 URL** | `https://opendart.fss.or.kr/api/*` |
| **인증** | `DART_API_KEY` (무료, 회원 가입 후) |
| **라이선스** | 공공 (public_domain) — `_license.py:LICENSE_POLICY['dart']` |
| **수집 의도** | 한국 상장사 corp_code 마스터 + 사업보고서 본문 + XBRL 재무 — finance 도메인의 backbone |
| **Ingestion 코드** | HTTP 클라이언트 모듈 `src/autonexusgraph/ingestion/dart_client.py` + 실행 스크립트 `scripts/ingest/{download_corp_codes,bulk_dart,bulk_dart_structural,download_business_reports,download_financials}.py` (5 스크립트) |
| **Loader 코드** | `src/autonexusgraph/loaders/load_companies.py` + `load_filings.py` + `load_financials.py` + `load_graph_structural.py` |
| **raw 저장** | `data/raw/dart/{corp_codes, filings, financials, structural}/` |
| **PG 테이블** | `master.companies` (295 row) / `fin.filings` (4,584 row) / `fin.financials` (184,199 row XBRL) |
| **Neo4j 노드·엣지** | `:Company` (12,914) / `:Person` (14,536) / `SUBSIDIARY_OF` (8,661) / `EXECUTIVE_OF` (33,064) / `MAJOR_SHAREHOLDER_OF` (12,548) |
| **vec.chunks** | `section='dart_business'` / `'dart_audit'` 등 — `corp_code` + `fiscal_year` 메타 |
| **7키 메타** | `source_type='dart_xbrl' / 'dart_business_report'`, `source_id=rcept_no`, `extraction_method='deterministic'` (P1), `confidence_score=0.95` (A 등급), `validated_status='validated'`, `snapshot_year=fiscal_year`, `schema_version="v2.2"` |
| **추출 Pass** | P1 (deterministic, LLM 0%) — XBRL 직매핑. P2 (deterministic) — 정형 지배구조 |
| **Tool 진입점** | `tools/financials.py`: `lookup_company / get_revenue / get_operating_income / get_balance_sheet_item / compare_companies`. `tools/graph.py`: `list_subsidiaries / get_executives / get_major_shareholders` |
| **답변 시나리오** | "삼성전자 2023년 매출은?" → `lookup_company('삼성전자')` → corp_code=00126380 → `get_revenue('00126380', 2023)` → PG fin.financials 조회 → **6.5분 latency 추정** (README §10.14 미실측) |
| **알려진 한계** | (a) **재무제표 IFRS 별도/연결 혼동** — 같은 회사 동일 항목이 보고 기준에 따라 다른 값. gold QA 에서 명시 필요. (b) 분기·반기 보고서는 fiscal_year 가 아닌 보고 시점 기준 — 적재 시 정규화 필요. (c) **사업보고서 본문 P3 LLM 추출** (COMPETES_WITH 등) 은 wired-but-disabled (`ontology/relations.yaml:226`) — 비용/환각 위험 |

---

### 1.2 KRX 상장사 마스터

| 항목 | 내용 |
|---|---|
| **출처** | KRX 상장사 정보 (수동 CSV 다운로드 또는 공공 API) |
| **인증** | 불필요 |
| **라이선스** | 공공 |
| **수집 의도** | 종목코드 ↔ corp_code 매핑 + market (KOSPI/KOSDAQ) 분류 |
| **Ingestion·Loader** | `src/autonexusgraph/ingestion/krx_client.py` + `scripts/ingest/download_listings.py` + `loaders/load_companies.py` (DART 와 통합) |
| **raw 저장** | `data/raw/krx/{top_kospi200.csv, top_kosdaq100.csv}` |
| **PG 테이블** | `master.companies` (DART 와 통합) / `master.entity_map` (id_type='stock_code') |
| **Tool** | `lookup_company` (종목코드 입력 가능) / `list_companies_by_market('KOSPI200')` |
| **답변 시나리오** | "코스피200 중 매출 1조 이상 회사" → `list_companies_by_market` → 각 corp_code 별 `get_revenue` |
| **알려진 한계** | KRX 데이터 수기 업데이트 — 분기 갱신 routine 미구현 (`docs/data_inventory.md §3 B11` 추적) |

---

### 1.3 Wikidata SPARQL

| 항목 | 내용 |
|---|---|
| **출처** | `https://query.wikidata.org/sparql` |
| **인증** | 불필요 (rate-limit 1 req/min, 429 응답) |
| **라이선스** | CC0 — `_license.py['wikidata']` |
| **수집 의도** | 한국 상장사 → Wikidata QID + 외부 ID (LEI/CIK/ISIN/homepage) 매핑 → entity_map 보강 |
| **Ingestion** | HTTP 클라이언트 `src/autonexusgraph/ingestion/wikidata_client.py` (RateLimiter + CheckpointStore) + 실행 스크립트 `scripts/ingest/download_wikidata.py` |
| **Loader** | `loaders/load_wikidata.py` |
| **raw 저장** | `data/raw/wikidata/{candidates.json, entities/<qid>.json}` |
| **PG 테이블** | `wiki.wikidata_facts` (466 row) / `master.entity_map` 보강 (QID/LEI/CIK/ISIN 등) |
| **7키 메타** | `confidence_score=0.80` (B 등급) |
| **Tool** | `lookup_company` 반환에 wikidata_qid 포함 |
| **답변 시나리오** | "삼성전자 영문명·홈페이지" → `lookup_company` 결과의 wikidata 보강 필드 |
| **알려진 한계** | **rate-limit 매우 엄격** (1 req/min) — 대량 수집 시 수 시간. Wikidata 매핑 커버리지 55.6% (전체 295 중 ~164) |

---

### 1.4 Wikipedia

| 항목 | 내용 |
|---|---|
| **출처** | `https://ko.wikipedia.org/wiki/<Title>` |
| **라이선스** | CC BY-SA — 본문 저장 OK (출처 표기) |
| **수집 의도** | 회사 narrative 검색 (사업 설명·역사 등) — vector RAG 원료 |
| **Ingestion·Loader** | `src/autonexusgraph/ingestion/wikipedia_client.py` + `scripts/ingest/download_wikipedia.py` + `loaders/load_wikipedia.py` + `build_wiki_chunks` |
| **raw 저장** | `data/raw/wikipedia/ko/<corp_code>/{meta.json, page.html, summary.json, infobox.json}` |
| **PG 테이블** | `wiki.wikipedia_pages` (276 row, 93.6% 매핑) |
| **vec.chunks** | `section='wikipedia_ko'` + `corp_code` 메타 |
| **Tool** | `search_documents(query, section='wikipedia_ko')` |
| **답변 시나리오** | "삼성전자의 주요 사업은?" → `search_documents` → top-5 chunk → LLM 합성 |
| **알려진 한계** | 본문 갱신 routine 없음 — Wikipedia 가 갱신돼도 본 시스템 stale. 분기별 재수집 권장 (미실행) |

---

### 1.5 SEC EDGAR

| 항목 | 내용 |
|---|---|
| **출처** | `https://www.sec.gov/cgi-bin/browse-edgar` |
| **인증** | User-Agent 필수 |
| **라이선스** | 공공 (US Gov) |
| **수집 의도** | (a) 한국 ADR (Korea ADRs) CIK 매핑 → entity_map 보강, (b) **글로벌 OEM (Tesla/Ford/GM/Stellantis/Toyota/Honda) XBRL** → auto 도메인 cross-domain |
| **Ingestion** | `src/autonexusgraph/ingestion/sec_client.py` + `scripts/ingest/download_sec_edgar.py` (한국 ADR) + `src/autograph/ingestion/sec_oem.py` (글로벌 OEM) |
| **Loader** | `loaders/load_sec.py` + `autograph/loaders/load_oem_sec.py` |
| **PG 테이블** | `sec.filings` (1,857 row) / `auto.oem_financials_sec` (3,199 row) |
| **bridge 영향** | `bridge.corp_entity.sec_cik` 9 매핑 (한국 OEM CIK 부재 시 글로벌 OEM 진입점) |
| **Tool** | `bridge_sec_cik_to_entity('0001318605')` → Tesla manufacturer entity_id |
| **답변 시나리오** | "Tesla 2024년 영업이익" → `bridge_sec_cik_to_entity` → entity → `get_oem_financials_sec` |
| **알려진 한계** | XBRL 태그 표준 다양 (us-gaap / ifrs-full) — 항목 매핑 수동. SEC API rate-limit 10 req/sec |

---

### 1.6 GLEIF LEI

| 항목 | 내용 |
|---|---|
| **출처** | `https://api.gleif.org/api/v1/` |
| **라이선스** | CC BY 4.0 |
| **수집 의도** | 한국 jurisdiction LEI ↔ business_no/jurir_no/corp_code 매핑 |
| **Ingestion·Loader** | `src/autonexusgraph/ingestion/{gleif_client,gleif_enrich}.py` + `scripts/ingest/download_gleif.py` + `loaders/load_gleif.py` |
| **PG** | `sec.lei` (2,704 row, registeredAs 통한 corp_code 매핑 128) / `master.entity_map` 보강 |
| **bridge 영향** | `bridge.corp_entity.lei` 5+ row (supplier strong-match) |
| **Tool** | `lookup_company` 반환 LEI 포함 |
| **알려진 한계** | GLEIF 의 한국 회사 registeredAs 필드가 business_no/jurir_no 혼재 — `registeredAs` 정규화 routine 적용 (`load_gleif.py` 의 매칭 로직) |

---

### 1.7 연합뉴스 RSS

| 항목 | 내용 |
|---|---|
| **출처** | 연합뉴스 RSS (3 feed) |
| **라이선스** | **copyrighted** — `_license.py['news_yonhap']` — **제목 + 요약 + URL 만 저장**, 본문 X |
| **수집 의도** | 뉴스 멘션 그래프 (`MENTIONS`, `CO_MENTIONED_WITH`) |
| **Ingestion·Loader** | `src/autonexusgraph/ingestion/news_client.py` + `scripts/ingest/download_news_rss.py` + `loaders/load_news.py` + `load_graph_news.py` |
| **PG** | `news.articles` (338 row) / 멘션 (141 row) |
| **Neo4j** | `:NewsEvent` (85) / `MENTIONS` |
| **Tool** | `list_mentioning_news(corp_code)` / `list_cooccurring(corp_code)` |
| **알려진 한계** | RSS 만 — 본문 X. **저작권 정책 강제**. 본문 검색 불가 → vector RAG 무효. 멘션 빈도만 활용 |

---

### 1.8 KCGS ESG

| 항목 | 내용 |
|---|---|
| **출처** | https://www.cgs.or.kr (수동 CSV 다운) |
| **라이선스** | 회원 한정 — 수동 다운로드 |
| **수집 의도** | ESG 등급 (A+/A/B+/B/C/D) → ESG-finance cross 분석 |
| **Loader** | `loaders/load_kcgs.py` |
| **PG** | `esg.ratings` |
| **답변 시나리오** | "ESG B+ 이상 코스피200 회사" → SQL filter |
| **알려진 한계** | 연 1회 발표 (분기 갱신 X). 비회원은 보도자료 모니터로만 추적 (`ingest-kcgs`) |

---

### 1.9 ECOS (한국은행)

| 항목 | 내용 |
|---|---|
| **출처** | 한국은행 ECOS Open API |
| **인증** | `ECOS_API_KEY` |
| **수집 의도** | 거시지표 (GDP / 환율 / 금리) — 답변 컨텍스트 보강 |
| **PG** | `macro.series` |
| **현재 상태** | 키 발급 후 적재 — 본 보고 시점 미확인 |

---

## 2. Auto 도메인

### 2.1 NHTSA vPIC

| 항목 | 내용 |
|---|---|
| **출처 URL** | `https://vpic.nhtsa.dot.gov/api/vehicles/` |
| **인증** | 불필요 |
| **라이선스** | 공공 (US Gov) — `_license.py['nhtsa_vpic']` |
| **수집 의도** | 차량 마스터 (manufacturer / model / variant) — BOM Level 0~2 |
| **Ingestion** | `src/autograph/ingestion/nhtsa_vpic.py` (RateLimiter) |
| **Loader** | `src/autograph/loaders/load_auto_pg.py` + `load_auto_neo4j.py` |
| **raw** | `data/raw/auto/nhtsa/vpic/` |
| **PG** | `auto.master_manufacturers` (22,145) / `master_vehicle_models` (6,770) / `master_vehicle_variants` (428) |
| **Neo4j** | `:Manufacturer` 22,145 / `:VehicleModel` 6,770 / `:VehicleVariant` 428 / `MANUFACTURES` / `HAS_VARIANT` |
| **7키** | `source_type='nhtsa_vpic'`, `confidence_score=0.95` (A) |
| **Tool** | `lookup_vehicle / get_vehicle_info` |
| **답변 시나리오** | "Hyundai Sonata 2024 trim 종류" → `lookup_vehicle` → variant 목록 |
| **알려진 한계** | (a) **글로벌 OEM 만** — 한국 내수 전용 모델 부재. (b) variant 데이터는 5 OEM × 2020-2024 만 (428 row). KGM/르노코리아는 data.go.kr 키 발급 후 추가 예정 |

---

### 2.2 NHTSA Recalls

| 항목 | 내용 |
|---|---|
| **출처** | `https://www.nhtsa.gov/recalls` API |
| **수집 의도** | 리콜 캠페인 (campaign_id 영구) |
| **PG** | `auto.events_recalls` (493 row, manufacturer 매핑 100%, model·variant 매핑 92%) |
| **Neo4j** | `:Recall` 493 / `AFFECTED_BY` (Variant → Recall) / `RECALL_OF` 601 (Recall → Component, NHTSA taxonomy 후 100% 매칭) |
| **7키** | `source_id=nhtsa_campaign_id`, `confidence_score=0.95` |
| **Tool** | `list_recalls_affecting(variant_id)` / `get_recall_info(campaign_id)` |
| **답변 시나리오** | "Hyundai Sonata 2024 리콜" → `lookup_vehicle` → variant_id → `list_recalls_affecting` |
| **알려진 한계** | 미국 시장 한정 — KR-only 리콜 (car.go.kr) 은 수동 CSV 모드 (`docs/operations/data_pipeline.md §수동 자료`) |

---

### 2.3 NHTSA Complaints

| 항목 | 내용 |
|---|---|
| **출처** | NHTSA Complaints API |
| **PG** | `auto.events_complaints` (16,005 row, mfr 100% / model·variant 97%) |
| **Neo4j** | `:Complaint` 16,005 / `REPORTED_IN` |
| **vec.chunks** | `section='nhtsa_complaint'` + variant_id 메타 — **결함 신고 본문 vector 검색** |
| **Tool** | `search_documents_auto(query, source='nhtsa_complaint', variant_id=...)` |
| **답변 시나리오** | "Sonata DN8 결함 신고 패턴" → vector 검색 → 자주 언급된 증상 추출 |
| **알려진 한계** | 본문이 영문 (NHTSA 원문) — 한국어 질문 → 영문 임베딩 검색 성능 (cross-lingual). BGE-M3 multi-lingual 가 일부 완화 |

---

### 2.4 NHTSA Investigations (ODI)

| 항목 | 내용 |
|---|---|
| **출처** | NHTSA Investigations bulk |
| **PG** | `auto.events_investigations` 154 row (PE 89 / EA 32 / DP 14 / RQ 11 / AQ 3) |
| **Neo4j** | `:Investigation` / `INVESTIGATED_BY` |
| **수집 의도** | 리콜 **전단계** 결함 조사 — 리콜 예측 / 트렌드 분석 |
| **Tool** | `list_investigations_affecting(variant_id)` / `get_investigation_recall_chain(investigation_id)` |
| **답변 시나리오** | "Tesla Model Y ADAS 조사 → 리콜 chain" → `get_investigation_recall_chain` |

---

### 2.5 NHTSA SafetyRatings (NCAP)

| 항목 | 내용 |
|---|---|
| **출처** | NHTSA SafetyRatings API v2 |
| **PG** | `auto.spec_measurements` (NCAP 1,680 row) |
| **Neo4j** | `(:VehicleVariant)-[:SAFETY_RATED_BY]->(:Standard {code:'NCAP_US'})` |
| **Tool** | `get_safety_rating(variant_id, agency='NCAP_US')` |
| **답변 시나리오** | "Sonata 2024 NCAP 등급" → 5-star rating + frontal/side/rollover |
| **알려진 한계** | KNCAP / Euro NCAP / IIHS 미통합 — 한국·유럽 등급 부재 (`docs/data_sources.md §10`) |

---

### 2.6 EPA fueleconomy

| 항목 | 내용 |
|---|---|
| **출처** | EPA fueleconomy.gov bulk CSV |
| **PG** | `auto.spec_measurements` (EPA 1,426 row — MPG / 배출 / 엔진 spec) |
| **Tool** | `get_spec(variant_id, metric='fuel_economy')` |

---

### 2.7 Wikidata mfr/model/supplier (P176)

| 항목 | 내용 |
|---|---|
| **출처** | Wikidata SPARQL |
| **수집 의도** | 글로벌 manufacturer/model/supplier QID 매핑 + **P176 (manufactured by)** 부품↔공급사 자동 추출 |
| **PG** | `auto.master_*` Wikidata 보강 / `auto.staging_relations` (P176 후보) — **0 row** |
| **Tool** | `lookup_vehicle` 의 QID 보강 |
| **알려진 한계** | **🔴 Wikidata P176 rate-limit (1 req/min, 429) 로 `auto.staging_relations` 0 row**. 자동 공급망 추출 사실상 미작동. 우회: `supplier_seed.yaml` manual 19 공급사 × 46 매핑 → Neo4j `SUPPLIED_BY` 30 distinct edges (customer 다중 dedupe). `docs/data_inventory.md §3 B7` |

---

### 2.8 AI Hub 부품 결함

| 항목 | 내용 |
|---|---|
| **출처** | https://aihub.or.kr (회원 가입 + 다운로드 승인 필요) |
| **라이선스** | 공공 (회원·승인) |
| **수집 의도** | 자동차 부품 결함 / 자율주행 진단 데이터셋 |
| **PG** | `auto.components` 의 source `aihub_578` (22) + `aihub_71347` (4) |
| **Neo4j** | `:Module` (L4) |
| **알려진 한계** | 활용률 0.001% — 3 GB 라벨 데이터에서 26 module 만 추출. 데이터 형식 한계 (이미지·센서 위주, 텍스트 부족) |

---

### 2.9 KOTSA 수리검사

| 항목 | 내용 |
|---|---|
| **출처** | data.go.kr 15155857 (한국교통안전공단 자동차검사관리 수리검사내역) |
| **인증** | 불필요 (파일 다운) |
| **라이선스** | 공공 (kogl_type1) |
| **수집 의도** | 차종별 사고/침수/도난 빈도 통계 (10년 시계열) |
| **PG** | `auto.events_inspections` 47,171 row (사고 46,883 / 침수 183 / 도난 35 / 기타 70, 2016~2025) |
| **Neo4j** | `(:Inspection)` 후속 PR — 적재 routine 미구현 |
| **답변 시나리오** | "사고 차량 통계" → PG SQL 직접. 차량 매핑은 차량번호 (한국 번호판) 기반 — VIN 매핑 어려움 |
| **알려진 한계** | (a) Neo4j 미적재 → 그래프 traversal 불가. (b) 차종 매핑은 모델명 fuzzy match 필요 |

---

### 2.10 DART 사업보고서 (제조)

| 항목 | 내용 |
|---|---|
| **출처** | DART 사업보고서 본문 — 핀맨스의 DART API 재활용 |
| **수집 의도** | 제조 도메인 — 공장 위치 / 생산능력 / 가동률 (정형 표 파서, LLM 0%) |
| **Ingestion** | `src/autograph/extractors/dart_production_parser.py` (정규식 + 표 파서) |
| **PG** | `auto.plant_capacity` 107 / `plant_production` 77 / `plant_utilization` 53 (Hyundai 12 plants × 4~7년 + Kia 5 plants × 6년) |
| **Neo4j** | `(:Manufacturer)-[:MANUFACTURED_AT {snapshot_year, capa_units, actual_units, utilization_pct, source_type='dart_business_report', confidence_score=0.80}]->(:Plant)` 99 edges (시계열) |
| **Tool** | `get_plant_capacity / get_oem_production / list_plants_by_oem` |
| **답변 시나리오** | "현대차 울산공장 2023년 생산량" → `get_oem_production('00164742', 2023)` |
| **알려진 한계** | (a) 가동률 표 컬럼 다양 → 일부 미파싱 (`dart_production_parser.py:316 TODO`). (b) Hyundai/Kia 만 — 다른 OEM 확장 routine 필요 |

---

### 2.11 KAMA 매크로

| 항목 | 내용 |
|---|---|
| **출처** | data.go.kr 15051116 (연 생산) + 15051118 (월 산업) |
| **PG** | `auto.macro_production_yearly` 21 row (2005~2025) / `macro_industry_monthly` 204 row (2009-01~2025-12) |
| **Tool** | `get_macro_production / get_macro_industry` |
| **답변 시나리오** | "2024 한국 자동차 세계 점유율" → 4.55% (`macro_production_yearly`) |

---

### 2.12 USGS MCS (핵심광물)

| 항목 | 내용 |
|---|---|
| **출처** | USGS Mineral Commodity Summaries 2025 PDF |
| **수집 의도** | BOM Level 6 소재 — 배터리 광물 (Li/Ni/Co/Mn/Graphite) |
| **Ingestion** | `usgs_mcs` PDF parser |
| **PG** | `auto.master_minerals` 5 row (2024 snapshot) — world_production·world_reserves·import_reliance·price |
| **Neo4j** | `:Material` 6 (cathode chem NCM811/622/523/NCA/LFP/GRAPHITE_ANODE) / `:Mineral` 5 / `DERIVED_FROM` 17 (7-key 100%) / `MADE_OF` 8 |
| **알려진 한계** | 연 1회 PDF — parser 가 PDF 변경에 fragile. 회사단위 셀↔OEM 소싱은 grade C candidate (sparse, 정직 표기 — README §9) |

---

### 2.13 OEM IR / 뉴스룸

| 항목 | 내용 |
|---|---|
| **출처** | Hyundai/Kia 공식 IR / 뉴스룸 sitemap |
| **라이선스** | **copyrighted** — metadata_only 게이트 |
| **PG** | `auto.events_oem_news` 37 row (Hyundai 25 + Kia worldwide 12) |
| **알려진 한계** | (a) Kia 한국 뉴스룸 robots.txt Disallow — 비활성. (b) Mobis SPA (JavaScript) — robots 게이트로 비활성 |

---

### 2.14 KAMP 카탈로그

| 항목 | 내용 |
|---|---|
| **출처 URL** | `https://www.data.go.kr/data/15089213/fileData.do` (KAMP 제조AI 데이터셋 카탈로그) |
| **인증** | 불필요 — 무인증 CSV 직접 다운 |
| **라이선스** | 공공 (중기부/KAMP), 사용조건 "콘텐츠 변경허용" 50/50 |
| **수집 의도** | KAMP 포털(kamp-ai.kr) 본체 50종 데이터셋의 **메타·링크 인덱스** + 산단공 `:Process` 정규화 사전 (37 unique 적용공정) — Layer 1 회사무관 공정 지식 진입점 |
| **Ingestion** | 무인증 1회 `curl` (`docs/operations/api_keys_pending.md §기타` 참고) |
| **Loader 코드** | `src/autograph/loaders/load_kamp_catalog.py` (EUC-KR/UTF-8 자동, 산단공 정규화 inline `_PROCESS_NORM` dict) |
| **raw 저장** | `data/raw/kamp/catalog/_catalog_15089213.csv` (EUC-KR 원본) + `.utf8.csv` (변환본) |
| **PG 테이블** | `auto.kamp_catalog` (50 row, 33 process_name_norm, 13 industry, 11 process_category 다이캐스팅/프레스/용접/열처리/도금/CNC/사출/단조/용해 등) — 회사 비귀속 (corp_code 없음) |
| **Neo4j 노드·엣지** | (현재 미러링 보류 — 카탈로그는 인덱스로만 사용. 본체 KAMP 데이터셋이 들어오면 그때 :Process 매핑 정규화 적용) |
| **7키 메타** | `source='datagokr_kamp_15089213'`, `source_type='kamp_manufacturing'`, `source_id='kamp:15089213/<seq>'`, `confidence_score=0.800` (B 등급, 익명), `validated_status='candidate'`, `extraction_method='deterministic'`, `schema_version='kamp_catalog_v1'` |
| **추출 Pass** | P1 (deterministic) — 카탈로그 CSV 한 줄당 한 노드, 산단공 정규화는 inline dict 매핑 |
| **상태** | **카탈로그 적재 완료** (2026-06-02). 본체 데이터셋은 **냉철 평가 후 보류 결정**: KAMP 본체는 출처 익명 + 단일 라인 → 일반화 약함. NHTSA+KOTSA 자체 텍스트로 만든 `:DefectType` 50개가 이미 더 강함 (`docs/operations/api_keys_pending.md` 참고) |
| **알려진 한계** | (a) KAMP 본체 다운은 회원가입(kamp-ai.kr) + 수동, 보류. (b) 본 채널은 메타 인덱스 + 정규화 사전이지 결함 데이터 자체 아님 |

---

### 2.15 NASA PCoE

| 항목 | 내용 |
|---|---|
| **출처 URL** | `https://www.nasa.gov/intelligent-systems-division/discovery-and-systems-health/pcoe/pcoe-data-set-repository/` + S3 미러 `https://phm-datasets.s3.amazonaws.com/NASA/` |
| **인증** | 불필요 — 무인증 S3 직접 다운 |
| **라이선스** | US 공공 도메인 (17 U.S.C. §105). 인용 권장 (NASA Ames Prognostics Data Repository + 원저자) |
| **수집 의도** | 회사무관 설비 고장모드 taxonomy (Layer 1) — readme/논문 텍스트에서 `:FailureMode` 노드 시드 추출. 시계열 raw는 적재 안 함 (가이드 §2.3 정신) |
| **수집 범위** | **Bearing IMS (1.0 GB)** + **Battery Li-ion (200 MB)** + **IGBT Accelerated Aging (229 MB)** = 3 zip 1.4 GB. C-MAPSS/Milling 제외 (자동차 bridge 약함) |
| **Ingestion** | 무인증 `curl` 3 zip → nested archive 1단계 풀기 (Bearing은 7z `py7zr`) → readme/논문 PDF 텍스트 추출 (`pdfplumber`) |
| **추출 (LLM 우회)** | Claude Code Agent (`general-purpose`)에게 3개 텍스트 입력 → 18 `:FailureMode` JSON 추출. **외부 API 호출 0** (`docs/operations/api_keys_pending.md` Anthropic 우회 패턴) |
| **raw 저장** | `data/raw/nasa_pcoe/{bearing,battery,igbt}/*.zip` + `_readme/{battery_README,bearing_README,igbt_paper}.txt` + `_failure_modes_pcoe.json` |
| **PG 테이블** | `auto.failure_modes` (18 row, equipment=igbt:8 / battery:6 / bearing:4, BGE-M3 embedding 100%) + `auto.failure_mode_manifestations` (72 엣지 — cosine_topk 36 + llm_assign 36) |
| **Neo4j 노드·엣지** | `:FailureMode` 18 (domain=['auto']) / `:Equipment` 3 (battery/bearing/igbt) / `SUBJECT_TO` 18 (Equipment→FailureMode) / `MANIFESTS_AS` 72 (FailureMode→DefectType, [§4.2](#42-layer1-bridge)) |
| **7키 메타** | `source='nasa_pcoe'`, `source_type='readme_text_extraction'`, `source_id='pcoe:<equipment>#<name>'`, `confidence_score=0.800` (A 공공, 단 회사 비귀속), `validated_status='candidate'`, `extraction_method='llm'`, `schema_version='failure_mode_v1'` |
| **추출 Pass** | Agent 우회로 readme/논문 → 18 mechanism-level `:FailureMode` (자동차 component_hint 명시 — EV motor 베어링/Hyundai/Kia ICCU IGBT 등) |
| **Tool 진입점** | `MATCH (e:Equipment)-[:SUBJECT_TO]->(fm:FailureMode)-[:MANIFESTS_AS]->(dt:DefectType)<-[:DEFECT_MATCHES]-(rc:Recall)` 4-홉 경로 — "엔진블록 균열 리콜의 추정 공정 원인은?" 질의 |
| **답변 시나리오** | KOTSA "고전압 배터리 제조 결함" 리콜 (`r_sim=0.99`) → :DefectType "배터리 셀 내부 단락" → :FailureMode "충방전 사이클 용량 감소" (llm_conf 0.72) → :Equipment "battery" |
| **알려진 한계** | (a) NASA 학술 어휘 ↔ NHTSA/KOTSA 자동차 OEM 어휘 갭 — cosine 평균 0.538 약함 (llm_assign 평균 0.642로 보강). (b) Battery는 lab 18650 cell ≠ pack-level 자동차 배터리, Bridge MEDIUM. (c) C-MAPSS/Milling 제외 — turbofan ≠ 자동차 turbo, milling은 off-scope |

---

### 2.16 EU Safety Gate

| 항목 | 내용 |
|---|---|
| **출처 URL** | `https://ec.europa.eu/safety-gate-alerts/` (구 RAPEX) + weekly XML API `https://ec.europa.eu/safety-gate-alerts/api/download/weeklyReport/detail/xml/<REPORT_ID>` |
| **인증** | 불필요 — `curl` no-auth XML |
| **라이선스** | **CC BY 4.0** (Commission Decision 2011/833/EU, EUR-Lex CELEX 32011D0833) — `_license.py`에 `eu_safety_gate = cc_by_4_0` 등록 권장 |
| **수집 의도** | Layer 2 회사귀속 자동차 리콜 — **세번째 지역 커버** (US NHTSA + KR KOTSA + EU). EU 시장 OEM(VW/Stellantis/BMW/Mercedes/Renault/Hyundai-EU/Kia-EU)의 cross-jurisdictional 결함 신호 |
| **REPORT_ID 매핑** | 약 +52/yr, 일부 missing. 2020 w38 = `10000012` / 2024 w19 = `10000200` / 2026 w14 = `10000300`. 2024-01부터 다운 = ID 10000185~10000315 (131개 weekly) |
| **Ingestion** | weekly XML 131 다운 (5 병렬 curl) → `<category>Motor vehicles</category>` 필터 (다른 카테고리 = 장난감/전자/화장품 제외) |
| **Loader 코드** | `src/autograph/loaders/load_eu_safety_gate.py` (XML 파싱 + brand 정규화 `_candidate_brands` 함수: case-insensitive + multi-brand split `/`,`,`,`and`,`&` + HTML entity decode + `.` strip) |
| **raw 저장** | `data/raw/eu_safety_gate/xml/weekly_<REPORT_ID>.xml` (122/131 정상, 9개 400 누락) — 총 21 MB |
| **PG 테이블** | `auto.events_recalls` (source='eu_safety_gate', **972 row** 2024-2026, with_danger 100%, brand 매핑률 **86.7%** = 843/972) |
| **vec.chunks** | `source='eu_recall'` (972 청크, BGE-M3 임베딩 100%, section='auto.recall') |
| **Neo4j 노드·엣지** | `:Recall` 972 (domain=['auto']) + 신규 `:Manufacturer` 9개 (SCANIA/POLESTAR/DAIMLER TRUCK/STELLANTIS/SKODA/SEAT/DACIA/MAN/RENAULT TRUCKS/DS AUTOMOBILES/CUPRA/BMW ALPINA/VAUXHALL) — source='eu_safety_gate_alias' / 'kotsa_alias' |
| **DEFECT_MATCHES** | 2,916 엣지 (cosine_topk top-3, cos_sim ≥ 0.40, 평균 **0.618**). 동일 OEM 다 지역 cross-jurisdictional bridge 가능 (Takata airbag / EA189 emissions 등) |
| **7키 메타** | `source='eu_safety_gate'`, `source_recall_no=<caseNumber>` (예 A12/01239/20), `confidence_score=1.000`, `validated_status='verified'`, `extraction_method='deterministic'`, `schema_version='eu_safety_gate_v1'`. country=ISO-2 notifyingCountry (DE/FR/IT/...) |
| **추출 Pass** | P1 (deterministic, XML 파싱) — brand → manufacturer_id 매핑은 alias dict + master_manufacturers exact match |
| **Tool 진입점** | `list_recalls_affecting(variant_id)` (기존 NHTSA Recalls 동일 인터페이스, source 필터 추가 가능) |
| **답변 시나리오** | EU 리콜 "Integrated Charging Control Unit (ICCU) can deteriorate" → :DefectType "전력 전자부품 내부 고장(충전기·컨버터·인버터)" cos=0.81 → 현대/기아 EV ICCU 고장 cross-region 추적 |
| **알려진 한계** | (a) 9 weekly REPORT_ID HTTP 400 (누락). (b) **brand 매핑 86.7%** — 잔여 13.3%는 부품 supplier(Goodyear/Meyle/Michelin), 농기/모터사이클(NEW HOLLAND/CF MOTO), brand=NULL 10건 — 추가 가치 낮음. (c) variant/model 매핑은 NULL (텍스트에서 정밀 추출 어려움), AFFECTED_BY 엣지 부분 |

---

## 3. IP 도메인

### 3.1 CPC scheme

| 항목 | 내용 |
|---|---|
| **출처** | USPTO/EPO 공동 CPC scheme bulk (CPCTitleList202605.zip) |
| **인증** | 불필요 |
| **PG** | `ip.cpc_scheme` **10,695 row** (section 9 + class 137 + subclass 681 + main_group 9,868) |
| **Neo4j** | `:CPCCode` 10,695 / `SUBCLASS_OF` 10,686 (7-key 100%) |
| **수집 의도** | 특허 분류 계층 (depth ≥ 4) — 정식 온톨로지 골격 |
| **Tool** | `list_patents_in_cpc('B60W', include_subclasses=True)` / `ip_cpc_descendants` |
| **알려진 한계** | subgroup 250K 는 별도 cron — 본 적재는 main_group 까지 |

---

### 3.2 OpenAlex

| 항목 | 내용 |
|---|---|
| **출처** | https://api.openalex.org |
| **인증** | 무료 키 (하루 10만 크레딧, 2025-02 이후 필수) |
| **라이선스** | CC0 |
| **수집 의도** | 글로벌 논문·연구 — institution↔corp_entity 매핑으로 특허×논문×재무 3중 cross |
| **PG** | `ip.works` 629 / `ip.institution` 38 / `ip.work_institution` 638 |
| **Neo4j** | `:Work` 629 / `:Institution` 38 / `AUTHORED_AT` 638 (7-key 100%) / `IS_ENTITY` 38 (Institution → Company cross-domain bridge) |
| **vec.chunks** | abstract 423건 → BGE-M3 backfill 대상 (현재 embedding NULL) |
| **수집 범위** | KR 38 corp_code 매칭 (현대차/모비스/기아/만도/LG/네이버/효성/금호석유/한미약품/Hyundai Steel …) × 상위 인용 work 20씩, 2020~ |
| **알려진 한계** | (a) embedding backfill 미실행. (b) 38 corp_code 만 — 코스피200 전체 확장 필요. (c) work 의 assignee → corp 매핑 (institution → corp) 만 — 저자 개인은 별도 |

---

### 3.3 USPTO Open Data Portal (예정)

| 항목 | 내용 |
|---|---|
| **출처** | https://data.uspto.gov (PatentsView 후속, 2026-03-20 이관 완료 — REST 종료, bulk dataset 채택) |
| **인증** | 무인증 (bulk) |
| **수집 의도** | US 특허 + 인용 네트워크 + assignee 정규화 |
| **현재 상태** | `ingestion/uspto_odp.py` 구현됨, bulk dataset 다운·적재 대기 |
| **목표 PG** | `ip.patents` / `ip.citations` / `ip.assignees` |
| **Tool (적재 후)** | `list_patents_by_assignee / get_citation_network` |

---

### 3.4 KIPRIS (예정)

| 항목 | 내용 |
|---|---|
| **출처** | KIPRIS Open API (공공데이터포털) |
| **인증** | `KIPRIS_API_KEY` |
| **라이선스** | 검색·서지 무료 / 본문·대량은 KIPRISPLUS 회원 |
| **현재 상태** | `ingestion/kipris.py` 구현됨, 키 발급 대기 |
| **목표 PG** | `ip.patents` (KR) / `ip.assignees` (KR) |

---

## 4. Bridge / Cross-Domain

### 4.1 bridge.corp_entity

| 항목 | 내용 |
|---|---|
| **목적** | 한국 corp_code (finance) ↔ 글로벌 entity (auto/ip) 양방향 매칭 |
| **매칭 우선순위** | `wikidata_qid > LEI > sec_cik > business_no > name fuzzy > manual` |
| **PG 테이블** | `bridge.corp_entity` — 4,806 row (manufacturer cand 1 + reviewed 11 + supplier cand 4,790 + reviewed 4) |
| **strong_match** | 15/15 = 100% (confidence ≥ 0.9) |
| **`match_method` enum** | `qid_exact | lei_exact | business_no_exact | corp_code_exact | fuzzy_name | manual` (6종) |
| **별개 컬럼** | `sec_cik` (글로벌 OEM 진입점, `bridge_sec_cik_to_entity` 함수 별도) |
| **Loader** | `src/autograph/loaders/load_bridge.py` |
| **Tool** | `bridge_corp_to_entity / bridge_entity_to_corp / bridge_sec_cik_to_entity / bridge_entity_to_sec_cik / cross_query` |
| **ipgraph mirror** | 신규 join 테이블 `ip.assignee_corp_map` (bridge.corp_entity 직접 변경 회피) |
| **답변 시나리오** | "현대모비스 매출 + 모비스가 공급하는 차종" → `bridge_corp_to_entity('00164788', entity_type='manufacturer')` → entity_id → `get_suppliers_of_component` → vehicles → `list_recalls_affecting` |
| **알려진 한계** | (a) **supplier candidate 4,790 영속 누적** — 검토 SOP 미정 (`docs/mental_model.md §5.3`). (b) name fuzzy match 의 false-positive 위험 — manual review 부담. (c) ip assignee → corp 매핑 routine 미실행 (assignee 적재 대기) |

---

### 4.2 Layer1 Bridge

| 항목 | 내용 |
|---|---|
| **목적** | 회사귀속 `:Recall` (L2, A 등급) ↔ 회사무관 `:DefectType` (L1, C 등급) ↔ 설비 `:FailureMode` ↔ `:Equipment` 의미 정렬 — 가이드 §1.x 4-홉 회사귀속·회사무관 추적 |
| **소속 출처** | (a) `:DefectType` 50 — NHTSA+KOTSA defect_summary 1,434건 텍스트 → Claude Code Agent 추출 (§2.2/§2.9 자체 + Agent 우회). (b) `:FailureMode` 18 + `:Equipment` 3 — NASA PCoE readme/논문 (§2.15) |
| **신규 SQL** | `infra/postgres/init/28_auto_defect_matches.sql` (`auto.defect_types` + `auto.defect_matches`) / `29_auto_failure_modes.sql` (`auto.failure_modes` + `auto.failure_mode_manifestations`) — 둘 다 pgvector embedding(1024) + 7키 풀 |
| **PG 테이블** | `auto.defect_types` 50 (assembly 8/software 8/electrical 7/process 7/design 6/material 5/mechanical 5/safety_system 4) / `auto.failure_modes` 18 / `auto.defect_matches` **7,417 엣지** / `auto.failure_mode_manifestations` 72 엣지 |
| **DEFECT_MATCHES** | `(:Recall)─[DEFECT_MATCHES {cos_sim, confidence, match_method}]→(:DefectType)`. 두 경로: **cosine_topk** 7,218 (BGE-M3 top-3, cos>=0.40) + **llm_assign** 199 (sample 200건 Agent 직접 분류). 정제 SOP: 교집합 → validated, cos>=0.85 → validated, cos<0.55 → rejected — 결과 **590 validated** / 85 rejected / 6,742 candidate |
| **MANIFESTS_AS** | `(:FailureMode)─[MANIFESTS_AS]→(:DefectType)`. cosine 평균 0.538 약함 → llm_assign 36 추가 (평균 conf 0.642) → 정제 결과 **14 validated** / 29 candidate / 29 rejected |
| **SUBJECT_TO** | `(:Equipment)─[SUBJECT_TO]→(:FailureMode)` 18 deterministic (PG → Neo4j MERGE) |
| **Loader 코드** | `src/autograph/loaders/extract_defect_types_llm.py` (LLM/Agent 추출 + DB upsert) / `load_defect_matches_neo4j.py` (PG → Neo4j 미러링 + Recall 보충) |
| **7키 메타** | DEFECT_MATCHES: `source='bridge_defect_matches'`, `source_type='bge_m3_cosine' | 'llm_label'`, `confidence_score=cos_sim` 또는 0.700 (LLM), `extraction_method='cosine_topk' | 'llm'`, `schema_version='defect_matches_v1'`. MANIFESTS_AS 동일 패턴 `schema_version='manifestations_v1'` |
| **Tool 진입점** | `(rc:Recall)-[:DEFECT_MATCHES]->(dt:DefectType)<-[:MANIFESTS_AS]-(fm:FailureMode)<-[:SUBJECT_TO]-(e:Equipment)` 4-홉 경로 — "이 자동차 리콜의 추정 공정 메커니즘은?" 질의 |
| **답변 시나리오** | KOTSA "고전압 배터리 제조 결함" 리콜 (DM cos=0.99) → :DefectType "배터리 셀 내부 단락" → :FailureMode "충방전 사이클 용량 감소"(llm 0.72) / "전해액 분해 저항 상승"(0.70) / "전극 전하전달 저항 상승"(0.70) → :Equipment "battery" |
| **알려진 한계** | (a) DEFECT_MATCHES 6,742 candidate (88%) 회색지대 (cos 0.55~0.85) — 사람 검토 SOP 미정. (b) MANIFESTS_AS cosine 약함 (학술↔OEM 어휘 갭) — llm_assign 보강이 핵심. (c) NHTSA/KOTSA defect_summary가 자동차 부품 specific(subframe/airbag) 어휘라 NASA 일반 mechanism 카테고리와 자연 매칭 어색한 경우 다수 |

#### 4.2.1 Cross-Jurisdictional 결함 패턴 (2026-06-04 검증)

`master_manufacturers` dedup (한국 OEM 5+4+3 + Ford 10 + 기타 7 OEM = 21 dup row → 8 canonical) 후 DEFECT_MATCHES 풀(cos≥0.65)을 사용한 글로벌 OEM 결함 시그널.

**4 OEM이 3 지역 모두 등장**: FORD / **HYUNDAI** / **KIA** / TESLA.
**9 OEM이 2 지역**: BMW / GENESIS / JAGUAR / MAN / MERCEDES-BENZ / PORSCHE / SCANIA / TOYOTA / VOLKSWAGEN.

**TOP 2+ source 동일 (OEM × :DefectType) 매칭**:

| OEM | DefectType (KO) | category | sources | 쌍 |
|---|---|---|---|---|
| FORD | 배치 오류에 의한 고온부 접촉 | assembly | EU+NHTSA | **161** |
| FORD | 후방 카메라 영상 손실·정지 | software | EU+NHTSA | **116** |
| VOLKSWAGEN | 안전삼각대 반사성능 부적합 | process | KOTSA+EU | 83 |
| MERCEDES-BENZ | 접착제·프라이머 접합 불량 | material | KOTSA+EU | 76 |
| HYUNDAI | 와이어 하니스 차체 간섭·마모 | design | EU+NHTSA | 43 |
| MERCEDES-BENZ | ECU 캘리브레이션·제어 로직 오류 | software | KOTSA+EU | 39 |
| HYUNDAI | 전력 전자부품 내부 고장 (충전기·컨버터·인버터) | electrical | EU+NHTSA | 4 |
| KIA | 전력 전자부품 내부 고장 (충전기·컨버터·인버터) | electrical | EU+NHTSA | 3 |
| JAGUAR | 주조 기포·박벽에 의한 누설 | process | KOTSA+EU | 3 |

**3-source (NHTSA+KOTSA+EU) 동시 매칭 — 1건**:
- FORD "연료 라인·레일 누유·손상" assembly **7 쌍**

**시스템 가치 — 3가지 시스템 의미**:
1. **현대·기아 EV ICCU 글로벌 캠페인 시그널 자동 검출** (HYUNDAI 4 + KIA 3) — 2023~2024 Ioniq6/EV6 ICCU 캠페인의 정확한 패턴
2. **JAGUAR "주조 기포·박벽에 의한 누설"** KOTSA+EU 3쌍 — NASA PCoE FailureMode 어휘가 자동차 OEM 리콜과 직결, 주조 공정 결함→자동차 리콜 추적이 그래프 차원 작동 검증
3. **FORD 글로벌 결함 시그널** (161+116+12+7) — Ford 9 dup row 통합으로 가시화된 글로벌 캠페인 신호

**dedup 운영 메모** (2026-06-04):
- 한국 OEM canonical: HYUNDAI=498 / KIA=499 / GENESIS=5083 (NHTSA vPIC id)
- Ford canonical: 460 (304 NHTSA recalls + 49 통합)
- 자회사·법인 그룹(현대자동차그룹/현대자동차 인도/현대자동차 체코 공장)은 **별도 entity 보존** — :Manufacturer 아닌 corporate group entity
- 통합 SOP: `(refs total = recalls + models + complaints + investigations)` 최다 row → canonical, dup → references UPDATE 후 master DELETE + 양방향 alias union

---

## 5. 알려진 한계 — 시스템 차원 통합

채널별 한계는 위 §1~§4 표 마지막 행. 시스템 차원으로 묶으면:

| 한계 카테고리 | 영향 채널 | 영향 |
|---|---|---|
| **외부 rate-limit** | Wikidata (1 req/min), SEC (10 req/sec) | 대량 수집 시간 비대화 — Wikidata P176 자동 추출 0 row |
| **수동 CSV 모드** | car.go.kr, KNCAP, KCGS, AI Hub | 자동 갱신 불가 — 분기별 수기 작업 필요 |
| **저작권 metadata_only** | 연합뉴스, OEM IR | 본문 vector RAG 불가 — 멘션·메타만 |
| **부분 적재 (체결 후 점진)** | embedding backfill, NHTSA TSB, KNCAP | 일부 채널 측정 무효 |
| **단일 OEM 의존** | DART 사업보고서 (Hyundai/Kia만), KOTSA (차량번호 매핑 어려움) | 확장성 한계 |

→ 시스템 차원 review 는 [docs/system_review.md](system_review.md) (다음 신설 문서).

---

## 5.1 Raw 디스크 보존 정책

| 영역 | 보존 정책 | 라이선스 게이트 |
|---|---|---|
| 공공 데이터 (NHTSA/KAMA/DART/산단공/KOTSA/Wikidata/CPC/USPTO ODP/OpenAlex) | **영구 보존** — 멱등 파이프라인 보장 | `src/autonexusgraph/ingestion/_license.py` |
| Wikipedia CC BY-SA | 본문 보존 가능 | 출처 표기 강제 |
| 연합뉴스 RSS | 메타+요약만 (저작권) | 본문 저장 금지 (`copyrighted` 게이트 자동 strip) |
| AI Hub | 약관에 따라 (회원 + 다운로드 승인) | 별도 게이트 |
| 제조사 IR / 뉴스룸 (Hyundai/Kia worldwide) | metadata_only (`copyrighted` 게이트) | robots/ToS 게이트 + Kia KR / Mobis 비활성 |
| **KAMP 카탈로그** (data.go.kr 15089213) | 영구 보존 — CSV + UTF-8 변환본 | 공공 (콘텐츠 변경허용) |
| **NASA PCoE** (Bearing/Battery/IGBT) | zip + 추출 readme 영구 보존 (1.4 GB) | US 공공 도메인, 인용 |
| **EU Safety Gate** weekly XML | 영구 보존 — 멱등 재파싱 가능 | CC BY 4.0 (출처 표기) |

**총 raw 사용량 (2026-06-04 측정)**:
```
data/raw/auto/             — 3.7 GB (AI Hub 3.6 GB 우세)
data/raw/dart_bulk/        — 1.6 GB (finance + 자동차 6 OEM 사업보고서)
data/raw/nasa_pcoe/        — 1.4 GB (Bearing 1.0 GB + IGBT 230 MB + Battery 200 MB)
data/raw/datagokr/         — 1.9 MB (산단공 + KAMA + KOTSA)
data/raw/eu_safety_gate/   — 21 MB (122 weekly XML)
data/raw/kamp/             — 25 KB (catalog CSV 50건)
data/raw/wikipedia/        — 34 MB
data/raw/wikidata/         — 6.4 MB
```

---

## 5.2 데이터 처리 파이프라인 공통 패턴

```
[1] Ingestion              [2] Loader (PG)               [3] Loader (Neo4j)
    ─────────────────         ─────────────────              ─────────────────
    공식 API / CSV        →  ON CONFLICT DO UPDATE      →  MERGE + edge_meta_cypher
    save_raw()               (corp_code, plant_code,       (의무 메타 7키 100%)
    CheckpointStore          snapshot_year)
    RateLimiter

           ↓                          ↓                          ↓
    data/raw/<source>/       auto.<table>                  :Label + Relationship

                                      ↓                          ↓
                            [4] 에이전트 도달 경로
                            ─────────────────
                            handler.allowed_intents (sql/graph/research)
                              → tools/{financials, graph, retrieve}.py     (finance)
                              → autograph/tools/{spec, graph, retrieve, bridge}.py (auto)
                              → ipgraph/tools/{patents, graph, retrieve, bridge}.py (ip)
                            (planner → supervisor → workers → synthesizer)
```

**의무 메타 7키** (README §3.7 — `EDGE_REQUIRED_META_KEYS` SSOT, `src/autonexusgraph/ontology/schema.py:28-36`):

| # | 키 | 의미 |
|---:|---|---|
| 1 | `source_type` | `recall \| ir_disclosure \| manual \| wikidata \| wikipedia \| llm_extraction \| manual_curation` 등 |
| 2 | `source_id` | `NHTSA-25V-001 / DART-rcept_no / chunk_id:NNN / supplier_seed.yaml#rowN` |
| 3 | `confidence_score` | `0.0~1.0` 할당값 (A=0.95 / B=0.80 / C=0.50) |
| 4 | `validated_status` | `candidate \| validated \| rejected \| needs_review` |
| 5 | `snapshot_year` | 측정·발표 연도 |
| 6 | `extraction_method` | `deterministic \| llm \| hybrid \| manual` |
| 7 | `schema_version` | ontology yaml 헤더 (실제 값 `"v2.2"` — `ontology/{auto,ip}/relations.yaml` 및 `ontology/relations.yaml` SSOT) |

**옵션 키 (라이프타임 엣지에만)**: `valid_from`, `valid_to` — `SUPPLIED_BY` / `MANUFACTURED_AT` / `COMPLIES_WITH` 같은 시점 구간 의미 있는 관계만.

검증 명령: `make audit-edge-meta --strict` (`scripts/audit/edge_meta_invariants.py`).

---

## 5.3 데이터 채널 트래픽라이트

```bash
make audit-data-channels    # eval/reports/data_channels_latest.md 생성
```

🟢 적재 완료 / 🟡 raw 만 (loader 대기) / 🔴 raw 도 없음 / ⊘ 키 대기.

**현재 상태 요약** (2026-06-04, 자세히는 [data_inventory.md](data_inventory.md)):

| 도메인 | 🟢 적재 완료 | 🟡 부분 | ⊘ 키/액션 대기 | 🔴 미수집 |
|---|---|---|---|---|
| finance | DART/KRX/Wikidata/Wikipedia/SEC/GLEIF/News/KCGS | ECOS | KOSIS / FTC / LAW | — |
| auto | NHTSA vPIC/Recalls/Complaints/Investigations/SafetyRatings, EPA, AI Hub, KOTSA, DART production, KAMA, USGS MCS, OEM IR (Hyundai/Kia ww), **KAMP catalog** (50), **NASA PCoE** (FailureMode 18 + Equipment 3), **EU Safety Gate** (Recall 972 + brand 86.7%), **DEFECT_MATCHES Bridge** (DefectType 50 / 7,417 엣지 / MANIFESTS_AS 72) | 팩토리온 | DATA_GO_KR_API_KEY (팩토리온) / BIGDATA_TIC_CLIENT_ID (KATRI) / KNCAP / Euro NCAP / IIHS / KAMP 본체 (kamp-ai.kr 가입 보류 결정) | Mobis IR (SPA), Kia KR newsroom (robots Disallow), MaintNet (가이드 SSOT 부정확 — repo 없음/license 미명시, 보류 결정) |
| ip | CPC scheme 10,695 / OpenAlex works 629 | — | **GCP Service Account JSON (BigQuery patents-public-data, P0)** / KIPRIS_API_KEY / USPTO ODP API key (2026-06-18부터 mandatory) | — |

---

## 5.4 더 필요한 데이터 — 우선순위 백로그

README §11.2 BOM 가용성 매트릭스 + 사용자 의제 ("크롤링이 진짜 가치") 기준.

### 🔴 P0 — 즉시 활성화 가능 (키 발급만)

1. **DATA_GO_KR_API_KEY 발급** — 한 키로 4 endpoint 활성:
   - ~~15089863 한국 리콜 (KOTSA)~~ → **오픈API 폐기. 3048950 CSV 로 대체** (키 불필요, events_recalls 941 row 적재 완료)
   - ~~15089213 KAMP 카탈로그~~ → **무인증 파일 다운, 50건 적재 완료** ([§2.14](#214-kamp-카탈로그))
   - 15087611 팩토리온 (plant↔생산품 매핑) — **키 발급+적재 완료**
   - 15051116/15051118 KAMA (이미 CSV 로 받음 — 키 있으면 자동 갱신)
   - 활용 신청: data.go.kr → 회원가입 → 활용신청 (자동 승인 ~1일)

2. **GCP Service Account JSON 발급** (P0, 2026-06-04 현재 작업 중단점) — Google Patents BigQuery 활성:
   - patents-public-data.patents.publications → 자동차 OEM(현대/기아/Toyota/Ford/VW/BMW/Mercedes/Tesla) 특허 추출
   - 발급 절차: [docs/operations/api_keys_pending.md §1](operations/api_keys_pending.md)
   - 환경: `GOOGLE_APPLICATION_CREDENTIALS=/path/to/json` — Python `google-cloud-bigquery 3.41.0` 설치 완료

3. **KIPRIS_API_KEY 발급** (선택, 한국 OEM 정밀 보강) — `src/ipgraph/loaders/load_kipris.py` + `src/autonexusgraph/ingestion/kipris_client.py` 코드 ready
   - 발급: http://plus.kipris.or.kr 회원가입 → 오픈API 신청 (자동 승인 ~1영업일)

4. **USPTO ODP API 키** (2026-06-18부터 mandatory, 현재 우회 가능) — GCP BigQuery로 자동차 OEM USPTO 특허 커버 시 불필요

3. **`plants.yaml` 확장** — DART production loader 가 미매핑 plant skip 중:
   - 현재 18 plant 등록 → 6 OEM × 사업보고서 raw 분석하여 ~30 plant 추가 가능
   - 우선: HMI (인도 첸나이), HMMR (러시아), HTMV (베트남), HMMI (인도네시아), KMS (슬로바키아), 모비스 글로벌 공장 6+

### 🟡 P1 — 가치 있지만 약관 검토 필요

4. **제조사 IR/뉴스룸 크롤링 확장** ("진짜 가치" 채널):
   - Hyundai newsroom (hyundai.com/worldwide/ko/newsroom/)
   - Kia newsroom, 모비스 뉴스
   - 추출: 공장 위치/CAPA/모델 배정 발표, 신차 출시
   - **약관 검토**: 각 사 robots.txt + 이용약관 검토 후 활성화

5. **Wikipedia plant 문서** — 기존 `wikipedia_auto.py` 는 모델·제조사만:
   - "Hyundai Motor Manufacturing Alabama" 류 plant 문서 별도 ingestion
   - model↔plant 자동 매핑 보강 (DART 본문보다 글로벌 범위 넓음)

6. **KOSIS / FTC / LAW.go.kr** — 거시 통계 + 기업집단 + 법령 — 키 발급 후 가치 정의 재검토

### 🟢 P2 — 향후 use case 정의 후

7. **AI Hub 67** (제조 AGV 열화 예지보전) — 자동차 관련만 다운로드 → `auto.processes` 보강 (~10-20 row 예상)

8. **KATRI (bigdata-tic.kr)** — OAuth 키 (BIGDATA_TIC_CLIENT_ID/SECRET) 발급 후 인증/표준 데이터 → `:Standard` 노드 ↔ `(:VehicleVariant)-[:COMPLIES_WITH]` 보강

9. **Euro NCAP / IIHS** — 별도 약관 검토 후

### ⚪ 영구 보류 (PRD non-goal — README §9)

- 라인·설비 수준의 진짜 제조 공정 데이터 (가동률, 설비 파라미터, 공정별 수율) — **영업비밀, 오픈 없음**
- 비공개 OEM 내부 BOM
- 실시간 텔레메트리
- 자율주행 안전성 인증 대체

---

## 6. 새 채널 추가 — 표준 절차

새 채널 추가 PR 은 다음을 모두 충족:

```
1. data_sources.md 의 §데이터 분류 SSOT 에 등급 (S/A/B/C/D) 부여 + 라이선스 명시
2. _license.py:LICENSE_POLICY 에 source 키 추가 (test_license.py invariant 통과)
3. src/<domain>graph/ingestion/<source>.py 구현 (RateLimiter + CheckpointStore + 멱등)
   또는 finance 의 경우 src/autonexusgraph/ingestion/<source>_client.py + scripts/ingest/download_<source>.py 분리 구조
4. 멱등 loader 작성 — ON CONFLICT DO UPDATE / MERGE + SAVEPOINT 패턴 + edge_meta_cypher 의무 메타
5. infra/postgres/init/<NN>_<table>.sql 마이그레이션 (멱등 + GRANT)
6. ontology/<domain>/{entities,relations}.yaml 갱신 (필요 시)
7. cypher_templates_<domain>.py 에 새 템플릿 추가 (필요 시, param schema 검증)
8. tools/ 에 사용자 진입 함수 추가 + 화이트리스트 (`agent_handler.allowed_intents`)
9. Makefile 타깃 추가 (.PHONY 등록 + `load-<domain>-all` 의존 list)
10. data_inventory.md 적재 후 측정값 갱신
11. **본 data_lineage.md 에 채널 1 항목 추가** ← 빼먹기 쉬움
12. gold QA 새 row 추가 (적재 검증) — `docs/gold_qa_guide.md` 참조
13. 테스트 (DB 미가용 환경에서 통과) — `make smoke-e2e` 통과
```

# AutoGraph — 데이터 소스 카탈로그

작성일: 2026-05-28 · 조사 방식: web search + 공식 문서 + 학술 논문 + 기존 코드 비교

본 문서는 AutoGraph 도메인 (자동차 제품·부품·리콜·공급망 GraphRAG) 의 **모든 후보 데이터 소스**를 정리한다. 각 소스는 (1) 키/인증 요구, (2) 코드 적용 상태, (3) 어떤 README §1 현황표·테이블·관계를 채우는지, (4) 미수집·미구현 사유, (5) 라이선스를 명시한다.

---

## 0. 요약 — 현재 통합 상태

| Tier | 정의 | 소스 개수 |
|---|---|---|
| **S** | 코드 통합 완료, 키 불필요 | 7 |
| **A** | 코드만으로 추가 가능, 키 불필요 | 9 |
| **B** | 키 발급 필요, 무료 (data.go.kr 등) | 7 |
| **C** | 스크래핑 또는 PDF 파싱 필요 | 5 |
| **D** | 상용/협의 필요 (제외) | 3 |

**README §11.2 BOM Level 0~4 / §4.0 출처 등급 A·B·C** 기준 매트릭스는 §6 참조.

---

## 1. Tier S — 통합 완료 (키 불필요)

### S1. **NHTSA vPIC** (Vehicle Product Information Catalog)
- **URL**: `https://vpic.nhtsa.dot.gov/api/`
- **무엇**: 차량 제조사·모델·연식·트림 마스터 + Canadian Vehicle Specs (제원)
- **포맷**: JSON REST · 키 불필요 · User-Agent 권장
- **채우는 곳**: `anxg_auto.master_manufacturers`, `anxg_auto.master_vehicle_models`, `anxg_auto.master_vehicle_variants`, `anxg_auto.spec_measurements` (dim/weight)
- **README §4.0 등급**: **A** (0.95)
- **모듈**: `autograph.ingestion.nhtsa_vpic` + `loaders.load_auto_pg.load_vpic` + `loaders.load_auto_specs`
- **갱신**: NHTSA 가 모델년도 단위 갱신 (연 1회)
- **누락**: US 시장 한정 — 한국 전용 트림·국내명은 미포함 (Wikidata 보강 필요)

### S2. **NHTSA Recalls API**
- **URL**: `https://api.nhtsa.gov/recalls/recallsByVehicle?make=&model=&modelYear=`
- **무엇**: 차종별 NHTSA 리콜 캠페인
- **포맷**: JSON · 키 불필요
- **채우는 곳**: `anxg_auto.events_recalls`, Neo4j `(VehicleVariant)-[:AFFECTED_BY]->(:Recall)`
- **README §4.0 등급**: **A** (0.95)
- **모듈**: `autograph.ingestion.nhtsa_recalls` + `loaders.load_auto_pg.load_recalls`
- **누락**: US 시장만. 한국 리콜은 §B2 (data.go.kr).

### S3. **NHTSA Complaints API**
- **URL**: `https://api.nhtsa.gov/complaints/complaintsByVehicle?make=&model=&modelYear=`
- **무엇**: 결함 신고 (소비자 불만)
- **포맷**: JSON · 키 불필요
- **채우는 곳**: `anxg_auto.events_complaints`, `anxg_vec.chunks` (`source='nhtsa_complaint'`), Neo4j `:Complaint`
- **README §4.0 등급**: **A** (0.95)
- **모듈**: `autograph.ingestion.nhtsa_complaints` + `loaders.load_auto_pg.load_complaints` + `build_chunks_auto`

### S4. **NHTSA SafetyRatings API** (P0 추가 완료)
- **URL**: `https://api.nhtsa.gov/SafetyRatings/modelyear/{Y}/make/{M}/model/{Mod}`
- **무엇**: NCAP 5-star 전체·정면·측면·전복·폴 등급 + ESC/FCW/LDW 기능 유무
- **포맷**: JSON · 키 불필요
- **채우는 곳**: `anxg_auto.spec_measurements.safety.ncap.*`, Neo4j `(VehicleVariant)-[:SAFETY_RATED_BY]->(:Standard {code:'NCAP_US'})`
- **README §4.0 등급**: **A** (0.95)
- **모듈**: `autograph.ingestion.nhtsa_safety_ratings` + `loaders.load_auto_safety`
- **누락**: NHTSA NCAP 만 (US). KNCAP/EuroNCAP 별도 필요 (§C2, §C4).

### S5. **Wikidata SPARQL**
- **URL**: `https://query.wikidata.org/sparql`
- **무엇**: 제조사 / 모델 / 공급사 마스터 + QID (글로벌 ID) + LEI (P1278) + 한국 사업자번호 (P3320) + 부품→공급사 P176
- **포맷**: SPARQL · 키 불필요 · User-Agent 필수
- **채우는 곳**: `anxg_auto.master_manufacturers/wikidata_qid`, `anxg_bridge.corp_entity`, `anxg_auto.master_suppliers`, `anxg_auto.staging_relations` (SUPPLIED_BY)
- **README §4.0 등급**: **B** (0.80)
- **모듈**: `autograph.ingestion.wikidata_auto` + `loaders.load_bridge` + `loaders.load_wikidata_part_supplies` (P4 완료)
- **누락**: Wikidata 자동차 부품 P176 sparse — 큰 OEM 의 메이저 부품 외엔 거의 없음. LLM P3 가 보완.

### S6. **Wikipedia (ko/en) REST API** (P3 추가 완료)
- **URL**: `https://{lang}.wikipedia.org/w/api.php?action=query&prop=extracts|info|pageprops` + `action=parse`
- **무엇**: 자동차 모델/제조사 본문 + Infobox 구조 데이터
- **포맷**: JSON · 키 불필요 · CC BY-SA 4.0
- **채우는 곳**: `anxg_vec.chunks` (`source='wikipedia_auto'`), narrative QA 검색
- **README §4.0 등급**: **B~C** (0.70)
- **모듈**: `autograph.ingestion.wikipedia_auto` + `loaders.build_chunks_auto.build_from_wikipedia`
- **누락**: 한국어판은 모델 detail 적음 → 영어판 fallback + (옵션) 나무위키 보강 (§C5).

### S7. **AI Hub 자동차 라벨링 데이터** (다운로드 형식)
- **URL**: `https://aihub.or.kr` (다운로드: `bin/aihubshell`)
- **데이터셋**: 71347 (자율주행 고장진단), 578 (부품 품질 검사 영상)
- **무엇**: 모터-감속기 / 배터리 / 도어 / 범퍼 등 부품×결함 라벨
- **포맷**: TL/VL JSON in zip/tar · **AI Hub API 키 필요** (회원가입 무료)
- **채우는 곳**: `anxg_auto.components` (Module), `anxg_vec.chunks` (`source='aihub_71347|578'`), Neo4j `:Module + CONTAINS_COMPONENT`
- **모듈**: `autograph.ingestion.aihub` + `loaders.load_auto_aihub`
- **누락**: Tier S 분류로 두지만, 키 발급은 사용자 회원가입 필요. 다운로드 승인 별도.

---

## 2. Tier A — 키 불필요, 코드 추가만 필요

> ⚠️ **상태 갱신 (2026-06-10)**: 본 Tier A 의 **A1 (NHTSA Investigations)·A4 (EPA fueleconomy)·A7 (SEC EDGAR OEM)** 은 이미 **통합·적재 완료** (각각 `events_investigations` 154 / EPA 1,426 / SEC facts 3,199 — `docs/data_inventory.md`, README §1). 아래 "신규 테이블 필요 / ~LOC 작업량" 서술은 **2026-05-28 카탈로그 시점 기준 (이제 to-do 아님)**.

### A1. **NHTSA Investigations API** (별도 endpoint 확인 필요)
- **URL 후보**: `data.transportation.gov/Automobiles/...` 의 Socrata SODA + `crashviewer.nhtsa.dot.gov/CrashAPI`
- **무엇**: 리콜 전단계 **결함 조사** history (NHTSA ODI 가 개시·종료한 조사) — recall 보다 깊은 결함 패턴
- **포맷**: SODA REST (Socrata) · 키 불필요 (rate-limit 있음, app token 권장)
- **채우는 곳**: `anxg_auto.events_investigations` (신규 테이블 필요) 또는 events_recalls 확장
- **README §4.0 등급**: **A** (0.95)
- **작업량**: ~120 LOC (recalls 패턴 복제)
- **누락 보강**: 진행 중 조사 → 향후 리콜 예측 신호

### A2. **NHTSA Technical Service Bulletins (TSB) — Socrata 다운로드**
- **URL**: `https://catalog.data.gov/dataset/nhtsas-office-of-defects-investigation-odi-technical-service-bulletins-system-tsbs-downloa`
- **무엇**: OEM 가 NHTSA 에 제출한 TSB (서비스 통신문) — 결함 패턴·수리 가이드
- **포맷**: ZIP CSV (`FLAT_TSBS.zip`) · 키 불필요
- **갱신**: 일 단위
- **채우는 곳**: `anxg_vec.chunks` (신규 source='nhtsa_tsb') — narrative 검색
- **README §4.0 등급**: **A** (0.90)
- **작업량**: ~100 LOC (CSV downloader + chunker)

### A3. **NHTSA FARS / Crash data (FTP + Crash API)**
- **URL**: `https://crashviewer.nhtsa.dot.gov/CrashAPI` + FTP CSV download
- **무엇**: 미국 치명사고 데이터 (1975~현재) — 차종별 안전성 사후 신호
- **포맷**: CSV/SAS · 키 불필요
- **채우는 곳**: 신규 `auto.events_crashes` 또는 `spec_measurements.safety.fars_*`
- **README §4.0 등급**: **A** (0.95)
- **누락 보강**: 충돌 통계 — recall 빈도가 적은 차종에도 신호 제공
- **작업량**: ~150 LOC

### A4. **EPA fueleconomy.gov 데이터**
- **URL**: `https://www.fueleconomy.gov/feg/download.shtml` (CSV/zip) + `https://www.fueleconomy.gov/feg/ws/rest/vehicle/{id}`
- **파일**: `vehicles.csv.zip` (1984~현재) + `emissions.csv.zip`
- **무엇**: US 차량 MPG (city/highway/combined), 엔진·변속기 spec, 배출가스 등급, GHG score, SmartWay
- **포맷**: CSV/XML · 키 불필요
- **채우는 곳**: `anxg_auto.spec_measurements.spec.efficiency.*`, `spec.emissions.*`, `spec.engine.*`
- **README §4.0 등급**: **A** (0.95)
- **작업량**: ~150 LOC (CSV downloader + variant 매칭)
- **누락 보강**: README §10.9 "제원 수치 EM 95%+" 직접 기여

### A5. **EPA Annual Certification Data**
- **URL**: `https://www.epa.gov/compliance-and-fuel-economy-data/annual-certification-data-vehicles-engines-and-equipment`
- **무엇**: 차량/엔진 제조사 인증 자료 — Tier 3 emissions, Federal/CARB 인증
- **포맷**: XLSX (CSV 변환 필요) · 키 불필요
- **채우는 곳**: `anxg_auto.spec_measurements.spec.emissions.tier3_*`, Standard 노드 enrichment
- **README §4.0 등급**: **A** (0.95)
- **작업량**: ~120 LOC

### A6. **DBpedia SPARQL**
- **URL**: `http://dbpedia.org/sparql`
- **무엇**: Wikipedia 추출 구조 데이터 — `dbo:Automobile`, `dbo:manufacturer`, `dbo:parentCompany`, `dbp:assembly`, `productionStartYear` 등
- **포맷**: SPARQL · 키 불필요 · User-Agent 권장
- **채우는 곳**: `auto.master_*` wikidata_qid 부족분, Neo4j Manufacturer parent 관계
- **README §4.0 등급**: **B** (0.80) — Wikipedia 파생
- **작업량**: ~120 LOC (wikidata_auto 패턴 복제)
- **누락 보강**: Wikidata 가 부족한 textual properties (model 설명·생산국·플랫폼 코드)

### A7. **SEC EDGAR Company Facts API** (글로벌 OEM)
- **URL**: `https://data.sec.gov/api/xbrl/companyfacts/CIK{0-padded-10digit}.json`
- **무엇**: Tesla / Ford / GM / Toyota ADR / Honda ADR / 등 글로벌 상장 OEM 의 XBRL 정제 데이터 (매출·생산·리콜 charge·R&D 등)
- **포맷**: JSON · 키 불필요 · User-Agent 필수 (`"App Name email@..."`)
- **Rate**: 10 req/s SEC 전체
- **채우는 곳**: `master.financial_*` (finance), `anxg_bridge.corp_entity` 강화 — cross_domain QA 의 핵심
- **README §4.0 등급**: **A** (0.95)
- **작업량**: ~80 LOC (finance `sec_client.py` 가 이미 있어 OEM CIK 리스트만 추가)
- **누락 보강**: 한국 OEM 은 KOSDAQ/KOSPI → DART 측 finance 모듈이 처리. 글로벌 OEM 만 SEC.

### A8. **Open Charge Map API** (EV)
- **URL**: `https://api.openchargemap.io/v3/poi/` (키 옵션, 무키 시 sample)
- **무엇**: 전세계 EV 충전소 위치·전력·운영자
- **포맷**: JSON/XML · 무키도 호출 가능 (live 데이터는 키 권장)
- **채우는 곳**: 신규 `auto.charging_stations`, EV 모델 컨텍스트 (subgraph)
- **README §4.0 등급**: **B** (0.80)
- **작업량**: ~100 LOC
- **누락 보강**: 전기차 모델의 인프라 신호 (현지 보급 추세)

### A9. **automotive-ontology.org / AUTO (edmcouncil/auto)** — Schema 보강
- **URL**: `https://github.com/edmcouncil/auto`
- **무엇**: W3C Automotive Ontology Community Group + EDM Council 의 OWL 온톨로지 (FIBO 패턴) — class/property SSOT
- **라이선스**: Apache 2.0
- **채우는 곳**: `ontology/auto/entities.yaml` 검증 — 외부 표준과 정렬
- **작업량**: ~40 LOC (yaml 비교·차이 보고)
- **누락 보강**: 우리 ontology 가 표준 따르는지 자동 검증

---

## 3. Tier B — 키 발급 필요, 무료

### B1. **공공데이터포털 (data.go.kr) — KOTSA 자동차결함 리콜현황 (3048950, CSV)**
- **URL**: `https://www.data.go.kr/data/3048950/fileData.do`  (구 오픈API `15089863` 은 **폐기** → CSV 파일데이터로 대체)
- **무엇**: **국내 차량 리콜현황** (제작자·차명·생산기간·리콜개시일·리콜사유) — NHTSA 가 못 보는 한국 시장
- **포맷**: **CSV 파일데이터 (cp949)** · **키 불필요** · 수동 다운로드 (로그인 불필요)
- **채우는 곳**: `anxg_auto.events_recalls` (source='datagokr_kotsa') — **941 row 적재 완료** (85% 제조사 매핑)
- **README §4.0 등급**: **A** (0.95)
- **모듈**: `loaders.load_datagokr_recalls --csv <path>` (`_iter_csv_items` cp949, 리콜번호 부재 → sha1 합성키)
- **누락**: 2023-12-31 스냅샷(실시간성 없음) · 미해석 15% 는 상용·이륜 브랜드(승용 OEM 마스터 외)

### B2. **공공데이터포털 — 국토교통부 자동차종합정보 API** (`15071233`)
- **URL**: `https://www.data.go.kr/data/15071233/openapi.do`
- **무엇**: 차량 기본정보 / 제원정보 / 이력정보 / 성능점검 — VIN 또는 차량등록번호 기반
- **포맷**: REST · **인증키 + 별도 승인 필요** (car365.go.kr 신청)
- **채우는 곳**: 차량 단위 spec 보강 (개인 차량 단위, 모집단 통계 아님)
- **누락**: 개별 차량 조회용 — 마스터 데이터 보강에는 부적합 (별도 fleet 확보 필요)

### B3. **공공데이터포털 — 한국교통안전공단 자동차종합정보 신규등록정보** (`15059401`)
- **URL**: `https://www.data.go.kr/data/15059401/openapi.do`
- **무엇**: 등록년·등록월·차종코드·지역코드별 신규등록 통계
- **포맷**: REST · 인증키 (무료)
- **채우는 곳**: 신규 `auto.market_registrations` (시계열 통계) — 시장 점유율 분석
- **README §4.0 등급**: **A** (0.95)

### B4. **KOSIS 공유서비스 (통계청)**
- **URL**: `https://kosis.kr/openapi/`
- **무엇**: 자동차 등록대수 (672건 관련 통계), 생산·수출입 시계열
- **포맷**: REST · 키 (개발계정 1000 트래픽/일 무료)
- **채우는 곳**: `master.macro_*` (finance 측에 이미 패턴) — 거시 컨텍스트
- **누락**: finance 측 `kosis_client.py` 가 이미 있음. 자동차 통계 ID 만 추가하면 됨.

### B5. **공공데이터포털 — KAMA 자동차 생산량** (`15051116`)
- **URL**: `https://www.data.go.kr/data/15051116/fileData.do`
- **무엇**: 국내 및 세계 자동차 생산량 통계 (산업통상자원부 / KAMA)
- **포맷**: 파일 다운로드 (CSV/Excel) · 로그인 무필요
- **채우는 곳**: `auto.market_production` (제조사·국가·연도 시계열)

### B6. **car365.go.kr 자동차민원 포털**
- **URL**: `https://www.car365.go.kr/`
- **무엇**: 자동차종합정보 파일자료 (배치성) — JSON/CSV bulk
- **포맷**: 다운로드 · 데이터프리존 예약 필요
- **누락**: 사용자가 KOTSA 담당자 (054-459-7264) 에 신청 절차 거쳐야 함

### B7. **국토교통부 통계누리 — 자동차등록현황**
- **URL**: `https://stat.molit.go.kr/portal/cate/statMetaView.do?hRsId=58`
- **무엇**: 월별 자동차 등록 통계 (전국·시도·차종)
- **포맷**: Excel 다운로드 · 무키
- **작업량**: 30 LOC (월별 URL 패턴 + Excel parser)

---

## 4. Tier C — 스크래핑·PDF 파싱·라이선스 주의

### C1. **자동차리콜센터 (car.go.kr) 공식 사이트** (CSV 수동 다운로드)
- **URL**: `https://www.car.go.kr/home/main.do`
- **무엇**: §B1 의 backup — API 미공개분은 web 화면에서 검색·다운로드만 가능
- **이미 코드 있음**: `autograph.ingestion.car_go_kr_recalls` 가 `data/raw/auto/car_go_kr/*.csv` 정규화 지원
- **누락**: 자동화 미적용 — 사용자가 정기적 CSV 다운로드 필요

### C2. **EuroNCAP 결과 페이지** (HTML 스크래핑)
- **URL**: `https://www.euroncap.com/en/results/`
- **무엇**: 유럽 차량 안전 등급 — 정면·측면·아이·보행자·SA(Safety Assist) 별점
- **포맷**: HTML · robots.txt 허용 · 스크래핑 가능 (rate-limit 보수)
- **채우는 곳**: `anxg_auto.spec_measurements.safety.euroncap.*`, Neo4j SAFETY_RATED_BY (Standard='EURO_NCAP')
- **README §4.0 등급**: **A** (0.95) — 공식 기관
- **작업량**: ~150 LOC (BeautifulSoup + 페이지 구조 변경 대응)
- **대안 API**: `regcheck.org.uk/api/bespokeapi.asmx` SOAP — 회원가입 무료 무비용 (UK)

### C3. **KIDI (보험개발원) 자동차 등급요율 PDF**
- **URL**: `https://www.kidi.or.kr/` 등급요율공시
- **무엇**: 자동차 사고율·수리비·도난율 → 차종별 보험요율 (결함 사후 신호)
- **포맷**: PDF 분기별 · 무키
- **작업량**: ~200 LOC (pdfplumber 등 PDF 표 추출)

### C4. **KNCAP (한국 신차 안전도 평가)** — 자동차안전연구원
- **URL**: `https://www.kncap.org/` — 평가결과 PDF
- **무엇**: 한국 차량 안전 등급 — EuroNCAP/NHTSA 외 국내 평가
- **포맷**: PDF + 별점 표
- **작업량**: ~120 LOC (PDF 파싱)

### C5. **나무위키 자동차 페이지** (라이선스 NC 주의)
- **URL**: `https://namu.wiki/w/{차종_또는_제조사}`
- **무엇**: 한국어 차량 detail — Wikipedia ko 보다 풍부 (특히 한국 모델)
- **포맷**: HTML or DB dump (Internet Archive 에서 ~월 1회 dump)
- **라이선스**: **CC BY-NC-SA 2.0 KR** — **비상업 한정**
- **갱신**: dump 비정기, archive.org/details/namuwikidumps
- **대안 도구**: `lovit/namuwikitext` (Korpora 데이터셋, 4.7 GB, 2020-10-25 마지막)
- **누락**: NC 라이선스 → 상업 서비스 시 사용 금지. 연구·내부용 OK.

---

## 5. Tier D — 상용 / 제외

### D1. **Marklines (marklines.com)**
- **상태**: 상용 paid · 학술 연구용 정식 협의 가능 (academic license)
- **카테고리**: company / customer / country / certificate / product 5-entity 글로벌 supply network
- **사용 사례**: 학술 논문 다수 (예: 2107.10609, 2305.08506) — 5-layer 다층 그래프 supply chain
- **결정**: 라이선스 비용으로 제외. supplychain-dataset-gen + Wikidata P176 + 자체 LLM P3 추출로 대체.

### D2. **JATO Dynamics**
- **상태**: 상용 paid · 시장 점유율·가격 detail
- **결정**: 제외

### D3. **Edmunds / CarAndDriver / Motor1**
- **상태**: ToS 가 스크래핑 명시 금지
- **결정**: 제외

---

## 6. PRD BOM Level × 데이터 가용성 매트릭스 (재정리)

| Level | 정의 | 가용 소스 (활용도 순) | 현재 채워짐? |
|---|---|---|---|
| **L0 Manufacturer** | 제조사 | Wikidata, NHTSA vPIC MakeId | ✅ |
| **L1 VehicleModel** | 모델 | NHTSA vPIC, Wikidata, Wikipedia, DBpedia | ✅ |
| **L2 Trim/Year (Variant)** | 트림·연식 | NHTSA vPIC GetModelsForMakeYear, Canadian Specs | ✅ |
| **L3 System** | 시스템 (powertrain, brake, body…) | ontology system_taxonomy.yaml (SSOT) | ✅ (derived `CONTAINS_SYSTEM` 완료) |
| **L4 Module** | 모듈 (Motor-Reducer, Battery Pack, Door…) | NHTSA component taxonomy 176 + AI-Hub 578 22 + manual supplier seed 18 + AI-Hub 71347 4 = **`anxg_auto.components` 220 row 전부 L4** | ⚠️ 부분 — L4 coverage **63.7%** (60% 목표 over). Wikidata P176 staging 은 rate-limit (429) 로 0 row |
| **L5 Part** | 부품 (셀·센서·인플레이터) | 리콜 본문 LLM 추출만 (P3 RECALL_OF) | ❌ 매우 sparse — Neo4j `:Part` 노드 **0**. 리콜·LLM 출처에서만 자연 발생 |
| **L6 Material/Process** | 소재·공법 | (부분 적재 — 곁가지) USGS MCS + materials_seed manual | ⚠️ 부분 — `:Material` 6 / `:Mineral` 5 / `DERIVED_FROM` 17 / `MADE_OF` 8 (`autograph.md §2.5.4`). Wikidata 자동 보강은 비활성 (BACKLOG L6-1) |

---

## 7. PRD 출처 등급 × 현재 구현 매트릭스

| 등급 | confidence | 적용 소스 | 통합 상태 |
|---|---|---|---|
| **A+** 0.95+ (verified) | 수동 검토 | 매뉴얼 seed, supplier_seed.yaml | ✅ |
| **A** 0.95 | NHTSA recalls/vPIC/NCAP, KNCAP, EuroNCAP, KAMA, DART | ✅ NHTSA 만. KNCAP/EuroNCAP 미통합 |
| **B** 0.80 | Wikidata, EPA, 매뉴얼/브로셔 | ✅ Wikidata. EPA 미통합 (§A4, A5) |
| **B~C** 0.70 | Wikipedia, DBpedia | ✅ Wikipedia (P3 완료). DBpedia 미통합 (§A6) |
| **C** 0.50 | LLM P3 추출 | ✅ P3 staging + cross_validate |
| **C-** 0.40 | 커뮤니티 / 비공식 | ❌ 사용 안 함 (PRD 정책) |

---

## 8. 관련 학술 논문 (조사 결과)

| 논문 | 핵심 기여 | 본 프로젝트와 관계 |
|---|---|---|
| **arXiv 2411.19539** — *Knowledge Management for Automobile Failure Analysis Using Graph RAG* (IEEE BigData 2024) | OEM 결함 분석에 GraphRAG 적용. ROUGE F1 +157.6% 개선 보고. 자체 Q&A 데이터셋. 코드 비공개. | **직접 유사** — failure analysis 가 우리 vehicle_recall 분기와 같은 use case |
| **arXiv 2504.01248** — *Automated Factual Benchmarking for In-Car Conversational Systems using LLMs* | 차량 대화형 시스템의 factual benchmarking 자동화. | gold QA 생성 자동화 참고 |
| **arXiv 2012.02558** — *Pre-trained language models as knowledge bases for Automotive Complaint Analysis* | NHTSA ODI complaints 로 PLM 도메인 적응. | 우리 P3 추출의 baseline |
| **arXiv 2107.10609** — *Data Considerations in Graph Representation Learning for Supply Chain Networks* | Marklines 데이터로 글로벌 자동차 공급망 그래프 representation learning. SOTA on link prediction. | 우리 SUPPLIED_BY 평가의 reference |
| **arXiv 2305.08506** — *A Knowledge Graph Perspective on Supply Chain Resilience* | KG 기반 공급망 회복력 분석 framework. | anxg_bridge.corp_entity 확장 방향 |
| **MDPI Electronics 2025** — *Document GraphRAG for Manufacturing* | 제조 도메인 GraphRAG. KG + RAG 결합으로 retrieval robustness. | Hybrid adapter 의 baseline |
| **arXiv 2409.20010** — *Customized Domain-centric KG Construction with LLMs* (자동차 전기 시스템) | 자동차 전기 시스템 도메인 KG 자동 구축. GraphGPT/REBEL 대비 우수. | 우리 LLM P3 추출의 직접 reference |
| **ACM AIAA 2024** — *NER of New Energy Vehicle Parts via LLM* | LFRC (LLM+Fine-tune+Reflective CoT) — 신에너지차 부품 NER | EV 부품 추출 strategy |
| **PMC 2024** — *Chinese NER for Automobile Fault Texts* | external context retrieving + adversarial training | recall text 정규화 patterns |

---

## 9. Open Datasets (재사용 가능)

### 9.1 봉인된 그래프 데이터셋

| 데이터셋 | 라이선스 | 규모 | 형태 | 활용 |
|---|---|---|---|---|
| **wey-gu/supplychain-dataset-gen** | Apache 2.0 | 40 vertices, 62 edges (sample) | NebulaGraph CSV | 우리 SUPPLIED_BY seed schema 검증 |
| **edmcouncil/auto** OWL ontology | Apache 2.0 | ~수백 클래스 | OWL/RDF | `ontology/auto/*.yaml` 검증 |

### 9.2 코퍼스 / NLP

| 데이터셋 | 라이선스 | 규모 | 활용 |
|---|---|---|---|
| **lovit/namuwikitext** | CC BY-NC-SA 2.0 KR | 4.7 GB / 31.2M lines | 한국어 자동차 narrative 청크 (비상업 한정) |
| **Internet Archive 나무위키 dumps** | CC BY-NC-SA 2.0 KR | 정기 dump | 위 + raw HTML |
| **Salesforce/wikitext** (Hugging Face) | CC BY-SA 3.0 | 영어 일반 | 자동차 fine-tune 부적합 (general) |
| **Kaggle: nhtsa/safety-recalls** | NHTSA public | 1967~현재 | 우리 NHTSA recalls API 와 중복 — skip |

---

## 10. 데이터 GAP 분석 (README §11.2 BOM 가용성 매트릭스 기준)

### 🟢 충분 (현재 인프라로 채워짐)
- **L0 Manufacturer**: NHTSA + Wikidata 가 글로벌 커버. KAMA 가 한국 보강.
- **L1 VehicleModel**: NHTSA vPIC + Wikipedia. ko/en 양면.
- **L2 Variant**: NHTSA vPIC + Canadian Specs. US 한정이지만 한국 OEM 의 글로벌 변형 다수 커버.
- **L3 System**: ontology SSOT + derived CONTAINS_SYSTEM. 자체 분류 안정.

### 🟡 부분 부족
- **L4 Module**: AI-Hub 71347/578 만 deterministic. 일부 카테고리 (Motor-Reducer / Battery / Door / Bumper …) 만. 나머지는 LLM P3 추출 의존 → confidence 0.50~0.80 가 다수.
  - **Gap 해소**: Wikidata P176 자동 추출 확장 (§S5 staging 완료) + DBpedia P527 (§A6) + EPA 인증 데이터 (§A5) 보완.
- **시계열 / 시점 메타**: README §3.7 의 `snapshot_year` 가 NHTSA recalls 에는 잘 채워지지만 manufacturer/model 마스터에는 sparse.
  - **Gap 해소**: KOSIS 신규등록 통계 (§B4) + 국토부 통계누리 (§B7) 가 시계열 모집단 제공.
- **안전 등급**: NHTSA NCAP 만 (US). EuroNCAP / KNCAP 미통합.
  - **Gap 해소**: §C2 EuroNCAP, §C4 KNCAP 스크래핑.

### 🔴 큰 부족
- **L5 Part**: PRD MVP 제외 (post-MVP). 리콜 LLM 추출만 진입.
- **한국 시장 리콜**: API 키 발급 전까지 manual CSV (§B1, §C1).
- **자기인증 / 형식승인**: KATRI 키 부재 — README §4 에 `events.certifications` 명시되지만 스키마·loader 모두 미구현.
- **부품사 IR**: 개별 부품사 (현대모비스, 만도, 한온시스템 …) IR 본문 미수집. DART 측에 finance 가 있지만 자동차 도메인 cross-reference 안 됨.
- **글로벌 OEM 재무**: SEC EDGAR 미통합 (§A7) — Tesla/Ford/GM/Toyota cross_domain QA 가 한국 OEM 한정.

### 📊 평가 데이터
- **Cross-Domain QA L1~L4 층화 라벨**: gold dataset 에 분류 라벨 미포함 — 사람 라벨링 필요.
- **multi-hop 비율**: gold 총 165건 (finance 30/auto 56/cross 49/ip 30) 적재됐으나, multi-hop·cross-domain 변별 셀은 여전히 보강 필요 (`docs/research/thesis_hybrid_routing.md` §4).

---

## 11. 결론 및 우선순위 권장 (재정리)

### 즉시 가능 (Tier A — 코드만)
1. **§A4 EPA fueleconomy.gov** — `spec.efficiency.*` + `spec.engine.*` 풍부화. README §10.9 직격.
2. **§A1 NHTSA Investigations** — 결함 시계열 깊이 보강.
3. **§A2 NHTSA TSB Socrata** — narrative 청크 추가.
4. **§A7 SEC EDGAR (글로벌 OEM)** — cross_domain QA 의 글로벌 확장.
5. **§A6 DBpedia** — Wikidata 부족분 보완.

### 키 발급 후 가능 (Tier B — 사용자 1회 회원가입)
6. **§B1 국토부 자동차 리콜정보 API** — 한국 시장 리콜 진입.
7. **§B4 KOSIS 자동차 통계** — 시장 시계열.

### 스크래핑 (Tier C — 보수적 + 라이선스 확인)
8. **§C2 EuroNCAP** — 유럽 안전 등급.
9. **§C4 KNCAP** — 한국 안전 등급.
10. **§C5 나무위키** (NC 한정) — 한국어 narrative 풍부.

### 사용자 직접 액션 필요
- **AI Hub 키** 발급 + 데이터셋 다운로드 승인 (S7).
- **car365.go.kr 데이터프리존** 예약 + 승인 (§B6).
- **KIDI 등급요율** 분기별 PDF 다운 (§C3).

---

## 12. IPGraph 도메인 데이터 소스 (보조축 — README §11.1 Phase C + §10.15~17 DoD)

> 2026-06-01 신설. 상세 설계·온톨로지·gold QA SSOT 는 [docs/ipgraph.md](./ipgraph.md). 본 §는 데이터 소스 후보 카탈로그 분담만.

### IP-S1. **CPC 분류 체계 bulk** (USPTO + EPO)

| 항목 | 내용 |
|---|---|
| 출처 | USPTO Bulk Data — CPC Master Classification File (XML) / EPO Open Patent Services |
| 라이선스 | 공공 |
| 인증 | 불필요 |
| 등급 | **A** (0.95) — 정식 분류 계층 (section A~H+Y → class → subclass → maingroup → subgroup, depth ≥ 4) |
| 채울 README 항목 | README §10.15~17 + §11.1 Phase C (ip 보조축) — `anxg_ip.cpc_scheme` + Neo4j `CPCCode/SUBCLASS_OF` |
| 작업 상태 | (예정) — 무인증 즉시 가능, 작업 순서 1번 |
| 미수집 사유 | `src/ipgraph/*` 실제 코드 미머지 |

### IP-S2. **USPTO Open Data Portal (PatentsView 후속)**

| 항목 | 내용 |
|---|---|
| 출처 | data.uspto.gov — **PatentsView REST 종료 (2026-03-20)** 후 ODP bulk dataset + Transition Guide |
| 라이선스 | 공공 (US Gov) |
| 인증 | 무인증 (bulk dataset) |
| 등급 | **A** (0.95) — 공식 특허청. 미국 특허 + 인용 + assignee 정규화 |
| 채울 README 항목 | README §10.15~17 + §11.1 Phase C (ip 보조축) — `anxg_ip.patents` (US) + `anxg_ip.citations` + `anxg_ip.assignee_corp_map` (strong 매칭) |
| 작업 상태 | (예정) — REST 가정 코드 모두 폐기, bulk dataset 기반 ingestion |
| 미수집 사유 | REST 종료로 인한 ingestion 전략 전환 필요. 작업 순서 2번 |

### IP-A1. **OpenAlex API**

| 항목 | 내용 |
|---|---|
| 출처 | api.openalex.org — 학술 논문 / 특허 / works 통합 |
| 라이선스 | CC0 |
| 인증 | 불필요 (mailto 헤더 권장, rate limit) |
| 등급 | **A** (0.95) — 글로벌·연구 확장. 특허는 부분 커버 |
| 채울 README 항목 | README §10.15~17 + §11.1 Phase C (ip 보조축) 옵션 — `anxg_ip.works` (R&D ↔ 특허 cross-reference 보강) |
| 작업 상태 | (예정, 옵션) |
| 미수집 사유 | 핵심 ingestion (CPC + USPTO ODP + KIPRIS) 후 보강 |

### IP-B1. **KIPRIS Open API (공공데이터포털)**

| 항목 | 내용 |
|---|---|
| 출처 | 공공데이터포털 — 한국특허정보원 KIPRIS Open API |
| 라이선스 | 공공 (검색·서지 무료 / **본문·대량은 KIPRISPLUS 회원 / 일부 비공개**) |
| 인증 | `KIPRIS_API_KEY` (공공데이터포털 발급) |
| 등급 | **A** (0.95) — 한국 특허·출원 |
| 채울 README 항목 | README §10.15~17 + §11.1 Phase C (ip 보조축) — `anxg_ip.patents` (KR) + assignee→corp_code 매칭 (현대차/기아/삼성SDI/LG엔솔/현대모비스 우선) |
| 작업 상태 | (예정) — 키 발급 + `src/autonexusgraph/ingestion/_license.py` 에 KIPRIS 게이트 추가 (commit `b70527a` IR/뉴스룸 license-gate 패턴 재사용) |
| 미수집 사유 | 키 발급 + 라이선스 게이트 |

---

## 부록: 검색 자료 (출처)

본 문서 작성에 참조한 공식 페이지 및 학술 논문:

### 공식·정부 페이지
- [NHTSA Datasets and APIs](https://www.nhtsa.gov/nhtsa-datasets-and-apis)
- [NHTSA vPIC](https://vpic.nhtsa.dot.gov/api/)
- [api.nhtsa.gov 정책](https://api.nhtsa.gov/)
- [NHTSA TSB Socrata 데이터셋](https://catalog.data.gov/dataset/nhtsas-office-of-defects-investigation-odi-technical-service-bulletins-system-tsbs-downloa)
- [NHTSA FARS](https://www.nhtsa.gov/research-data/fatality-analysis-reporting-system-fars)
- [Crash Viewer API](https://crashviewer.nhtsa.dot.gov/CrashAPI)
- [fueleconomy.gov Download](https://www.fueleconomy.gov/feg/download.shtml)
- [fueleconomy.gov Web Services](https://www.fueleconomy.gov/feg/ws/)
- [EPA Annual Certification Data](https://www.epa.gov/compliance-and-fuel-economy-data/annual-certification-data-vehicles-engines-and-equipment)
- [SEC EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)
- [KOTSA_자동차결함 리콜현황 (CSV — 구 15089863 API 폐기)](https://www.data.go.kr/data/3048950/fileData.do)
- [국토교통부_자동차종합정보 API](https://www.data.go.kr/data/15071233/openapi.do)
- [KOSIS 공유서비스](https://kosis.kr/openapi/)
- [KOTSA TS 데이터 개방센터](https://www.kotsa.or.kr/portal/contents.do?menuCode=03030200)
- [무공해차 통합누리집 ev.or.kr](https://ev.or.kr/)
- [국토교통부 통계누리 자동차등록](https://stat.molit.go.kr/portal/cate/statMetaView.do?hRsId=58)
- [KAICA 한국자동차산업협동조합](https://www.kaica.or.kr/)
- [KAMA 한국자동차산업협회](https://www.kama.or.kr/)
- [Automotive Ontology Working Group (W3C)](https://www.automotive-ontology.org/)
- [edmcouncil/auto OWL ontology](https://github.com/edmcouncil/auto)
- [Open Charge Map API](https://openchargemap.org/site/develop/api)

### 학술 논문 / 데이터셋
- [arXiv 2411.19539 — Graph RAG for Automobile Failure Analysis](https://arxiv.org/abs/2411.19539)
- [arXiv 2504.01248 — Factual Benchmarking for In-Car LLMs](https://arxiv.org/abs/2504.01248)
- [arXiv 2012.02558 — PLMs for Automotive Complaint Analysis](https://arxiv.org/pdf/2012.02558)
- [arXiv 2107.10609 — Supply Chain Graph Representation Learning](https://arxiv.org/pdf/2107.10609)
- [arXiv 2305.08506 — KG for Supply Chain Resilience](https://arxiv.org/pdf/2305.08506)
- [MDPI Electronics 2025 — Document GraphRAG for Manufacturing](https://www.mdpi.com/2079-9292/14/11/2102)
- [arXiv 2409.20010 — Domain-centric KG with LLMs (Automotive Electrical)](https://arxiv.org/pdf/2409.20010)
- [ACM AIAA 2024 — NER of NEV Parts via LLM](https://dl.acm.org/doi/10.1145/3700523.3700532)
- [PMC 2024 — Chinese NER for Auto Fault Texts](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC11854445/)
- [wey-gu/supplychain-dataset-gen (Apache 2.0)](https://github.com/wey-gu/supplychain-dataset-gen)
- [lovit/namuwikitext (CC BY-NC-SA 2.0 KR)](https://github.com/lovit/namuwikitext)
- [나무위키 DB Dumps (Internet Archive)](https://archive.org/details/namuwikidumps)

## 13. 신뢰도 등급 + 도메인별 소스 상세 (README §4 migration)

> README §4 에서 이동(2026-06-11) — 출처 신뢰도 거버넌스 + 도메인별 소스 목록.


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
| KOSIS 광공업동향 | **A** | 0.95 | `anxg_macro.kosis_series` |
| Wikidata | **B (중간)** | 0.80 | 글로벌 ID 매핑, `MANUFACTURES` (보조) |
| DART 사업보고서 III. 생산·설비 (가동률) | **B** | 0.80 | `MANUFACTURED_AT` (시점) |
| Wikipedia | **B~C** | 0.70 | 설명 문서, 보조 근거 |
| 부품사 IR (공식 공시) | **B** | 0.75 | `SUPPLIED_BY` (후보) |
| 매뉴얼 / 브로셔 | **B** | 0.75 | `CONTAINS_*` (시스템·모듈) |
| KAMP 제조AI 데이터셋 (data.go.kr 15089213) | **B (익명)** | 0.80 | `anxg_auto.process_metrics` (회사 비귀속) |
| AI Hub 제조 멀티모달·품질 | **B (익명)** | 0.80 | `anxg_vec.chunks` + ProcessStep 통계 속성 (회사 비귀속) |
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

§4.0 정적 등급표는 **데이터셋 단위 할당값**이다. 이와 별개로, 합성/LLM 등 **C 등급 출처의 row 도 외부 A/B 출처 시그널이 충분히 누적되면 row 단위로 0.80 (B) 까지 승급**할 수 있다 — 현 단계 운영 대상은 **`anxg_auto.processes` (산단공 합성 15151075, C 0.50) 단독**, 410 공정명 중 외부 매칭 가능한 row 한정 (예상 격상률 15~30%, 70~85% 는 C 유지).

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
- 동적 격상: `src/autograph/extractors/process_confidence.py` — `compute()` 수식/clip/grade **구현 완료 + tested** (운영 wire-up 은 BACKLOG PG-3)
- staging: `auto.staging_process_signals` (`infra/postgres/init/16_process_signals.sql`)
- 운영: `scripts/upgrade_processes_confidence.py` (1회 풀런 ≤ $2 + GPU 1분, idempotent)

---

| 데이터 | 출처 | 라이선스 | 적재 위치 |
|---|---|---|---|
| 사업보고서·공시 | DART Open API | 공공 | `data/raw/dart_bulk/` → `anxg_vec.chunks` + `anxg_fin.filings` |
| 재무제표 (XBRL) | DART | 공공 | `anxg_fin.financials` |
| 지배구조 (자회사·임원·최대주주) | DART | 공공 | Neo4j SUBSIDIARY_OF / EXECUTIVE_OF / MAJOR_SHAREHOLDER_OF |
| 상장사 마스터 | KRX | 공공 | `anxg_master.companies` |
| 거시지표 | 한국은행 ECOS | 공공 | `anxg_macro.series` |
| Wikipedia 본문·Infobox | ko.wikipedia.org | CC BY-SA | `anxg_wiki.wikipedia_pages` + `anxg_vec.chunks` (section=wikipedia_ko) |
| Wikidata 글로벌 ID·CEO·자회사 | query.wikidata.org | CC0 | `anxg_wiki.wikidata_facts` + `anxg_master.entity_map` |
| 연합뉴스 RSS | 연합뉴스 | 저작권 | `anxg_news.articles` (메타+요약만) |
| SEC EDGAR (ADR) | sec.gov | 공공 | `anxg_sec.filings` |
| GLEIF LEI | gleif.org | CC BY 4.0 | `anxg_sec.lei` + `anxg_master.entity_map` |
| KCGS ESG 등급 | cgs.or.kr | 회원 (수동) | `anxg_esg.ratings` + Neo4j Company 속성 |
| 공정위 기업집단 | data.go.kr | 공공 | (키 확보 후) Neo4j Group + BELONGS_TO_GROUP |
| KOSIS 산업 통계 | kosis.kr | 공공 | (키 확보 후) `anxg_macro.kosis_series` |
| LAW.go.kr 법령 | open.law.go.kr | 공공 | (키 확보 후) `anxg_law.laws` |
| GLEIF ↔ OpenCorporates 관계 파일 | gleif.org (LEI↔OC 오픈소스 매핑) | CC0 / 오픈 | `anxg_sec.lei` + `anxg_master.entity_map` (LEI 매칭 보강) |
| 글로벌 법인 식별자 (145 관할권 2.3억+) | OpenCorporates API | 오픈 (share-alike — `_license.py` 게이트) | `anxg_master.entity_map` (비상장 부품사·자회사 보강) |

**수집 범위 (1차):** 코스피 200 + 코스닥 100 약 300개사, 최근 3개 회계연도.
**제조 데이터 끝까지 채움 (wired, partial — 키 확보 대기):**
- `DATA_GO_KR_API_KEY` → 팩토리온 [15087611](https://www.data.go.kr/data/15087611/openapi.do) (ingestion `factoryon_registry.py` + loader `load_factoryon.py` → `anxg_auto.factoryon_registry` PG `24_auto_factoryon.sql`. `make load-factoryon`)
- 자동차 리콜 [3048950 (CSV)](https://www.data.go.kr/data/3048950/fileData.do) (구 오픈API 15089863 폐기) + 검사 [15155857](https://www.data.go.kr/data/15155857/fileData.do) (ingestion + `load_datagokr_*.py`)
- DART 사업보고서 **가동률 표** 파서 — `dart_production_parser._parse_utilization_table` → `anxg_auto.plant_utilization` PG 적재 (`load_dart_production.py:199`). 완료.
- KOSIS 산업 통계 — `kosis_client.py` + `load_kosis_industry.py` → `anxg_macro.kosis_series` (`make load-kosis`). KOSIS_API_KEY 필요.
- Wikidata 배터리 셀 chem (cathode) — `wikidata_cell_chem.py` (CC0, 무인증). materials_seed.yaml 의 manual seed 보강. **회사단위 셀↔OEM 소싱은 grade C candidate 정직 표기** (§2.3).

모두 정형 — LLM 0%. 라이선스: `public_domain` / `kogl_type1` (KOSIS / DATA_GO_KR).
**범위 외 (Out-of-Scope):** 빅카인즈 본문, 나무위키(CC BY-NC-SA), 종목토론방, LinkedIn, Twitter.

### AutoGraph 데이터 소스

| 데이터 | 출처 | 라이선스 | 인증 | 적재 위치 |
|---|---|---|---|---|
| 차량 마스터·제원 (전 세계 vPIC) | NHTSA vPIC API | 공공 (US Gov) | 불필요 | `auto.master_*` |
| 리콜 캠페인 | NHTSA Recalls API | 공공 | 불필요 | `anxg_auto.events_recalls` + Neo4j Recall |
| 결함 신고 | NHTSA Complaints API | 공공 | 불필요 | `anxg_auto.events_complaints` + `anxg_vec.chunks` |
| 제조사·모델·공급사 QID·LEI·사업자번호 | Wikidata SPARQL | CC0 | 불필요 (rate limit) | `auto.master_*` + `anxg_bridge.corp_entity` |
| 자동차 리콜정보 (한국) | data.go.kr [3048950 (CSV)](https://www.data.go.kr/data/3048950/fileData.do) | 공공 | (무인증 CSV) | `anxg_auto.events_recalls` 941행 적재 (CSV 전량) |
| 자동차검사관리 수리검사내역 (사고·침수·도난 차량 검사) | data.go.kr [15155857](https://www.data.go.kr/data/15155857/fileData.do) (파일 다운) | 공공 | 불필요 (파일) | `data/raw/datagokr/` → (적재 후) `anxg_auto.events_inspections` |
| 시험인증 (KATRI / 부품 인증) | bigdata-tic.kr Open API | 공공 (회원) | OAuth `BIGDATA_TIC_CLIENT_ID/SECRET` | (키 확보 후) `auto.cert_*` |
| 안전등급 (NCAP) | NHTSA SafetyRatings API | 공공 (US Gov) | 불필요 | `anxg_auto.spec_measurements` (safety.ncap.* / safety.feature.*) + Neo4j `(:VehicleVariant)-[:SAFETY_RATED_BY]->(:Standard {code:'NCAP_US'})` |
| ODI 결함 조사 (리콜 전단계) | NHTSA Investigations bulk | 공공 (US Gov) | 불필요 | `anxg_auto.events_investigations` + Neo4j `(:VehicleModel)-[:INVESTIGATED_BY]->(:Investigation)` |
| 차량 연비·엔진·배출 spec | EPA fueleconomy.gov bulk CSV | 공공 (US Gov) | 불필요 | `anxg_auto.spec_measurements` (spec.efficiency.* / spec.engine.* / spec.emissions.*) |
| 글로벌 OEM 재무 (Ford/GM/Stellantis/Toyota/Honda/Tesla …) | SEC EDGAR Company Facts (XBRL) | 공공 | UA 필수 | `anxg_auto.oem_financials_sec` + `anxg_bridge.corp_entity.sec_cik` 강화 |
| 제조사 통신문 / TSB | NHTSA Manufacturer Communications (수동 zip) | 공공 (US Gov) | 불필요 | `anxg_vec.chunks` (source='nhtsa_tsb') |
| 안전등급 (KNCAP) | car.go.kr (수동 / 별도 API) | 공공 | (지정 채널) | (후속) `anxg_auto.spec_measurements` + `:Standard {code:'KNCAP'}` |
| Euro NCAP / IIHS (옵션) | euroncap.com / iihs.org | 공공 (사용 약관) | 불필요 | (후속) `anxg_auto.spec_measurements` + `:Standard` (Euro NCAP / IIHS TSP) |
| 제조 공정·생산능력 (제조 도메인) | DART 사업보고서 본문 파서 | 공공 | DART 키 (finance 와 공유) | `auto.production_*` (LLM 0% — 정규식 + 표 파서) |
| 산단공 합성 공정데이터 (15151075) | data.go.kr (수동 CSV) | 공공 | 불필요 (파일) | `anxg_auto.processes` + Neo4j `:Process` 410 / `:ProcessStep` 550 / `PRECEDES`·`INSTANTIATES` (BoP routing, grade C). SSOT [docs/process_graph.md](./docs/process_graph.md) |
| 공장 등록정보 (15087611) — 회사·공장번호·산단별 조회 | data.go.kr 팩토리온 (`apis.data.go.kr/B550624`) | 공공 | `DATA_GO_KR_API_KEY` (작동 확인) | `anxg_auto.factoryon_registry` 90행 적재 (OEM 5사 + tier-1) → MANUFACTURED_AT 보강 |

> 인증 키 부재 시 ingestion 은 graceful skip — 코드 변경 없이 `.env` 만 채우면 활성화.

### IPGraph 데이터 소스 (예정 — 본 PR outline · 후속 PR ingestion)

> 상세 설계·온톨로지·gold QA SSOT 는 [docs/ipgraph.md](./docs/ipgraph.md). 배터리·소재 표는 본 절 아님 — auto 의 L5/L6 확장 (다음 표).

| 데이터 | 출처 | 라이선스 | 인증 | 적재 위치 | 상태 |
|---|---|---|---|---|---|
| 한국 특허·출원 | KIPRIS Open API (공공데이터포털) | 공공 (검색·서지 무료 / **본문·대량은 KIPRISPLUS 회원·일부 비공개**) | `KIPRIS_API_KEY` | `anxg_ip.patents` + Neo4j Patent | (scaffold, 보조) |
| 미국 특허·인용·assignee 정규화 | **USPTO Open Data Portal (data.uspto.gov)** — PatentsView 후속 | 공공 (US Gov) | **이관 완료 (2026-03-20)** — `search.patentsview.org` REST 종료(410 Gone), **ODP bulk dataset + Transition Guide** 채택 | `anxg_ip.patents` + `anxg_ip.citations` | (scaffold, 보조) |
| CPC 분류 체계 (계층 depth ≥ 4) | CPC scheme bulk (USPTO / EPO) | 공공 | 불필요 | `anxg_ip.cpc_scheme` + Neo4j CPCCode/SUBCLASS_OF | ✅ **10,695 row 적재** (§1 IPGraph 현황표) |
| 글로벌 논문·연구 (assignee↔institution↔author) | OpenAlex API | CC0 | **무료 키 필요 (하루 10만 크레딧, 2025-02 이후)** | `anxg_ip.works` + Neo4j Work/Institution/Author | ✅ **629 row 적재** — 특허×논문 cross 승격은 institution↔corp_entity 매핑 후속 |

### 배터리·소재 보완 (auto 의 L5/L6 확장 — 예정)

> ip 도메인이 아님. `(:Module {배터리팩})-[:CONTAINS_MODULE]->(:Cell)-[:MADE_OF]->(:Material {NCM811})-[:DERIVED_FROM]->(:Mineral {Ni})` BOM 하향. 상세는 [docs/autograph.md](./docs/autograph.md) §2.5.4.

| 데이터 | 출처 | 라이선스 | 적재 위치 | 상태 |
|---|---|---|---|---|
| 배터리 화학조성 (NCM/LFP 등 셀 chem) | Wikidata + 셀 제조사 공개 IR PDF | CC0 / 공공 | `auto.master_materials` | (예정) |
| 핵심광물 (Li/Ni/Co/Mn/흑연) 세계·미국 통계 | USGS Mineral Commodity Summaries (MCS 2025 PDF) | 공공 (US Gov) | `anxg_auto.master_minerals` + Neo4j `:Mineral` / `:Material` / `:DERIVED_FROM` | ✅ **2024 estimate 5종 적재** — Li/Ni/Co/Mn/Graphite, 6 Material × 5 Mineral × 17 DERIVED_FROM (7-key 100%) |
| 광물 수입 통계 (한국) | 관세청 무역통계 / 무역협회 K-stat | 공공 | `macro.trade_minerals` | (예정) |
| 회사단위 소싱 (셀 ↔ OEM) | 공개 IR 부분 — grade C candidate | 공공 (sparse — 정직 표기) | `anxg_auto.staging_relations` (candidate) | (예정, 한계 명시) |

### EV 충전 인프라 (auto 의 EV 확장 — 예정)

> Operator(운영기관) → `anxg_bridge.corp_entity` 로 "충전 인프라 운영사 ↔ 재무" cross-domain. 이미 보유한 `DATA_GO_KR_API_KEY` 재사용.

| 데이터 | 출처 | 라이선스 | 인증 | 적재 위치 | 상태 |
|---|---|---|---|---|---|
| 전국 충전소 위치·운영정보 (운영기관·충전기타입·충전용량·설치년도) | data.go.kr 한국환경공단 (`apis.data.go.kr/B552584/EvCharger`) | 공공 | `DATA_GO_KR_API_KEY` | `anxg_auto.ev_chargers` + Neo4j `:ChargingStation` | (예정) |
| 지역별 급속충전기 설치현황·실제 이용량 | data.go.kr 한국에너지공단 (`apis.data.go.kr/B553530/TRANSPORTATION/ELECTRIC_CHARGING`) | 공공 | `DATA_GO_KR_API_KEY` | `anxg_auto.ev_charger_usage` | (예정) |

---

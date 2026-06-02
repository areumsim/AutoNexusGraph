# 데이터 파이프라인 운영 가이드

> **인용 규약**: 본 문서의 `PRD §6.5` 등 인용은 **구 PRD 표기** — README v3.0 통합 후 README §3.6 (4-Pass + Bridge Pass) / §4 (데이터 소스) 가 새 SSOT.

본 문서는 AutoNexusGraph 의 raw → processed → DB 3-tier 멱등 파이프라인을 단계별로 안내한다.
각 단계는 앞 단계의 raw 가 있다면 언제든 재실행 가능 (멱등). 도중 끊겨도 `state/` 의 done/failed
체크포인트로 이어받기. 모든 적재 PG `INSERT ... ON CONFLICT DO UPDATE`, Neo4j `MERGE`.

## 전체 디렉토리 표준

```
data/
├── raw/                  ← 외부에서 받은 원본 (수정·삭제 금지)
│   ├── dart/             — corp_codes, filings, financials, structural
│   ├── krx/              — top_kospi200.csv, top_kosdaq100.csv
│   ├── wikidata/         — candidates.json, entities/<qid>.json
│   ├── wikipedia/ko/<corp_code>/ — meta.json, page.html, summary.json, infobox.json
│   ├── news/<feed>/<YYYYMMDD>/<hash>.json
│   ├── sec/<cik>/        — submissions.json
│   ├── gleif/            — kr_records.json
│   ├── kcgs/             — sample/template.csv, <year>/ratings.csv, press/<no>/
│   └── fss/, ftc/, kosis/, kipris/, law/  — 키 확보 후
│
├── processed/            ← 파싱·정규화 결과. raw 만 있으면 언제든 재생성.
│   ├── entity_resolution/
│   ├── chunks/           — 청킹 결과 (embedding NULL)
│   └── extracted/        — P3 LLM 추출 결과 (후속)
│
└── state/                ← 진행 체크포인트
    ├── ingest/<source>.done.jsonl
    └── ingest/<source>.failed.jsonl
```

## Step 별 묶음 target (Makefile)

| Step | 묶음 target | 내용 |
|---|---|---|
| 1 | `make ingest-step1` | DART corp 마스터 + KRX 상장사 + targets 매칭 |
| 2 | `make ingest-step2` | DART 사업/반기/분기 보고서 + 재무 XBRL + 정형 지배구조 |
| 3 | `make ingest-step3` | Wikidata SPARQL 한국 상장사 + 회사별 entity 상세 |
| 4 | `make ingest-step4` | Wikipedia 한국어 페이지 + Infobox |
| 5 | `make ingest-step5` | FTC 기업집단 + KOSIS + FSS (키 필요) |
| 6 | `make ingest-step6` | 연합뉴스 RSS |
| 7 | `make ingest-step7` | SEC EDGAR + GLEIF + KIPRIS + LAW |
| 8 | `make ingest-step8` | KCGS 보도자료 모니터 + 수동 CSV 적재 가이드 |

각 ingest 스크립트는 `--resume` / `--retry-failed` / `--force` / `--limit N` / `--dry-run` 옵션을 표준화.

## 추출 4-pass (README §3.6 4-Pass + Bridge Pass)

수집·청크·임베딩이 끝나면 다음 4-pass 로 관계·수치를 추출한다. P1/P2 는 deterministic
(0% LLM) — 항상 안전. P3 는 selective LLM — 비용 게이트 통과 후. P4 는 P3 결과를 P2 SSOT 로
cross-validate.

| Pass | 명령 | 입력 | 산출 | LLM |
|---|---|---|---|---|
| P1 | `make load-financials` | DART XBRL JSONL | `fin.financials` | 0% |
| P2 | `make load-graph-structural` | DART 지배구조 JSON | Neo4j SUBSIDIARY_OF / EXECUTIVE_OF / MAJOR_SHAREHOLDER_OF | 0% |
| P3 | `make p3-extract-dry` → `make p3-extract` | 사업보고서 본문 청크 | `data/processed/extracted/<corp>/<rcept>.jsonl` | 100% (selective 53%↓) |
| P4 | `make p4-load` | P3 JSONL | Neo4j PARTNER_OF / COMPETES_WITH / INVESTED_IN / PRODUCES (source=`p3_llm`) | 보조 (검증) |

**P3 비용 가드 (`extract_business_report_relations.py`):**
- `--dry-run` 이 비용 추정만 (LLM 호출 0)
- `--max-cost <USD>` HARD limit (기본 1.0 — Makefile)
- `--top-by-market-cap N` 으로 회사 수 제한 (기본 30)
- 청크당 결과는 idempotent (`data/processed/extracted/.../jsonl` 이미 있으면 skip — `--force` 로 재추출)

**P4 검증 분기 (`validator.py`):**
- `confidence >= 0.70` + P2 충돌 없음 → Neo4j MERGE
- `0.50 <= confidence < 0.70` → `data/reports/review_queue_<date>.jsonl` (사람 검토)
- `< 0.50` 또는 P2 와 충돌 → 폐기 (`ops.quality_checks` audit trail)

## LangGraph 활성화 — 에이전트 계층

데이터 적재가 끝나면 에이전트가 그 위에서 추론한다. LangGraph StateGraph + PG checkpoint
(`chat` 스키마) 가 표준. 상세는 [`agents.md`](./agents.md) 참조.

```bash
make install-agent      # pip install -e ".[agent]" — langgraph + langfuse + langsmith
make enable-langgraph   # 헬스체크: _HAS_LANGGRAPH + checkpointer 타입 확인
make serve-api          # FastAPI :31020 — POST /chat (blocking) + /chat/stream (SSE)
make serve-ui           # Streamlit :31021 — st.status 노드 진행 표시
```

체크포인트 테이블은 자동 생성 (`chat.checkpoints`, `chat.checkpoint_writes`,
`chat.checkpoint_blobs`, `chat.checkpoint_migrations`). 스키마 위치는
`.env` 의 `LANGGRAPH_CHECKPOINT_SCHEMA` 로 변경 가능 (기본 `chat`).

## 적재 순서 — 의존성 (DAG)

### Finance 도메인

```
ingest-corp     → load-companies      ─┐
ingest-krx      ────────────────────────┤→ load-entity-map (시드)
ingest-targets  ────────────────────────┘

ingest-bulk     → load-filings, load-financials
ingest-structural → load-graph-structural, load-persons

ingest-wikidata → load-wikidata        — entity_map 보강 (QID/ISIN/LEI/CIK/homepage)
ingest-wikipedia → load-wikipedia, build-wiki-chunks

ingest-news     → load-news, load-graph-news

ingest-sec      → load-sec
ingest-gleif    → load-gleif           — entity_map 보강 (LEI)

make migrate-schema                    — 1회 (Sector→Industry / Person birth_year)
make validate-quality                  — 마지막에 매번 실행
```

### Auto 도메인 (`make load-auto-all` 내부 순차 강제)

```
neo4j-init                              # CONSTRAINT/INDEX 멱등
   ↓
pg                                      # NHTSA vPIC + Recalls + Complaints → auto.master_* / events_*
   ↓
specs                                   # NHTSA NCAP + EPA + Canadian → auto.spec_measurements
   ↓
neo4j                                   # PG → Neo4j MERGE (Manufacturer/Model/Variant/Recall)
   ↓
bridge                                  # bridge.corp_entity 매칭 (QID > LEI > sec_cik > business_no > name)
   ↓
standards / plants                      # standards.yaml + plants.yaml seed
   ↓
safety / epa                            # SAFETY_RATED_BY 엣지 + EPA spec 보강
   ↓
aihub                                   # AI Hub 71347 + 578 → auto.components (L4 부분)
   ↓
nhtsa-taxonomy                          # NHTSA recall taxonomy 178 raw → 176 normalized module
   ↓
supplier-edges                          # supplier_seed.yaml 19 공급사 46 매핑 → SUPPLIED_BY 30 distinct edges
   ↓ (이 순서가 강제 — aihub 선행 없으면 component foreign key 위반)
complaints-neo4j                        # auto.events_complaints → Neo4j REPORTED_IN
   ↓
recall-components / complaint-components  # component 매칭 → RECALL_OF 601 edges
   ↓
investigations                          # NHTSA ODI 154 → INVESTIGATED_BY
   ↓
oem-sec                                 # SEC EDGAR 글로벌 OEM XBRL → auto.oem_financials_sec
   ↓
derive-contains-system                  # System taxonomy 19 → CONTAINS_SYSTEM
   ↓
wikidata-part-supplies                  # Wikidata P176 staging (rate-limit 로 0 row — `docs/data_inventory.md §3 B-issue`)
   ↓
manufactured-at                         # plants_seed + DART 사업보고서 → MANUFACTURED_AT 99 edges
   ↓
build-chunks-auto                       # NHTSA complaint/recall/tsb + Wikipedia → vec.chunks (manufacturer/model/variant 메타)
```

### IP 도메인 (실제 Makefile 타깃 — `ip` prefix 없음 정정 2026-06-02)

```
PG schema (18_ipgraph + 19_ipgraph_bridge + 22_ip_works + 23_ip_cpc — hot-apply)
   ↓
load-cpc                                # ✅ 적재 완료 — CPC scheme bulk 10,695 (무인증, 1회)
   ↓
ingest-openalex → load-openalex         # ✅ 적재 완료 — works 629 / institution 38 / work_institution 638
                                        #   (OpenAlex 무료 키 — `OPENALEX_EMAIL` ENV)
   ↓
(대기) ingest-uspto-odp                 # USPTO Open Data Portal bulk dataset (PatentsView 후속, 무인증 bulk)
   ↓
(대기) ingest-kipris                    # KIPRIS_API_KEY 발급 후
   ↓
(대기) load-assignee-corp-map           # assignee → corp_code 매핑 (supplier candidate SOP 재사용)
```

## 자주 쓰는 명령

```bash
# 인프라
make up                       # PG + Neo4j docker-compose up
make health                   # 모든 컴포넌트 ping

# 수집 (점진 — 이어받기)
make ingest-step1             # 마스터부터 시작

# 적재 (멱등)
make load-companies load-entity-map

# 임베딩 (장시간)
make serve-embeddings &       # 별도 프로세스 권장
make embed-chunks             # vec.chunks NULL embedding backfill

# 품질 검증
make validate-quality         # → data/reports/quality_<date>.md
```

## 재처리 시나리오

### 1) 청킹 로직 수정 후 재청크
```bash
# 청크 메타만 갱신 — raw 는 그대로
rm -rf data/processed/chunks
psql $POSTGRES_DSN -c "TRUNCATE vec.chunks RESTART IDENTITY"
make build-chunks build-wiki-chunks
make embed-chunks
```

### 2) 임베딩 모델 교체 (BGE-M3 → 다른 모델)
```bash
# embedding 만 NULL 화. text/메타는 유지
psql $POSTGRES_DSN -c "UPDATE vec.chunks SET embedding = NULL"
# 새 모델 가동 후
make embed-chunks
```

### 3) 그래프 스키마 정합성 (라벨/관계명 충돌)
```bash
make migrate-schema                   # 멱등. 변경 0 이면 이미 적용됨.
```

### 4) Entity Resolution 매핑 보강 (신규 외부 소스)
```bash
# 신규 source 추가했으면 적재 후
make load-entity-map          # 시드 (DART 자체 ID)
make load-wikidata            # QID / LEI / ISIN / CIK 추가
make load-gleif               # LEI 보강
make validate-quality         # 매핑 커버리지 점검
```

## 수동 자료 적재 — car.go.kr / KNCAP (by design)

두 source 모두 **공식 Open API 미공개**. README §4 가 자동 수집을 명시했으나 실제 채널이
없어 **수동 CSV 모드를 정식 운영 방식으로 채택** (의도된 fallback). 대안 채널은 NHTSA
자동수집이 KR-only 리콜의 80% 를 보강 — 본 절 끝 "대체안" 참조.

### car.go.kr (KR 리콜)

1. https://www.car.go.kr/ 의 리콜 검색에서 기간/제조사 필터로 CSV 다운로드.
2. 파일을 `data/raw/auto/car_go_kr/` 하위에 저장 (UTF-8 권장, BOM 자동 처리).
3. `python -m autograph.ingestion.car_go_kr_recalls` 실행 — `_normalized.jsonl` 생성.
4. 이후 표준 적재: `make load-auto-recalls`.

대체안: 한국 OEM 의 미국 출시 모델 리콜은 NHTSA 자동수집(`make ingest-nhtsa-recalls`)
이 KR-only 리콜을 보강하므로, MVP 범위에선 NHTSA 만으로도 80% 커버.

### KNCAP (KR 안전등급)

1. KNCAP 사무국에서 받은 자료를 `data/raw/auto/kncap/` 하위에 CSV 또는 JSON 으로 저장.
2. `python -m autograph.ingestion.kncap` — 표준화된 jsonl 생성.
3. 이후 적재: `make load-auto-kncap` (Standard 노드 + SAFETY_RATED_BY 엣지).

`KNCAP_API_KEY` 환경변수는 향후 API 공개 시를 위해 자리만 잡아둠 — 현재 어떤 path
도 키를 읽지 않는다 (warning 로그만 출력하고 수동 모드로 폴백).

대체안: NHTSA SafetyRatings 가 5 star 등급 자동 수집. 한국 출시 동일 모델 다수가
NHTSA 에 등재되어 있어 KNCAP 의존도 낮음.

## 라이선스 정책 (자동 강제)

`src/autonexusgraph/ingestion/_license.py` 의 `LICENSE_POLICY` 가 source 키별 본문 저장 여부를 강제.
`save_raw()` 호출 시 정책 확인 → `copyrighted` / `metadata_only` 이면 본문 필드 자동 strip.

| Tier | 예시 source | 본문 저장 |
|---|---|---|
| public_domain | dart, sec_edgar, kosis, nhtsa_*, epa, usgs_mcs, uspto_odp, cpc_scheme | OK |
| cc0 | wikidata, openalex | OK |
| cc_by_sa | wikipedia | OK (출처표기) |
| cc_by_4_0 | gleif | OK (출처표기) |
| kogl_type1 | fss_press, ftc, kipris, datagokr (KOTSA / 산단공 / KAMA 등) | OK |
| **kogl_type1_by_nc** | (일부 공공 데이터의 비상업 한정) | OK (비상업 사용 한정 + 출처표기) |
| cc_by_nc_sa | namuwiki (CC BY-NC-SA 2.0 KR — **out-of-scope**) | **본 시스템 사용 금지** |
| copyrighted | news_yonhap, news_hankyung, oem_news (Hyundai/Kia IR/뉴스룸 본문) | 제목+요약+URL 만 (metadata_only 자동 게이트) |
| metadata_only | bigkinds, kia_kr_news (robots Disallow), mobis_kr_news (SPA) | 본문 X |
| share_alike | opencorporates | OK (cc_by_sa 게이트 + `require_share_alike()` helper) |

코드 SSOT = `src/autonexusgraph/ingestion/_license.py` 의 `LICENSE_POLICY` dict. 신규 source 추가 시 정책 미등록이면 `tests/test_license.py` invariant test (`PASS — 15/15`) 가 fail.

## 점검 쿼리

```sql
-- PG 적재량 한눈에 (3 도메인 통합)
SELECT 'master.companies'        tbl, count(*) FROM master.companies UNION ALL
SELECT 'master.entity_map',           count(*) FROM master.entity_map UNION ALL
SELECT 'master.persons',              count(*) FROM master.persons UNION ALL
SELECT 'fin.financials',              count(*) FROM fin.financials UNION ALL
SELECT 'fin.filings',                 count(*) FROM fin.filings UNION ALL
SELECT 'auto.master_manufacturers',   count(*) FROM auto.master_manufacturers UNION ALL
SELECT 'auto.master_vehicle_models',  count(*) FROM auto.master_vehicle_models UNION ALL
SELECT 'auto.events_recalls',         count(*) FROM auto.events_recalls UNION ALL
SELECT 'auto.events_complaints',      count(*) FROM auto.events_complaints UNION ALL
SELECT 'auto.components',             count(*) FROM auto.components UNION ALL
SELECT 'bridge.corp_entity',          count(*) FROM bridge.corp_entity UNION ALL
SELECT 'ip.cpc_scheme',               count(*) FROM ip.cpc_scheme UNION ALL
SELECT 'ip.works',                    count(*) FROM ip.works UNION ALL
SELECT 'vec.chunks',                  count(*) FROM vec.chunks UNION ALL
SELECT 'vec.chunks (embedded)',       count(*) FROM vec.chunks WHERE embedding IS NOT NULL;

-- ID 커버리지 (finance entity_map)
SELECT id_type, count(*) FROM master.entity_map GROUP BY 1 ORDER BY 2 DESC;

-- bridge 매칭 분포
SELECT entity_type, reviewed_status, count(*)
  FROM bridge.corp_entity GROUP BY 1, 2 ORDER BY 1, 2;
```

```cypher
// Neo4j 상태 (3 도메인 통합)
MATCH (n) RETURN labels(n)[0] AS label, count(n) AS c ORDER BY c DESC;
MATCH ()-[r]->() RETURN type(r) AS rel, count(r) AS c ORDER BY c DESC;

// 동명이인 분리 검증 (finance Person)
MATCH (p:Person) WITH p.name AS name, collect(DISTINCT p.birth_year) AS years
WHERE size(years) > 1 RETURN name, years LIMIT 10;

// 7키 의무 메타 누락 엣지 (audit-edge-meta 와 동일 invariant)
MATCH ()-[r]->() WHERE r.source_type IS NULL OR r.confidence_score IS NULL
RETURN type(r), count(*) ORDER BY count(*) DESC LIMIT 20;
```

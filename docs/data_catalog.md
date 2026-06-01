# AutoGraph 데이터 카탈로그

> 2026-06-01 기준. 신규 채널 추가 시 본 문서가 SSOT — `docs/data_inventory.md` 는 실시간 측정값, `docs/data_sources.md` 는 후보·라이선스 검토 노트, 본 문서는 **이미 구현된 채널의 운영 가이드**.

각 데이터 채널을 (1) 출처·라이선스, (2) 분류 (PRD §3.5 신뢰도 등급),
(3) Raw 파일 보존, (4) Ingestion → Loader → 적재 위치, (5) 에이전트 도달 경로,
(6) 알려진 한계 순으로 정리. 새 합류자가 한 채널을 처음부터 끝까지 따라가는
지도로 사용.

---

## 데이터 분류 SSOT

PRD §3.5 출처 신뢰도 등급. 본 등급은 코드 SSOT 인 `src/autograph/ingestion/_confidence.py` 와 일치:

| 등급 | 기본 confidence | 의미 | 단독 근거 |
|:---:|:---:|---|:---:|
| **A+** | 1.00 | 수동 검토 확정 | ✅ |
| **A**  | 0.95 | 공공 API / 공식 인증 (NHTSA, KAMA, KNCAP, NCAP, vPIC, KATRI) | ✅ |
| **B**  | 0.80 | Wikidata, 공식 공시 (DART), 매뉴얼, IR | ✅ |
| **B~C** | 0.70 | Wikipedia | ⚠ 보조 |
| **C**  | 0.50 | LLM 추출, 산단공 합성 데이터, 분해 자료 | ❌ 금지 |

`Validator` 의 `LOW_CONFIDENCE_THRESHOLD = 0.50` 미만 confidence 엣지로만 구성된 답변은 hard fail → replan. Mixed (일부 미달) 는 soft warning.

---

## 채널 1: NHTSA vPIC / Recalls / Complaints / SafetyRatings / Investigations

| 항목 | 내용 |
|---|---|
| 출처 | NHTSA (US 정부, vpic.nhtsa.dot.gov + api.nhtsa.gov) |
| 라이선스 | 공공 (US Gov) — 인증 불필요 |
| 등급 | **A** (0.95) |
| Ingestion | `src/autograph/ingestion/nhtsa_{vpic,recalls,complaints,safety_ratings,investigations}.py` |
| Raw | `data/raw/auto/nhtsa_{vpic,recalls,complaints,safety,investigations}/<OEM>/...` |
| Loader (PG) | `src/autograph/loaders/load_auto_pg.py` — 마스터 + events_recalls + events_complaints |
| Loader (Neo4j) | `load_auto_neo4j.py`, `load_complaints_neo4j.py`, `load_auto_investigations.py` |
| PG 적재 | `auto.master_manufacturers` (22,143) / `master_vehicle_models` (6,770) / `master_vehicle_variants` (237) / `events_recalls` (493) / `events_complaints` (16,005) / `events_investigations` (154) / `spec_measurements (safety.ncap.*)` (1,680) |
| Neo4j | `:Manufacturer` / `:VehicleModel` / `:VehicleVariant` / `:Recall` / `:Complaint` / `:Investigation` + `[:MANUFACTURES]` / `[:HAS_VARIANT]` / `[:AFFECTED_BY]` / `[:REPORTED_IN]` / `[:INVESTIGATED_BY]` |
| 에이전트 tool | `lookup_vehicle`, `get_vehicle_info`, `get_spec`, `get_safety_rating`, `list_recalls_affecting` (graph), `list_investigations_affecting` (graph) |
| 한계 | 글로벌 데이터 우세 (한국 시장 별도) |

---

## 채널 2: Wikidata (자동차 마스터)

| 항목 | 내용 |
|---|---|
| 출처 | query.wikidata.org SPARQL |
| 라이선스 | CC0 |
| 등급 | **B** (0.80) — 일부 P176 부품→공급사는 staging → P4 cross-validate |
| Ingestion | `src/autograph/ingestion/wikidata_auto.py` — 4 종 SPARQL (manufacturers / models / suppliers / part_supplies) |
| Raw | `data/raw/auto/wikidata/{manufacturers,models,suppliers,part_supplies}.jsonl` |
| 알려진 결손 | P176 (manufactured by) 는 1 req/min rate-limit 으로 429 — **2026-05-29 commit 2d70995 에서 chunked + retry-after 해결**: 부품 class 10 개로 분할, Retry-After 헤더 인식 |
| Loader | `load_auto_pg.py` (마스터 보강) + `load_wikidata_part_supplies.py` (staging → P4) |
| 에이전트 tool | NHTSA tool 과 통합 (`lookup_vehicle` 가 vPIC + Wikidata 결합 결과 반환) |

---

## 채널 3: AI Hub (제조 ML 데이터)

| 항목 | 내용 |
|---|---|
| 출처 | aihub.or.kr (한국지능정보사회진흥원 NIA) |
| 라이선스 | 개방데이터 (이용약관 — 다운 승인 필요) |
| 등급 | **C** (0.50) — 합성/ML 학습 데이터 |
| 현재 보유 | 71347 (자율주행 고장진단), 578 (부품 품질) |
| 잠재 추가 | 67 (제조현장 이송장치 AGV 열화 예지보전, ~100MB×N) — 자동차 관련 라벨만 필터링 권장 |
| Ingestion | `src/autograph/ingestion/aihub.py` (현재 71347/578) |
| Loader | `src/autograph/loaders/load_auto_aihub.py` — 라벨 → `auto.components` + `vec.chunks` |
| PG 적재 | `auto.components` (level=4 Module, 71347→4건 + 578→22건) |
| Neo4j | `:Module` + `(:VehicleModel)-[:CONTAINS_COMPONENT]->(:Module)` |
| 한계 | **활용률 0.001%** — 3 GB 라벨 → 4~22 모듈 추출만 가능. ML 학습용이라 KG 매핑이 본질적으로 어려움. 후속 도입 시 라벨에서 자동차 관련 키만 추출하여 `auto.processes` 보강 권장 |

---

## 채널 4: 산단공 자동차 부품 제조업 공정 합성데이터 (15151075) ⭐ 신규

| 항목 | 내용 |
|---|---|
| 출처 | data.go.kr 15151075 (한국산업단지공단) |
| 라이선스 | 공공 — 키 불필요 (수동 CSV 다운로드 또는 odcloud API) |
| 등급 | **C** (0.50) — 합성 데이터, 단독 근거 금지 |
| Ingestion | (수동 다운로드 — odcloud API 도 가능하나 키 필요) |
| Raw | `data/raw/datagokr/한국산업단지공단_자동차 부품 제조업 공정 합성데이터_YYYYMMDD.csv` |
| 형태 | 8 컬럼 CSV: 공장관리번호, 업종차수, 업종코드, 공정도명, 공정도설명, 공정순서, 공정명, 공정설명 |
| Loader | `src/autograph/loaders/load_sandang_processes.py` — UPSERT `auto.processes` |
| 운영 | `make load-sandang-processes` (또는 `--dry-run` 으로 통계만) |
| PG 적재 | `auto.processes` (550 row / 410 distinct 공정명, 1 산업) |
| Neo4j | (현재 미연결 — 후속 PR `:Process` 노드화 검토) |
| 에이전트 tool | `search_processes(query, limit=20)` — ILIKE `process_name_norm` |
| 한계 | 합성 데이터라 실제 공장과 직접 매핑 불가. **공정명 정규형 사전으로만 사용** — "스프레이도장", "CNC 가공" 등 표준 표기 검색. |
| 인코딩 | EUC-KR / UTF-8 자동 감지 (`_open_csv`) |

---

## 채널 5: DART 사업보고서 — "III. 생산 및 설비" ⭐ 신규

| 항목 | 내용 |
|---|---|
| 출처 | DART (전자공시시스템) 사업보고서 XML |
| 라이선스 | 공공 |
| 등급 | **B** (0.80) — 공식 공시 |
| 대상 OEM | 현대차 (00164742) / 기아 (00106641) / 모비스 (00164788) / 한온 (00161125) / HL만도 (01042775) / 현대위아 (00106623) |
| Raw | 기존 `data/raw/dart_bulk/corp/<corp_code>/documents/*.zip` (이미 보유, 64+ 사업보고서) |
| Parser | `src/autograph/extractors/dart_production_parser.py` — lenient lxml.html + ROWSPAN 상속 |
| Loader | `src/autograph/loaders/load_dart_production.py` — zip walker + UPSERT + Neo4j sync |
| 운영 | `make load-dart-production` (전체) / `--dry-run` / `--no-neo4j` / `--corp-code 00164742` |
| PG 적재 | `auto.plant_capacity` / `plant_production` / `plant_utilization` (마지막은 schema 만, parser 미완) |
| Neo4j | `(:Manufacturer)-[:MANUFACTURED_AT {capa_units, actual_units, utilization_pct, source_type='dart_business_report', confidence_score=0.80, validated_status='validated'}]->(:Plant)` |
| Plant 매핑 | `_DART_PLANT_CODE_MAP` 모듈 상수 — DART 약어 (HMC/HMMA/...) → `plants.yaml` 코드. **의도적 부분 매핑** — HYU_ULSAN/HYU_MONTGOMERY/KIA_HWASEONG 등 등록 plant 만. HMI/HMMR/HTMV 등 미등록 plant 는 PG 에는 저장되지만 Neo4j 엣지 skip + log.warning |
| 에이전트 tool | `get_plant_capacity(corp_code, plant_code?, year?)` / `get_oem_production(corp_code, year?)` / `list_plants_by_oem(corp_code)` |
| 한계 | (1) 차량부문만 (금융부문/위탁/상용 제외 — PRD non-goal). (2) **가동률(utilization) 파서 미구현** — schema 와 다른 column 구조라 별도 branch 필요. (3) Plant 매핑은 plants.yaml 확장 시 추가. |
| 실측 (2026-06-01) | 현대차 dry-run: 16 zip / sample 2 zip 파싱 → capacity 27 + production 36 행 (1 zip), 누적 capa 51 + prod 51 (2 zip) |

---

## 채널 6: KAMA 매크로 통계 (15051116 + 15051118) ⭐ 신규

| 항목 | 내용 |
|---|---|
| 출처 | data.go.kr 산업통상자원부 (한국자동차산업협회) — odcloud OAS 또는 CSV 다운로드 |
| 라이선스 | 공공 |
| 등급 | **A** (0.95) — 공식 통계 |
| Raw | `data/raw/datagokr/산업통상부_국내 및 세계 자동차 생산량(한국자동차산업협회)_*.csv` (15051116, 21 행) <br>`data/raw/datagokr/산업통상부_전체 자동차 산업 현황_*.csv` (15051118, 204 행) |
| 인코딩 | UTF-8 (BOM) / CP949 자동 감지 |
| Loader | `src/autograph/loaders/load_kama_macro.py` |
| 운영 | `make load-kama-macro` / `--dry-run` |
| PG 적재 | `auto.macro_production_yearly` (snapshot_year PK) <br>`auto.macro_industry_monthly` (year, month PK) |
| GENERATED 컬럼 | `domestic_share_pct = ROUND(domestic / global * 100, 3)` STORED |
| 에이전트 tool | `get_macro_industry(year?, month?)` / `get_macro_production(year?)` |
| Cross-Domain 가치 | DART 분기 매출 ↔ KAMA 월간 수출금액 정합, ECOS 환율과 결합 시 환위험 분석, KOSIS 산업통계 macro hub 구성 |
| 한계 | per-OEM 아님 (회사 단위 분해 불가). 매크로 시계열 컨텍스트로만 활용 |

---

## 채널 7: 팩토리온 (15087611) — Scaffold 만

| 항목 | 내용 |
|---|---|
| 출처 | data.go.kr 15087611 (한국산업단지공단 공장등록정보) |
| Base URL | apis.data.go.kr/B550624/fctryRegistInfo |
| 라이선스 | 공공, 개발계정 1,000 traffic |
| 등급 | **B** (0.80) — 공식 등록 |
| 3 Endpoint | `getFctryPrdctnService_v2` (회사명 → 공장+생산품) / `getFctryByFctryManageNoService_v2` (공장관리번호 단건) / `getFctryListInIrsttService_v2` (산업단지명) |
| Ingestion | `src/autograph/ingestion/factoryon_registry.py` |
| Raw 위치 | `data/raw/auto/factoryon/{by_company,by_factory_no,by_industrial_complex}/...` |
| **상태** | **DATA_GO_KR_API_KEY 미설정 — graceful skip**. 키 도착 즉시: `make ingest-factoryon-company NAME=현대자동차` |
| Loader / PG / Neo4j | **미구현** — 데이터 형태 확인 후 정의 (활성화 시 plant↔생산품 매핑으로 MANUFACTURED_AT 보강 기대) |

---

## 채널 8: 한국 리콜 (15089863, KOTSA) — Scaffold 만

| 항목 | 내용 |
|---|---|
| 출처 | data.go.kr 15089863 (자동차리콜센터) |
| 라이선스 | 공공 |
| 등급 | **A** (0.95) — 공식 |
| Ingestion | `src/autograph/ingestion/datagokr_recalls.py` |
| Loader | `src/autograph/loaders/load_datagokr_recalls.py` (OEM 한국어 alias 매칭 포함 — `_KO_MFR_ALIAS` 12 사) |
| Raw 위치 | `data/raw/auto/datagokr_recalls/page_*.json` |
| **상태** | **DATA_GO_KR_API_KEY 필요** — graceful skip. 키 도착 후 `make ingest-datagokr-recalls` + `make load-datagokr-recalls` |
| PG | `auto.events_recalls WHERE source='datagokr_kotsa'` (기존 schema 재사용) |

---

## 채널 9: 제조사 IR / 뉴스룸 (Hyundai · Mobis · ~~Kia~~) ⭐ 신규

| 항목 | 내용 |
|---|---|
| 출처 | Hyundai www.hyundai.com/worldwide/{ko,en}/company/ir/, Mobis www.mobis.com + www.mobis.co.kr |
| 라이선스 | `public_partial` (Hyundai/Mobis — 본문 저장 가능, 출처 표기 필수) / `metadata_only` (Kia) |
| 등급 | **B** (0.80) — 공식 IR |
| **Kia 한국 정책** | ⚠️ **비활성** — robots.txt `Disallow: /kr/discover-kia/news/` 명시 (2026-06-01 직접 확인) |
| 라이선스 SSOT | `src/autonexusgraph/ingestion/_license.py::OEM_NEWSROOM_POLICY` — robots.txt + ToS 결정 매트릭스 |
| Ingestion | `src/autograph/ingestion/oem_ir_newsroom.py` — sitemap-first crawler |
| 보호 메커니즘 | (1) `is_url_allowed()` 정책 게이트 (host + path prefix whitelist + 명시 Disallow), (2) `urllib.robotparser` 런타임 robots.txt 검증 (User-Agent 별), (3) RateLimiter 2 req/sec, (4) User-Agent `AutoGraph-Research/0.1 (research, public-info)`, (5) HTTP 429 → Retry-After 인식 |
| Raw | `data/raw/auto/oem_ir/<oem>/_meta.jsonl` (메타) + `<YYYY-MM-DD>_<slug>.html` (본문) |
| Loader | `src/autograph/loaders/load_oem_ir_news.py` |
| 운영 | `make ingest-oem-ir-hyundai` / `make ingest-oem-ir-mobis` / `make ingest-oem-ir-policies` (정책 dump) / `make load-oem-ir-news` |
| Schema | `infra/postgres/init/17_autograph_oem_news.sql` |
| PG 적재 | `auto.events_oem_news` (UNIQUE oem+url, section 분류, body_text, body_html_path, license_tier 동봉) |
| Section 분류 | `ir/public_disclosure` / `ir/quarterly_earnings` / `ir/sales_results` / `ir/events` / `news/press` 등 — URL 패턴 기반 자동 라벨링 |
| 활용 가치 | (1) 공장 위치 / CAPA / 모델 배정 발표 추출 → `MANUFACTURED_AT` 보강, (2) IR 분기실적·판매실적 → DART 매출과 시계열 정합, (3) 신규 모델 출시 발표 → variant 마스터 보강 |
| LLM 추출 경로 (후속) | P3 LLM → plant 명 / 모델명 / 수치 후보 → `auto.staging_relations` → P4 cross-validate (DART 본문 매칭) → Neo4j MANUFACTURED_AT promote |
| 한계 | (1) Kia 한국 비활성 — `press.kia.com` 등 글로벌 newsroom 별도 검토 필요. (2) 본 v0 는 sitemap-base — RSS feed 발견 시 그쪽 우선. (3) JS 렌더링 페이지 (SPA) 는 본문 비어있을 수 있음 (lxml + headless 후속) |
| 검증 | `make ingest-oem-ir-policies` 로 적용 정책 dump, `tests/test_oem_ir_newsroom.py` 36 케이스 (라이선스 게이트 + sitemap + 텍스트 추출) |

> **운영 약관 주의**: 본 모듈은 robots.txt 변경에 대응하지 못한다. 약관 갱신 시 `OEM_NEWSROOM_POLICY` dict 의 `notes` 필드 측정일 갱신 + `disallowed_path_prefixes` 동기화 필수. PR 시 robots.txt 갱신 확인 `curl https://<host>/robots.txt` 결과 첨부 권장.

---

## 채널 10: KOTSA 수리검사 (15155857)

| 항목 | 내용 |
|---|---|
| 출처 | data.go.kr 15155857 (한국교통안전공단 수리검사내역) |
| 라이선스 | 공공 — 파일 다운로드 (키 불필요) |
| 등급 | **A** (0.95) |
| Raw | `data/raw/datagokr/수리검사내역(UVTOTLOSSRS_T).csv` (49,290 row 이미 보유) + `한국교통안전공단_자동차검사관리_수리검사내역_*.zip` |
| Ingestion | `src/autograph/ingestion/datagokr_inspections.py` |
| Loader | `src/autograph/loaders/load_datagokr_inspections.py` → `auto.events_inspections` |
| Neo4j | `(:Inspection)` 노드 (후속 PR) |

---

## 채널 11: KCGS ESG 등급 (한국ESG기준원) {#kcgs-esg}

| 항목 | 내용 |
|---|---|
| 출처 | cgs.or.kr (한국ESG기준원) — 공식 API 없음, 회원 페이지 + 보도자료 |
| 라이선스 | 공공 (보도자료) + 회원 (등급 풀데이터) — 본문/CSV 는 수동 다운로드 |
| 등급 | **B** (0.80) — 등급표는 정확, 발표 시점은 보도자료 수동 확인 |
| Raw | `data/raw/kcgs/press/<no>/{meta.json, body.html}` (보도자료 자동) + `data/raw/kcgs/<year>/ratings.csv` (등급표 수동) + `data/raw/kcgs/sample/template.csv` (형식 예시) |
| Ingestion | (자동) `make ingest-kcgs` — `scripts/ingest/download_kcgs.py` 가 press_list.jsp 의 '등급' 키워드 보도자료 polling. ESG 등급 조정·평가 발표 시 새 게시물 자동 감지. 커스텀: `python scripts/ingest/download_kcgs.py --svalue 평가 --pages 5 --with-body` |
| Loader | (수동 CSV → PG/Neo4j) `make load-kcgs` (기본 year=2024) 또는 `python scripts/load/load_kcgs.py --year 2024` → PG `esg.ratings` + Neo4j `Company.esg_<year>_{env,soc,gov,total}` |
| CSV 형식 | `회사명, 종목코드, 환경, 사회, 지배구조, 종합` — 컬럼명 자동 감지 (회사명/기업명, 종목코드/코드, 환경/E, 사회/S, 지배구조/G, 종합/통합) |
| 검증 | PG `SELECT total_grade, count(*) FROM esg.ratings WHERE year=2024 GROUP BY 1` / Neo4j `MATCH (c:Company) WHERE c.esg_2024_total='A+' RETURN c.corp_code, c.corp_name LIMIT 10` |
| 알려진 한계 | (a) **자동 다운로드 불가** — 등급 풀데이터는 회원 가입 + 약관. (b) 등급 조정 보도자료 본문은 자동 OK, **첨부 PDF 는 JS 함수 호출이라 수동 다운로드 필요**. (c) 매년 정기 등급 발표 (10~11월) 시 보도자료 monitor → 사용자 페이지 방문 후 CSV 저장 → `make load-kcgs` 자동 적재. |
| 다운로드 경로 | (1) 회원 가입 시 KCGS 회원 페이지 / (2) 공개 시점 보도자료 첨부 HWP/PDF / (3) 3rd party (DBpia / 언론사 정리 자료) |

---

## Raw 디스크 보존 정책

| 영역 | 보존 정책 | 라이선스 게이트 |
|---|---|---|
| 공공 데이터 (NHTSA/KAMA/DART/산단공/KOTSA/Wikidata) | **영구 보존** — 멱등 파이프라인 보장 | `src/autonexusgraph/ingestion/_license.py` |
| Wikipedia CC BY-SA | 본문 보존 가능 | 출처 표기 강제 |
| 연합뉴스 RSS | 메타+요약만 (저작권) | 본문 저장 금지 (자동 strip) |
| AI Hub | 약관에 따라 |
| 제조사 IR / 뉴스룸 | (현재 미구현) — 약관 검토 필수 |

총 raw 사용량 (2026-06-01):
```
data/raw/auto/        — 3.7 GB (AI Hub 3.6 GB 우세)
data/raw/dart_bulk/   — 1.6 GB (자동차 6 OEM 포함)
data/raw/datagokr/    — 1.9 MB (산단공 + KAMA + KOTSA)
data/raw/wikipedia/   — 34 MB
data/raw/wikidata/    — 6.4 MB
```

---

## 데이터 처리 파이프라인 (모든 채널 공통 패턴)

```
[1] Ingestion             [2] Loader (PG)               [3] Loader (Neo4j)
    ─────────────────         ─────────────────              ─────────────────
    공식 API / CSV        →  ON CONFLICT DO UPDATE      →  MERGE + edge_meta_cypher
    save_raw()               (corp_code, plant_code,       (의무 메타 100%)
    CheckpointStore          snapshot_year)
    RateLimiter

           ↓                          ↓                          ↓
    data/raw/<source>/       auto.<table>                  :Label + Relationship

                                      ↓                          ↓
                            [4] 에이전트 도달 경로
                            ─────────────────
                            agent_handler.AUTO_SQL_ALLOWED  → autograph/tools/spec.py
                            agent_handler.AUTO_GRAPH_ALLOWED → autograph/tools/graph.py
                            agent_handler.AUTO_RESEARCH_INTENTS → autograph/tools/retrieve.py
                            (planner → supervisor → workers)
```

**의무 메타** (PRD §6.7 — 모든 관계 엣지 100% 강제):
- `source_type`, `source_id` (provenance)
- `extraction_method`, `extractor_version`
- `confidence_score` (0.0~1.0, `_confidence.py` SSOT)
- `validated_status` (candidate / validated / needs_review / rejected)
- `snapshot_year`, `valid_from`, `valid_to`
- `schema_version` (현재 'v2.1')

---

## 데이터 채널 트래픽라이트

```bash
make audit-data-channels    # eval/reports/data_channels_latest.md 생성
```

🟢 적재 완료 / 🟡 raw 만 (loader 대기) / 🔴 raw 도 없음.

---

## 2026-06-01 실측 적재 상태 (`make audit-data-channels`)

🟢 = 적재 완료 / 🟡 = raw 만 / 🔴 = 미수집 / ⊘ = 키 대기

| 채널 | 상태 | PG row | 인사이트 |
|---|:---:|---:|---|
| 산단공 공정 (15151075) | 🟢 | 550 | 410 distinct 공정명 |
| DART production (Hyundai+Kia) | 🟢 | 184 (capa 107+prod 77) | 12 + 5 = 17 plants × 4-6 years |
| DART 가동률 utilization | 🟢 | 53 | Hyundai 본사 116.6% / 베트남 54.1% |
| KAMA 매크로 (yearly+monthly) | 🟢 | 225 | 2009~2025 시계열 |
| OEM IR 뉴스룸 (Hyundai+Kia ww) | 🟢 | 37 (Hy 25 + Kia ww 12) | sitemap-first, robots/ToS 게이트 |
| vec.chunks (oem_ir + wiki plants) | 🟢 | 75 | LLM P3 가능 |
| 팩토리온 (15087611) | ⊘ | 0 | DATA_GO_KR_API_KEY 대기 |
| 한국 리콜 (15089863) | 🔴 | 0 | DATA_GO_KR_API_KEY 대기 |
| KOTSA 수리검사 (15155857) | 🟡 | (raw 1 CSV) | loader 실행 대기 |

신규 에이전트 도구 (2026-06-01):
- `get_plant_capacity` / `get_oem_production` / `list_plants_by_oem` (DART)
- `search_processes` (산단공)
- `get_macro_industry` / `get_macro_production` (KAMA)

LLM P3 활성화 경로:
- `make extract-ir-p3-cost` — 비용 추정 ($0.024 / 25 chunks @ gpt-4o-mini)
- `make extract-ir-p3` — 실제 호출 (IR_P3_HARD_LIMIT=1.0 보호)
- `IRRelationExtractor` → `MANUFACTURED_AT` + `CAPACITY_REPORTED` →
  `auto.staging_relations` → P4 cross-validate → Neo4j 적재

---

## 더 필요한 데이터 (우선순위)

PRD §3.4 BOM 가용성 매트릭스 + 사용자 의제 ("크롤링이 진짜 가치") 기준.

### 🔴 P0 — 즉시 활성화

1. **DATA_GO_KR_API_KEY 발급** — 한 키로 4 endpoint 활성:
   - 15089863 한국 리콜 (KOTSA)
   - 15087611 팩토리온 (plant↔생산품 매핑)
   - 15051116/15051118 KAMA (이미 CSV 로 받음 — 키 있으면 자동 갱신)
   - 활용 신청: data.go.kr → 회원가입 → 활용신청 (자동 승인 ~1일)

2. **`plants.yaml` 확장** — DART production loader 가 미매핑 plant skip 중:
   - 현재 18 plant 등록 → 6 OEM × 사업보고서 raw 분석하여 ~30 plant 추가 가능
   - 우선: HMI (인도 첸나이), HMMR (러시아), HTMV (베트남), HMMI (인도네시아),
     KMS (슬로바키아 질리나), 모비스 글로벌 공장 6+

### 🟡 P1 — 가치 있지만 약관 검토 필요

3. **제조사 IR/뉴스룸 크롤링** — 사용자가 강조한 "진짜 가치" 채널:
   - Hyundai newsroom (hyundai.com/worldwide/ko/newsroom/)
   - Kia newsroom, 모비스 뉴스 등
   - 추출: 공장 위치/CAPA/모델 배정 발표, 신차 출시
   - **약관 검토**: 각 사 robots.txt + 이용약관 — 검토 후 활성화 결정

4. **Wikipedia plant 문서** — 기존 `wikipedia_auto.py` 는 모델·제조사만:
   - "Hyundai Motor Manufacturing Alabama" 류 plant 문서 별도 ingestion
   - model↔plant 자동 매핑 보강 (DART 본문보다 글로벌 범위 넓음)

### 🟢 P2 — 향후 use case 정의 후

5. **AI Hub 67** (제조 AGV 열화 예지보전) — 사용자 결정대로 "자동차 관련만"
   다운로드 → `auto.processes` 보강 (~10-20 row 예상)

6. **KATRI (bigdata-tic.kr)** — OAuth 키 (BIGDATA_TIC_CLIENT_ID/SECRET) 발급 후
   인증/표준 데이터 → `:Standard` 노드 ↔ `(:VehicleVariant)-[:COMPLIES_WITH]` 보강

7. **Euro NCAP / IIHS** — 별도 약관 검토 후

### ⚪ 영구 보류 (PRD non-goal)

- 라인·설비 수준의 진짜 제조 공정 데이터 (가동률, 설비 파라미터, 공정별 수율) — **영업비밀, 오픈 없음**
- 비공개 OEM 내부 BOM
- 실시간 텔레메트리
- 자율주행 안전성 인증

---

## 운영자 체크리스트 (새 채널 추가 시)

새 채널을 추가하는 PR 은 다음 9 가지를 모두 충족해야 한다 (CLAUDE.md 컨벤션):

1. ☐ `infra/postgres/init/NN_*.sql` — `CREATE ... IF NOT EXISTS` 멱등 + GRANT
2. ☐ `src/autograph/ingestion/*.py` — graceful skip + CheckpointStore + RateLimiter
3. ☐ `src/autograph/loaders/*.py` — SAVEPOINT 패턴 + ON CONFLICT UPSERT
4. ☐ (필요 시) `_neo4j_helpers.run_batched` + `edge_meta_cypher` 의무 메타
5. ☐ `Makefile` — `ingest-*` / `load-*` / `migrate-*` 타겟 + `.PHONY`
6. ☐ `make load-auto-all` 의존 list 에 등록 (순서 주의)
7. ☐ `src/autograph/tools/spec.py` 또는 `graph.py` — agent SQL/Cypher tool
8. ☐ `src/autograph/agent_handler.py` — `AUTO_SQL_ALLOWED` / `AUTO_GRAPH_ALLOWED` 등록
9. ☐ 테스트 (DB 미가용 환경에서 통과) + 본 카탈로그 1 행 추가

---

## 관련 문서

- `PRD.md` §3 (데이터 정책) / §4 (스키마) / §6 (재구성) / §10 (DoD)
- `docs/data_inventory.md` — 실시간 측정값 (자동 갱신)
- `docs/data_sources.md` — 후보 카탈로그·라이선스 검토 노트
- `docs/operations/data_pipeline.md` — 3-tier 멱등 파이프라인 + 4-pass 추출 가이드
- `docs/autograph.md` — 자동차 도메인 전체 가이드
- `src/autograph/ingestion/_confidence.py` — 출처 등급 → confidence SSOT

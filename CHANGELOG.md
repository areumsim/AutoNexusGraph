# CHANGELOG

본 파일은 AutoNexusGraph 의 release-grade 변경 이력. 작은 fix/refactor 는 `git log`
참조. 도메인 추가·DoD audit 메커니즘 도입·schema 마이그레이션 등 중요 milestone 만 기록.

본 prefix: `feat:` 기능 / `fix:` 버그 / `docs:` 문서 / `chore:` 잡무 / `refactor:`
구조 변경. PRD §10 DoD 항목 영향은 `[DoD §10.X]` 로 표기.

---

## 2026-06-04 — v2.2-rev2: ProcessGraph P0 게이트(DoD #19) 통과 + 미완료 라벨 전수 정정 (PR #6)

PR #6 (`docs/label-audit-recall-source-fix` → main, 16 commits) 머지. v2.2-rev1 BoP 정책
정의를 실데이터로 충족 + Layer 1 Bridge 신규 + Layer 2 EU 지역 확장 + Neo4j namespace
SSOT. [DoD §10.19 충족 / §10.20 부분 — 결함전파·공정↔재무 경로 구조 완성, 정확도 실측만 LLM 키 대기]

### Added
- **ProcessGraph 엣지 5종 — DoD §10.19 통과**: PERFORMED_AT 94 (G-1, 회사귀속 ≥ 30 게이트 통과)
  / PRODUCED_BY 46 (G-2, Part→ProcessStep) / USES_EQUIPMENT 16 + CONSUMES_MATERIAL 6 (G-3,
  Equipment 13 신규) / CAUSED_BY_PROCESS 96 (G-4, KOTSA 한글 리콜 결함→공정 deterministic) /
  USES_PROCESS 189 (G-6, Module→Process). 산단공 익명 스텝 무오염·비귀속 위반 0
- **Layer 1 Bridge — 가이드 §1.x 4-홉 회사귀속·회사무관 추적 처음 동작**: `:DefectType` 50
  (NHTSA+KOTSA defect_summary 1,434 → Agent 추출, 8 카테고리 균형) + `:FailureMode` 18 +
  `:Equipment` 3 (NASA PCoE Bearing/Battery/IGBT readme + 논문 1.4 GB → Agent) + DEFECT_MATCHES
  7,417 / MANIFESTS_AS 72 / SUBJECT_TO 18. 신규 SQL `28_auto_defect_matches.sql` +
  `29_auto_failure_modes.sql` (pgvector 1024 + 7키 풀)
- **Layer 2 — 3 지역 자동차 리콜 2,406건**: NHTSA 493 + KOTSA 941 + **EU Safety Gate 972**
  (weekly XML 122/131, CC BY 4.0). brand 매핑 NHTSA 100% / KOTSA 92.1% / EU 86.7%.
  `master_manufacturers` dedup 21→8 row → **cross-jurisdictional 9 패턴 검출** (Ford
  "연료라인 누유" 3-region 7쌍 / 현대·기아 EV ICCU 글로벌 캠페인 4+3 / JAGUAR 주조 결함 /
  VW 안전삼각대 83 / Mercedes 접착제 76 등)
- **Neo4j domain namespace SSOT** (CE multi-DB 미지원 우회) — 33 라벨 매핑 + 96,969 노드
  backfill
- **운영·보안·DX**: O-1 FastAPI API key 인증·rate limit·thread 소유권 / O-2 production 배포
  가이드 + `docker-compose.prod.yml` / Q-1 Bridge candidate 검토 SOP (Streamlit UI + KPI) /
  LLM 비용 가드 실효화 (turn·세션 한도 + kill-switch + auto-wrap)
- **KAMP 카탈로그 50 row** + 산단공 `:Process` 정규화 사전 (37→33 매핑, inline `_PROCESS_NORM`)
- **신규 문서 3건**: `docs/operations/api_keys_pending.md` (P0 GCP / P1 KIPRIS·Anthropic·KAMP.ai / P2 USPTO·EPO 발급 대기 + 진입 체크리스트) / `docs/data_lineage.md` §2.14~16 + §4.2~4.2.1 (3 신규 출처 + cross-jurisdiction 인사이트) / `BACKLOG.md` G-7/G-8/G-9 + PG-4 + IP-1 trigger 갱신

### Fixed
- D-1 팩토리온 / D-5 리콜 라벨 정정 (live PG 실측 — factoryon 5→90행, events_recalls 941행)
- S-1 MCP tool count 드리프트 교정 (52→59, auto 31→38) — audit SSOT 정합
- S-3 온톨로지 검증 + Y-1 보조 yaml pydantic strict 충족
- G-5 `ontology/ip/relations.yaml` 오기 정정 — `MAPPED_TO`는 BOM↔공정 아닌 **IP assignee→Company** 브릿지

---

## 2026-06-02 — v2.2-rev1: ProcessGraph (BoP) 축 격상 정책 통합 (PR-P0-A)

산단공 자동차 부품 제조업 공정 합성데이터 (data.go.kr 15151075, `auto.processes` 550 row /
410 공정명) 를 auto 도메인의 BoP (Bill of Process) 1급 축으로 격상하기 위한 **PRD 정책
변경만 포함**. 실제 적재·로더·온톨로지·도구 작업은 후속 13 PR (P0-B 부터 P4-C 까지) 로
분리. 본 commit 은 정책 게이트만 (코드·데이터 변경 0). [DoD §10.18~20 신설]

### Added
- **PRD §12.6** — "ProcessGraph — BoP 축 격상 (auto 도메인 심화)" 신설 (§12.5 IPGraph 패턴
  미러). 설계 SSOT = `PRD_process_graph.md` (사용자 작성 중, `docs/process_graph.md` 로
  이관 예정). 도메인 어댑터 슬롯 / 데이터 소스 (산단공·DART·팩토리온·KAMP·AI Hub·KOSIS) /
  Cross-Domain CD-Process 시연 / 14 PR 작업 순서 (P0~P4) / 정량 게이트.
- **PRD §10 DoD #18/#19/#20 신설** —
  - #18: BoP 모델 안정 (5 노드 + 7 엣지: PRODUCED_BY/PRECEDES/INSTANTIATES/USES_EQUIPMENT/
    CONSUMES_MATERIAL/PERFORMED_AT/CAUSED_BY_PROCESS, `make audit-ontology` PASS)
  - #19: 회사 귀속 공정 인스턴스 (`PERFORMED_AT` ≥ 30, A/B 100%, 산단공/KAMP/AI Hub 위반 0건)
  - #20: 공정 cross 시연 (AUTO 공정 문항 ≥ 10 + CD-Process ≥ 5 + 정확도 ≥ 50%)
- **PRD §3.5.1 신설** — "row 단위 동적 confidence 격상 (C→B)". 정적 등급표 §3.5 본문 무변경
  + `_confidence.py::SOURCE_TO_GRADE` 무변경 + `validator.py:LOW_CONFIDENCE_THRESHOLD=0.5`
  무변경. 8 시그널 (M1~M7 + C1) 가중합산 → `clip(0.50 + Σ w·s·grade − 0.20·|conflicts|,
  0.30, 1.00)`. 산단공 row 단독 운영. C 단독 격상은 `validated_status='candidate'` 유지
  (§3.5 단독 근거 금지 원칙 보존).
- **PRD §13 의사결정 로그 1행 추가** — "v2.2-rev1 ProcessGraph 격상" (대안: 새 도메인 /
  단일 노드 단순 모델, 사유: BoM ⟂ BoP 직교 확장 + 회사 귀속 A/B 분리).

### 후속 PR (`/root/.claude/plans/quiet-bubbling-wadler.md` SSOT, 14 PR / 약 4.5주)
- **P0-B**: `ontology/auto/process.yaml` 신규 (Process / ProcessStep / Equipment) +
  `relations.yaml` 7 엣지 추가 + `src/autograph/extractors/process_confidence.py` 시그니처
- **P1-A~C**: `:Process` taxonomy (410 distinct, key=`SCREAMING_SNAKE(name_norm)`) +
  `:ProcessStep` BoP 인스턴스 + `:Equipment` + PRODUCED_BY / PRECEDES / INSTANTIATES /
  USES_EQUIPMENT 결정적 적재
- **P2-A~D**: `:Part` L5 도입 (NHTSA recall + Wikidata P527, LLM 회피) + `:Material` L6
  확장 (cathode chem → 합금/플라스틱 25+) + CONSUMES_MATERIAL + SUPPLIED_BY × Part +
  KAMP 15089213 / AI Hub / KOSIS 풍부화 (회사 비귀속 통계 속성만)
- **P3-A~C**: PERFORMED_AT (A/B 회사 귀속만, `load_performed_at.py` source allowlist
  hard-check) + CAUSED_BY_PROCESS (NHTSA recall LLM P3 → P4 검증) + cross_validate 8
  시그널 row 단위 격상 (`scripts/upgrade_processes_confidence.py` 1회 풀런 ≤ $2 + GPU 1분)
- **P4-A~C**: `src/autograph/tools/process.py` 10 함수 + `auto_proc_*` Cypher 6 템플릿 +
  Gold QA AUTO 공정 10+ / CD-Process 5+ + 문서 동기화 (data_lineage / data_sources /
  data_inventory / autograph / README)

### 보류 (사용자 작업 존중)
- **`PRD_process_graph.md` → `docs/process_graph.md` 이관** — 사용자가 작성 중. P0-A 에서는
  PRD §12.6 / §3.5.1 / §10 본문이 직접 `PRD_process_graph.md` 를 참조 (이관 후 사용자가
  링크 갱신). PR-P4-C 의 문서 동기화 단계에서 이관 완료 가정.
- **청사진 §1.1 line 25 "USES_PROCESS base" 잔존 표현** — 청사진 §3.2 엣지 리스트 (7개)
  에 `USES_PROCESS` 부재 (`INSTANTIATES`/`PRODUCED_BY` 가 base). 구버전 표현 잔존
  가능성이지만 사용자 작업 존중, 본 PR 에서 수정하지 않음.

### 검토 회피 (사용자 강조)
사용자가 본 세션에서 "에이전트 답변이 아니라 실제 코드 기반으로 꼼꼼히 검토" 를 명시
요구. Plan agent 1차안의 9건 문제 (`:Process` 단일 노드 모델 / yaml `from: Module ∪ Part`
문법 불가 / `_OPTIONAL_INDEXES` hardcoded 미인지 / `required_confidence_min` 기존 schema
신설 주장 / 청사진 SSOT 무시 등) 를 실제 파일·라인 대조 후 모두 수정. 메모리
`feedback_verify_real_code.md` 보강.

---

## 2026-06-01 — 정합성 검토 + IPGraph (도메인3) 인프라 통합

대형 검토·정리 PR. 본 세션 7 commit (`414bc1b` ~ `0066a19`) 으로 도메인3 (ip = 특허)
정식 흡수 + 검증 layer 일원화 + DoD audit 자동 wiring + 문서 SSOT 정리 완료.

### Added
- **`src/ipgraph/` 패키지 전체** (18 py) — 도메인3 plug-in (handler / policy /
  ontology / cypher_templates_ip + tools/{bridge,graph,patents,retrieve} +
  loaders/{load_cpc,load_openalex,load_assignee_corp_map} + ingestion/{cpc_scheme,
  kipris,uspto_odp,openalex}).
- **PG schema 12 ip.* 테이블** — `18_ipgraph.sql` + `19_ipgraph_bridge.sql` 적용 완료.
  patents/assignees/inventors/citations/patent_*/cpc_scheme/works/institution/
  work_institution/assignee_corp_map. FK 정합 (master.companies(corp_code)
  REFERENCES + ON DELETE CASCADE).
- **`ontology/ip/{entities,relations}.yaml`** — 7 entity + 9 relation 정의.
  edge_required_meta 7키 (auto/finance 표준 동기화).
- **`docs/architecture.md`** — 시스템 구조 SSOT (~300줄, Mermaid 3) — 패키지
  토폴로지 / 도메인 모듈 매트릭스 / SQL 24 마이그레이션 / LangGraph 11 노드 /
  plug-in 등록 메커니즘 / SSOT 위치 색인. 6 docs (PRD/README/autograph/ipgraph/
  mental_model/learning_guide) cross-link.
- **검증 layer 5종**:
  - `tests/test_license.py` (15 invariants) — LICENSE_POLICY 도메인별 source 키
    동기화 강제. [DoD §6.7]
  - `scripts/audit/ontology_validate.py` cypher↔yaml cross-check — `cypher_templates_<domain>.py`
    의 엣지 타입이 `relations.yaml` 에 정의되어 있는지 검증. cross-domain
    reference (예: ip cypher → auto.SUPPLIED_BY) WARN 강등. [DoD §10.17(c)]
  - `scripts/audit/edge_meta_invariants.py` 확장 (auto 8 → 12 invariants —
    ip/finance 도메인 추가). [DoD §6.7 / §10.11]
  - `eval/runners/run_matrix_smoke.py:compute_dod_13_14()` — manifest 의
    `main_hop_efficiency` + `latency` 를 흡수해 DoD #13/#14 자동 산출.
    `prd_dashboard._collect_{hop,latency}_audit()` 가 자동 흡수 → `make audit-dod`
    한 줄에 반영. [DoD §10.13 / §10.14]
  - `eval/metrics/_thresholds.py` + `eval/metrics/_thesis.py` — PRD §10 임계값
    SSOT 분리 (이전 4 모듈에 분산된 hardcoded 값 → 한 파일).
- **`src/common/retrieve_base.py`** — 3 retrieve.py (finance/auto/ip) 의 공통
  cap_topk + normalize_source_filter 추출.
- **`Makefile smoke-e2e` target** — DB·LLM 없는 mock 정합성 일괄 검증 (pytest +
  6 audit + gold qa lint). pre-push 게이트.
- **gold_qa cross 신규 7 row** — CD-L3-009/010 + CD-L4-005 (auto cross 이행) +
  CD-L3-011 + CD-L4-006/007 (refusal/fallback 시나리오). gold_qa_cross 38→44.
- **`scripts/audit/validate_gold_qa.py` 강화** — `_` prefix 파일 자동 skip
  (사용자 작업물 보호) + main_hop_path↔hop_count 자동 검증.
- **`opendata_patch.md` 본문 흡수 후 삭제** — USGS MCS / EV chargers /
  GLEIF×OpenCorporates / OpenAlex 4종을 README/docs/data_sources 본문에 분배.

### Fixed
- **SQL `12_` prefix 충돌** — `12_autograph_inspections.sql` + `12_autograph_investigations.sql`
  → `12a_…` / `12b_…` rename.
- **`ip.patents` schema drift** — 기존 (14 cols: application_no/registration_no/...)
  vs `18_ipgraph.sql` DDL (pub_no/jurisdiction/source) mismatch → DROP CASCADE +
  18 재적용 (row 0 이라 안전). [DoD §10.17(c)]
- **`ip.assignee_corp_map` FK 미적용** — `corp_code VARCHAR` (FK 부재) →
  `CHAR(8) REFERENCES master.companies(corp_code) ON DELETE CASCADE`.
- **README §1 SSOT 수치 3건 재측정** (psycopg/neo4j-driver 직접 쿼리):
  - `bridge.corp_entity` 4,806 = manufacturer reviewed 11 + cand 1 + supplier
    reviewed 4 + cand 4,790 ✓ (이전 "10 + 4,792 + 2 = 4,804 ≠ 4,806" 모순 해소).
  - SUPPLIED_BY 30 edges 100% meta (yaml 46 vs Neo4j 30 = customer dimension
    dedupe — 데이터 모델 정상, "16 매핑 누락" 진단 부정확).
  - strong_match **15/15 = 100%** (manufacturer 11 + supplier 4, conf≥0.9).
    이전 "12/12" 는 stale.
- **`ip relations.yaml edge_required_meta` 5키 → 7키** — extraction_method +
  schema_version 추가 (auto/finance 표준 동기화).
- **cypher↔yaml 누락 2건 보완**:
  - `auto.LED_TO_RECALL` (Investigation → Recall, side_hop, deterministic, 0.95).
  - `ip.MAPPED_TO` (Assignee → Company, main_hop cross-domain bridge, hybrid, 0.80).
- **gold_qa_auto 의 3 cross_domain row** (AUTO0008/9/11) → `gold_qa_cross_v0.jsonl`
  의 CD-L3-009/010 + CD-L4-005 로 이동 (`notes` 에 migration 흔적 보존).
- **test isolation** — `test_auto_detect_domain_without_routers_returns_finance` 가
  `_DISCOVERY_DONE=True` 도 monkeypatch 하여 후속 테스트의 `_ROUTERS` baseline 보존.

### Changed
- **README §10 DoD 트래픽라이트 표** — 자동 PASS 8→9/14 (§10.12 baseline reset
  `bab9411` → `414bc1b` 효과 + §10.13/§10.14 wired 명시).
- **baseline reset (§10.12)** — `4049caf` → `bab9411` → `414bc1b`
  (`eval/reports/core_diff_baseline_ledger.md`).
- **`eval/reports/prd_dashboard_latest.md`** — 최신 audit-dod 결과 (9 pass /
  14 measurable) 로 동기화.

### Removed
- `eval/qa_gold/_stage2_cd_l4_ip.jsonl` (4행 모두 `gold_qa_cross_v0.jsonl` 에 흡수 완료).
- `eval/qa_gold/_stage2_new_cross.jsonl` (3행 → CD-L3-011/CD-L4-006/CD-L4-007 로 흡수).
- `opendata_patch.md` (본문 흡수 후 폐기).

### Audit 측정 결과 (2026-06-01)

| ID | 기준 | 상태 | 비고 |
|---|---|:---:|---|
| §10.4 | MVP 범위 | ✅ | OEM=5 / models=102 |
| §10.5 | BOM L0~L3 + L4 ≥60% | ✅ | L4=63.7% |
| §10.6 | strong_match ≥80% | ✅ | **15/15 = 100%** (재측정) |
| §10.11 | SUPPLIED_BY 100% meta | ✅ | **30 edges**, all `source_type=manual_supplier_seed` |
| §10.12 | 코어 변경 <5% | ✅ | baseline `414bc1b` → 0/15,396 = 0.00% |
| §10.13 | 메인 홉 효율 -30% | (wired) | LLM 키 필요 (run_matrix_smoke --full) |
| §10.14 | latency <8s/<12s | ✅ | internal pass=100% (simulation 측정 기준) |
| §10.15 | ip 도메인 wire-up | ✅ | handler+router+ontology+25 cypher templates |
| §10.16 | ip gold seed 30 + CD ip 8 | ✅ | gold_qa_ip 30 + cross_ip 8 |
| §10.17(a) | MCP 래퍼 | ⚠️ | SDK 미설치 (`pip install -e ".[mcp]"` 후 PASS) |
| §10.17(b) | Langfuse 실측 | ⚠️ | TRACE_BACKEND 미설정 |
| §10.17(c) | 온톨로지 strict | ✅ | yaml 6/6 + cypher cross-check 통과 |
| §10.17(d) | 평가 매트릭스 | (wired) | LLM 키 필요 |

### 사용자 액션 대기 (외부 의존)
- **KIPRIS_API_KEY 발급** → `python -m ipgraph.ingestion.kipris --applicants ...`.
- **USPTO ODP bulk dataset 다운로드** → `data/raw/ip/uspto_odp/{patents,assignees,
  citations,inventors}.jsonl` 배치 → `python -m ipgraph.ingestion.uspto_odp`.
- **assignee → corp_entity 매핑** → `python -m ipgraph.loaders.load_assignee_corp_map`.
- **finance 73,602 엣지 의무 메타 결손** — 별도 PR (본 PR 외 기존 적재 데이터).

### 커밋 이력 (본 세션)
1. `414bc1b` — feat: PRD/README/code 정합성 검토 + ipgraph 패키지 인프라 일괄
2. `8021cff` — feat: cypher cross-check dashboard 노출 + stage 흡수 + 임계값 SSOT 분리
3. `31171a6` — feat: P1-2 footnote 실측 + P2 ip.* schema drift 해소 + thesis 모듈 분리
4. `32dbd78` — docs: README §1 SUPPLIED_BY footnote 데이터 모델 정상 명확화
5. `6ae2439` — feat: §10.7 thesis — hits@k fallback metric + multi-hop subset 보강
6. `0066a19` — fix+feat: 정합성 재검토 P0 4건 + edge_meta_invariants ip/finance 확장
7. (본 commit) — final: P1 #5/#7/#8/#9 + CHANGELOG + retrieve common base

---

## 이전 milestone (참고)

- **2026-05-29** `bab9411` — P0~P3 추가 결손 (vector search + Plant wiki + Korean
  alias + eval gold).
- **2026-05** `4049caf` — Phase B 안정화 (도메인1+2 finance+auto 완료) — IPGraph
  통합 전 anchor.

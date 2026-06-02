# BACKLOG — AutoNexusGraph 전수 미완료 항목 SSOT

> **위치**: 루트 단일 SSOT. 모든 "예정 / scaffold / wired-but-disabled / TODO / 미구현 / 데이터 대기 / 키 부재" 항목 전수.
>
> **상위 SSOT**: 요약 + P0+/P1 트래픽라이트는 [README §12 보완 개발 백로그](./README.md#12-보완-개발-백로그-critical-gaps), 정량 게이트 본문은 [README §10 DoD 20항](./README.md#10-dod-definition-of-done--20-항). 본 문서는 **세부 항목 + 활성화 트리거** 풀 카탈로그.
>
> **갱신 주기**: PR 마지막 단계에서 항목 추가·이동·완료. `make audit-dod` 가 자동 반영하는 항목은 (자동) 라벨.
>
> **버전**: v1.0 (2026-06-02, README v3.0 통합 시 신설). **83 항목 / 15 카테고리 / P0+/P0/P1/P2/P3 트래픽라이트**.

---

## 0. 요약 통계 + 우선순위 정의

| 카테고리 | 항목수 | P0 | P1 | P2 | P3 |
|---|---:|---:|---:|---:|---:|
| 1. 데이터 인입 (키 / bulk download) | 9 | 2 | 2 | 1 | 4 |
| 2. 그래프·엣지 적재 | 6 | 1 | 1 | 2 | 2 |
| 3. 에이전트·도구·HITL | 6 | 0 | 2 | 2 | 2 |
| 4. 상용 신호 (MCP / Langfuse / SHACL / 매트릭스) | 5 | 0 | 3 | 1 | 1 |
| 5. 운영·보안·배포 | 6 | 2 | 1 | 2 | 1 |
| 6. Bridge·데이터 품질·calibration | 5 | 1 | 1 | 1 | 2 |
| 7. 평가·신뢰성·gold QA | 6 | 0 | 2 | 3 | 1 |
| 8. 문서·DX | 4 | 0 | 0 | 2 | 2 |
| 9. ProcessGraph 회사 귀속 + KAMP + 품질 | 3 | 1 | 1 | 1 | 0 |
| 10. IPGraph 데이터 적재 + bridge join | 7 | 0 | 4 | 1 | 2 |
| 11. 배터리·소재 L5/L6 | 5 | 0 | 0 | 4 | 1 |
| 12. EV 충전 인프라 | 2 | 0 | 0 | 2 | 0 |
| 13. NCAP / Euro NCAP / IIHS | 4 | 0 | 0 | 0 | 4 |
| 14. 라우팅·정책·미정 결정 | 2 | 0 | 0 | 1 | 1 |
| 15. 온톨로지·schema | 2 | 0 | 0 | 1 | 1 |
| **합계** | **83** | **7** | **18** | **23** | **23** |

### 우선순위 정의

- **P0+ (상용 신호)** — 1차 목표 "**서비스 등급 agent + ontology 정량 증명**" 의 직접 게이트. MCP·Langfuse·SHACL·평가 매트릭스 4 항. README §12.1 SSOT.
- **P0 (차단)** — 현재 시스템을 production 에 올릴 때 **반드시 깨지는** 것. 보안·배포·핵심 데이터.
- **P1 (운영필수)** — 1개월 내 해결 권장. 데이터 적재 / 평가 실측 / Bridge 품질.
- **P2 (개선)** — 분기별. 도메인 확장 / 외부 데이터 / 도구 신설.
- **P3 (의문/장기)** — 우선순위 모호 또는 6개월+ 시점. 비전 / 4번째 도메인.

---

## 1. 데이터 인입 (키 / bulk download)

| ID | 항목 | 상태 | 우선순위 | 활성화 트리거 | 위치 |
|---|---|---|:---:|---|---|
| D-1 | **팩토리온 공장 등록 (15087611)** — 회사·공장번호·산단별 조회 | (scaffold) | **P0** | `DATA_GO_KR_API_KEY` 발급 → `make ingest-factoryon-company` | README §7, BACKLOG §9 (ProcessGraph #19 직접 의존) |
| D-2 | **KIPRIS Open API** — 한국 특허·출원 | (예정) | **P1** | `KIPRIS_API_KEY` 발급 (공공데이터포털) → `make ingest-kipris` | docs/ipgraph.md §4, BACKLOG §10 |
| D-3 | **USPTO Open Data Portal (PatentsView 후속)** — 미국 특허·인용·assignee | (예정) | **P1** | bulk download (data.uspto.gov) → `make ingest-uspto-odp`. PatentsView REST 종료 (2026-03-20, 410 Gone) | docs/ipgraph.md §4 |
| D-4 | **KAMP 제조AI 데이터셋 (15089213)** — 사출/용접/프레스 시계열·불량 | (scaffold) | P1 | CSV 수동 다운 → `make load-kamp-process-metrics`. `auto.process_metrics` (corp_code 컬럼 의도적 부재 = 익명) | docs/process_graph.md §2, BACKLOG §9 |
| D-5 | **자동차 리콜정보 (15089863)** — 한국 OEM 리콜 | (예정) | P2 | `DATA_GO_KR_API_KEY` (D-1 공유) → `make ingest-datagokr-recalls` | README §4 |
| D-6 | **자동차검사관리 (15155857)** — 사고·침수·도난 검사 | (예정) | P3 | CSV 파일 다운 (무인증) → `make ingest-datagokr-inspections`. **이미 47,171 row 적재 완료 (2016~2025) — 이 항목은 신규 채널 보강용** | docs/data_sources.md |
| D-7 | **공정위 기업집단 데이터** | (예정) | P3 | data.go.kr 키 → Neo4j Group + BELONGS_TO_GROUP | README §4 |
| D-8 | **KOSIS 산업 통계 (광공업동향)** — 제조업 생산지수 by KSIC | (예정) | P3 | `KOSIS_API_KEY` 발급 → `make load-kosis` → `macro.kosis_series` | README §4 |
| D-9 | **LAW.go.kr 법령** | (예정) | P3 | open.law.go.kr 키 → `law.laws` | README §4 |

---

## 2. 그래프·엣지 적재

| ID | 항목 | 상태 | 우선순위 | 활성화 트리거 | 위치 |
|---|---|---|:---:|---|---|
| G-1 | **`PERFORMED_AT` (회사 귀속 공정)** ≥ 30 | (scaffold, 0/30) | **P0** | D-1 팩토리온 키 + ProcessStep↔Plant 매핑 출처 | README §10.19, docs/process_graph.md §2 |
| G-2 | **`PRODUCED_BY` (Part→ProcessStep)** | (scaffold, 0) | P1 | 산단공 `part_id` 부재 — 부품↔공정 결정적 매핑 출처 확보 | docs/process_graph.md §2 |
| G-3 | **`CONSUMES_MATERIAL` / `USES_EQUIPMENT`** | (scaffold, 0) | P2 | 산단공 소재·설비 정보 부재 — Wikidata + manual seed | docs/process_graph.md §2 |
| G-4 | **`CAUSED_BY_PROCESS` (Recall→Process)** | (scaffold, 0) | P2 | 리콜 493건 US 영문 ↔ 한글 합성공정 환각위험 (P3 dry-run $0.51). KOTSA 한글 리콜 (D-1 키) 또는 영문 공정 taxonomy 확보 후 P3+P4 | docs/process_graph.md §2 |
| G-5 | **`MAPPED_TO` (BOM↔공정 cross)** | wired (yaml 정의) | P3 | 부품↔공정 결정적 매핑 (G-2 와 같은 트리거) | ontology/ip/relations.yaml:88 |
| G-6 | **`USES_PROCESS` (산단공 :Process ↔ :Module)** | wired (ontology) | P3 | 산단공 사전 ↔ NHTSA Module taxonomy 매칭 routine 미구현 | README §12.5 |

---

## 3. 에이전트·도구·HITL

| ID | 항목 | 상태 | 우선순위 | 활성화 트리거 | 위치 |
|---|---|---|:---:|---|---|
| A-1 | **`sensitive_decision` HITL trigger 정책** | wired (interrupts.py) + 휴리스틱 활성 (SENSITIVE_KEYWORDS 10종) | P1 | 운영 데이터에서 false-positive 측정 → 키워드 정정. nodes.py:668~688 게이트 활성 | README §7 (HITL sensitive_decision 행) |
| A-2 | **P3 LLM 4종 활성화** — COMPETES_WITH / MANUFACTURED_AT(LLM) / CONTAINS_MODULE / CONTAINS_PART | `enabled:false` | P1 | 비용·환각 위험 검증 후 selectively 활성. validation gate 강화 | README §12.5, ontology/auto/relations.yaml:226-235 |
| A-3 | **HITL `clarification`/`cost_approval` 무한 루프 가드** | wired | P2 | (P2) Streamlit dialog 의 resume 재진입 횟수 cap. 의도적이지만 미구현 | docs/operations/agents.md |
| A-4 | **새 Cypher 템플릿** — recall 전파 · 공급 집중도 · 시점 정합 cross | finance 22 + auto 24 + ip 25 = 71 | P2 | use case 별 신규 템플릿. 자유 Cypher 금지 원칙 유지 | README §12.5 |
| A-5 | **N-domain bridge 일반화** — `bridge.drug_entity` 등 다형 | `bridge.corp_entity` 만 (2-domain 가정) | P3 | 4번째 도메인 추가 시. 또는 `bridge.cross` 다형 1 테이블 | README §12.5 |
| A-6 | **DomainHandler intent allowlist 확장** | finance / auto / ip 각각 정의 | P3 | 새 도메인 추가 시 자동 확장. 신규 intent 추가 시 화이트리스트 갱신 | src/autonexusgraph/agents/_domain_handler.py |

---

## 4. 상용 신호 (MCP / Langfuse / SHACL / 평가 매트릭스)

| ID | 항목 | 상태 | 우선순위 | 활성화 트리거 | 위치 |
|---|---|---|:---:|---|---|
| S-1 | **MCP 래퍼** — typed tool pool 52 tools (finance 21 + auto 31) | (wired) — `make audit-mcp` SDK 미설치 SKIPPED | **P0+** | `pip install -e ".[mcp]"` 또는 `[all]` extras → `python -m autonexusgraph.mcp` stdio server | README §10.17 (a) |
| S-2 | **Langfuse 실측 ON (turn별 token/cost/replan)** | (wired) — Langfuse 4.x OTEL native | **P0+** | `.env`: `TRACE_BACKEND=langfuse` + `LANGFUSE_*` 키 → `make audit-trace` (simulation 또는 `--full`) | README §10.17 (b) |
| S-3 | **온톨로지 SHACL/pydantic 검증** | (wired) — 6 yaml PASS, cypher cross-check PASS | P1 | 보조 yaml (extractors.yaml / system_taxonomy.yaml / plants.yaml) 별도 모델 추가 | README §10.17 (c) |
| S-4 | **축소 평가 매트릭스 실측 (4 어댑터 × FAST tier 1종 + rerank ablation)** | (wired, partial) — 8 cells enumerate simulation 모드 PASS | **P0+** | LLM 키 + `make audit-eval-matrix --full` → `eval/reports/<run>/summary.md` PR 첨부 + Allganize 외부 벤치 stub 채움 | README §10.17 (d) |
| S-5 | **§10.12 baseline reset 정책 dashboard 자동 반영** | (wired) — baseline reset 2회 이력 | P1 | `make audit-dod` 출력에 baseline commit + 누적 reset 이력 + "도메인 추가 마다 reset" 명시 (대부분 완료, dashboard 표시만 보강) | README §10.12 |

---

## 5. 운영·보안·배포

| ID | 항목 | 상태 | 우선순위 | 활성화 트리거 | 위치 |
|---|---|---|:---:|---|---|
| O-1 | **API 인증 / Rate limit** | ✅ **구현** (`api/auth.py` + `test_api_auth.py` 12건) — API key 헤더 (`X-API-Key`/`Bearer` + `API_KEYS` env) + thread_id↔user_id 바인딩 (타인 403) + per-identity in-memory rate limit. **잔여 (P2)**: OAuth2/OIDC 발급기관 연동, multi-instance 분산 (redis/reverse proxy) | ~~P0~~ → **P2** (잔여) | (잔여) 외부 IdP 통합 시 | README §12.2 |
| O-2 | **Production 배포 가이드** — `docs/operations/production_deploy.md` | 미작성 | **P0** | k8s / compose prod profile / health probe / blue-green / canary. dev Quickstart 와 분리 | README §12.3 |
| O-3 | **백업·DR** — PG dump + Neo4j backup + 재생성 RPO/RTO | 없음 | P1 | PG dump 스케줄 + `neo4j-admin backup` cron + vec.chunks embedding 재생성 시간 측정 (finance 748K + auto 16K 추정 수 시간) | README §12.3 |
| O-4 | **CI/CD 파이프라인** — `.github/workflows/` 부재 | 없음 | P1 | unit test + lint + `make audit-dod --strict` + (옵션) ephemeral PG/Neo4j 통합테스트 | README §12.3 |
| O-5 | **모니터링·알람** — Prometheus + Grafana | 없음 (Langfuse fail-soft만) | P2 | Prometheus exporter (node count / chunk count / cost / error rate) + Grafana 대시보드 + 알람 (PG 끊김 / Neo4j disk full / LLM cost spike) | README §12.3 |
| O-6 | **TLS / Secrets / PII 정책** | uvicorn http 만, `.env` 한 곳, PII 정책 미정의 | P2 | nginx/caddy reverse proxy + HSTS + cert renewal. vault / k8s secret. master.persons 9,948 (name, birth_year) GDPR-style 삭제 권리 + log redaction | README §12.2 |

---

## 6. Bridge·데이터 품질·calibration

| ID | 항목 | 상태 | 우선순위 | 활성화 트리거 | 위치 |
|---|---|---|:---:|---|---|
| Q-1 | **Bridge candidate 4,792 검토 SOP** | 미설계 | **P0** | (1) Streamlit 검토 UI — name match candidate → ✓/✗ 라벨 (2) 6개월 미검토 candidate 자동 `rejected` (3) 검토 진행률 KPI | README §12.4 |
| Q-2 | **confidence_score calibration** — A=0.95 / B=0.80 / C=0.50 가 실제 정답률과 단조 미검증 | 측정 인프라 wired (`scripts/audit/calibrate_confidence.py`) | P1 | LLM 키 활성 후 `make eval-full` → `make audit-calibrate` 1회. Platt scaling + 10-bin reliability diagram. systematic 어긋남이면 §4.0 표 재조정 | README §4.0 (Calibration 박스), §12.4 |
| Q-3 | **`master.persons` 동명·동년생 충돌 빈도 측정** | (name, birth_year) 키 사용 | P2 | 충돌 빈도 측정 routine + (name, birth_year, 회사) 보조 키 | README §12.4 |
| Q-4 | **embedding backfill 진행률 가시화** | finance 748K 중 일부 + auto 16K 100% | P3 | `make embed-status` 또는 dashboard. 누락 청크 자동 재시도 cron | README §12.4 |
| Q-5 | **데이터 freshness 모니터링** | 없음 | P3 | NHTSA recalls 마지막 호출 시각 / DART 마지막 filing 등 source 별 freshness check + stale 알람 | README §12.4 |

---

## 7. 평가·신뢰성·gold QA

| ID | 항목 | 상태 | 우선순위 | 활성화 트리거 | 위치 |
|---|---|---|:---:|---|---|
| E-1 | **12 조합 매트릭스 실측** (4 어댑터 × 3 LLM) | 측정 대기 | P1 | `make eval-full / eval-auto / eval-cross` 풀 실행 + LLM 키 + `eval/reports/<run>/summary.md` PR 첨부 | README §12.6 |
| E-2 | **gold QA 확장** — finance 30 / auto 46 / cross 44 / ip 30 → 각 100 row + 외부 큐레이터 30% | seed 적재 완료 | P1 | 사람 라벨링 + 외부 큐레이터 채널 확보 (Allganize 흡수 워크플로 포함) | README §12.6, docs/gold_qa_guide.md |
| E-3 | **§10.13/14 trace 메트릭** — hop 수 + tool call sequence | latency 수집됨 / hop 수 미구현 | P2 | per-turn trace 에 cypher hop count + tool call sequence 기록 → `eval/metrics/main_hop_efficiency.py` 활성 | README §12.6 |
| E-4 | **답변 사용자 피드백 루프** — 👍/👎/📝 → 저장소 | UI wiring 완료, 저장소 정의 없음 | P2 | `chat.feedback` 스키마 + 저주파 retraining loop | README §12.6 |
| E-5 | **Vector RAG 공정성 검증** — gold QA "Vector 도 풀 수 있는 질문" 비율 | 매트릭스 내 Vector adapter 단독 측정 | P2 | 작성자 편향 완화 — 사람 검증 또는 외부 큐레이터 | README §12.6 |
| E-6 | **performance benchmark** — p50/p95/p99 latency + 평균 토큰·cost/turn | PRD 목표만, 실측 미수행 | P3 | E-1 풀 실측 후 dashboard 구축 | README §12.7 |

---

## 8. 문서·DX

| ID | 항목 | 상태 | 우선순위 | 활성화 트리거 | 위치 |
|---|---|---|:---:|---|---|
| F-1 | **CONTRIBUTING.md / SECURITY.md** | 없음 | P2 | 코드 스타일 + PR 절차 + 보안 보고 채널 | README §12.7 |
| F-2 | **TROUBLESHOOTING.md** | 없음 | P2 | 흔한 실패 (LLM rate limit / pgvector 미설치 / Neo4j auth / DART 키 만료) 진단 트리. **단일 SSOT 신설 권장** — docs/faq.md 와 통합 또는 분리 | README §12.7 |
| F-3 | **`docs/design/`** 빈 디렉토리 | placeholder | P3 | 핵심 컴포넌트 (LangGraph 노드 / DomainHandler / Bridge / P3-P4) ADR + diagrams | README §12.7 |
| F-4 | **GitHub Issue/PR template** | 없음 | P3 | bug / feature / data-source 템플릿 | README §12.7 |

---

## 9. ProcessGraph 회사 귀속 + KAMP + 품질

| ID | 항목 | 상태 | 우선순위 | 활성화 트리거 | 위치 |
|---|---|---|:---:|---|---|
| PG-1 | **DoD #19 회사 귀속 인스턴스 `PERFORMED_AT` ≥ 30** | ⚠️ 0/30 | **P0** | D-1 팩토리온 키 + ProcessStep↔Plant 매핑 출처. **본 시스템의 ProcessGraph "주요 축" 주장의 핵심 게이트** | README §10.19, docs/process_graph.md |
| PG-2 | **DoD #20 cross 정확도 ≥ 50% — 공정↔재무 / 결함전파** | ⚠️ 부분 (소재 리스크 + 생산↔거시 2종 answerable, 2종 refusal) | P1 | LLM 키 + G-1 + G-4 (CAUSED_BY_PROCESS) | README §10.20 |
| PG-3 | **row 단위 동적 confidence 격상 실측** | wired (`scripts/upgrade_processes_confidence.py`) | P2 | 1회 풀런 ≤ $2 + GPU 1분 (idempotent). 격상률 15~30% 예상 | README §4.0.1 |

---

## 10. IPGraph 데이터 적재 + bridge join

| ID | 항목 | 상태 | 우선순위 | 활성화 트리거 | 위치 |
|---|---|---|:---:|---|---|
| IP-1 | **`ip.patents` (KIPRIS + USPTO ODP)** | 0 row, schema 적용 완료 | P1 | D-2 + D-3 키·bulk → `ingestion/{kipris,uspto_odp}.py` | README §1.5 |
| IP-2 | **`ip.assignees` + Wikidata QID·LEI·business_no 매칭** | 0 row, schema 적용 완료 | P1 | IP-1 적재 후 → `bridge_assignee_to_corp` 호출 | README §1.5 |
| IP-3 | **`ip.citations` (PatentsView 후속 USPTO ODP)** | 0 row, schema 적용 완료 | P1 | D-3 bulk 적재 후 → `get_citation_network(depth≤2)` cap 강제 | README §1.5 |
| IP-4 | **`ip.assignee_corp_map` 매핑** | 0 row, schema 적용 완료 | P1 | IP-2 적재 후 → supplier candidate 운영 SOP 재사용 (Q-1 와 같은 흐름) | README §1.5 |
| IP-5 | **IP gold QA `gold_answer` 채우기** | seed 30 row, gold_answer 채우기는 KIPRIS/USPTO 적재 후 | P2 | IP-1 적재 후 수동 또는 `fill_ip_gold.py` 자동 | docs/gold_qa_guide.md |
| IP-6 | **`ip.inventors / ip.patent_inventors / ip.patent_assignees / ip.patent_cpc`** | 0 row 각각, schema 적용 완료 | P3 | IP-1 적재 후 FK ON DELETE CASCADE 로 자동 채움 | README §1.5 |
| IP-7 | **CPCCode subgroup 250K** — 현재 main_group 9,868 만 적재 | section 9 + class 137 + subclass 681 + main_group 9,868 = 10,695 | P3 | 별도 cron — 무인증 USPTO/EPO bulk download | README §1.5 |

---

## 11. 배터리·소재 L5/L6 (auto 곁가지)

| ID | 항목 | 상태 | 우선순위 | 활성화 트리거 | 위치 |
|---|---|---|:---:|---|---|
| L6-1 | **Wikidata 배터리 셀 chem 확장** | :Material 6 적재는 **manual seed** (materials_seed.yaml: NCM811/622/523/NCA/LFP/GRAPHITE_ANODE). **Wikidata 자동 보강은 비활성** — `CATHODE_QIDS` 빈 dict (이전 QID 오류: Q899037=루마니아 마을, Q900614=carbochemistry) | P2 | `wikidata_cell_chem.py` 의 `CATHODE_QIDS` 정확한 QID 재큐레이션 (CC0, 무인증) → manual seed 자동 보강 | docs/autograph.md §2.5.4 |
| L6-2 | **알루미늄 합금 / 다이캐스팅 등 공법 ontology** | 미정의 | P2 | `:Material` ontology 확장 (배터리/금속 seed) + `:Process` 와 연결 (USES_PROCESS) | README §12.5 |
| L6-3 | **회사단위 셀↔OEM 소싱 (SUPPLIES)** | grade C candidate (sparse) | P2 | 공개 IR PDF 또는 manual seed. 자동 만료 (6개월 미검토 → rejected) | docs/autograph.md §2.5.4 |
| L6-4 | **무역통계 — 관세청 / K-stat (Li/Ni/Co 한국 수입)** | 0 | P2 | `macro.trade_minerals` 신규 스키마 + ingestion | docs/autograph.md §2.5.4 |
| L6-5 | **EVO 온톨로지 정렬** (arXiv 2304.04893 — 20 클래스·17 객체속성·54 데이터타입) | 미적용 | P3 | EV/배터리 확장 시 EVO 클래스명·속성 정렬 참조. SHACL/pydantic 검증과 시너지 | docs/autograph.md §2.5.4 |

---

## 12. EV 충전 인프라

| ID | 항목 | 상태 | 우선순위 | 활성화 트리거 | 위치 |
|---|---|---|:---:|---|---|
| EV-1 | **전국 충전소 위치·운영정보** (한국환경공단 `B552584/EvCharger`) | (예정) | P2 | D-1 `DATA_GO_KR_API_KEY` (공유) → `auto.ev_chargers` + Neo4j `:ChargingStation`. Operator → `bridge.corp_entity` cross | README §4 EV 충전 인프라 |
| EV-2 | **지역별 급속충전기 설치현황·실제 이용량** (한국에너지공단 `B553530/TRANSPORTATION/ELECTRIC_CHARGING`) | (예정) | P2 | D-1 키 공유 → `auto.ev_charger_usage` | README §4 EV 충전 인프라 |

---

## 13. NCAP / Euro NCAP / IIHS

| ID | 항목 | 상태 | 우선순위 | 활성화 트리거 | 위치 |
|---|---|---|:---:|---|---|
| N-1 | **NHTSA NCAP SafetyRatings** | ✅ 1,680 row 적재 (auto.spec_measurements) | — | (완료) | README §1.2 |
| N-2 | **KNCAP** | 인터페이스만 | P3 | 공식 채널 약관 검토 후 PDF 파서 + Standard 노드 매핑 | README §12.5 |
| N-3 | **Euro NCAP** | 미구현 | P3 | euroncap.com 사용 약관 검토 후 | README §12.5 |
| N-4 | **IIHS** | 미구현 | P3 | iihs.org 사용 약관 검토 후 | README §12.5 |

---

## 14. 라우팅·정책·미정 결정

| ID | 항목 | 상태 | 우선순위 | 활성화 트리거 | 위치 |
|---|---|---|:---:|---|---|
| R-1 | **N-domain bridge 식별자 우선순위 sequence** — `wikidata_qid > LEI > 사업자번호 > name` 외 DUNS/CIK/ISIN/NDC/ATC 등 | 미정 | P2 | 4번째 도메인 추가 시 결정 | README §11.1 열린 질문 |
| R-2 | **`_legacy/v2/` 폴더 정책** | 보존 | P3 | 삭제 vs 마이그레이션 vs archived branch 미정 | README §7 (legacy 행), docs/mental_model.md §5.10 |

---

## 15. 온톨로지·schema

| ID | 항목 | 상태 | 우선순위 | 활성화 트리거 | 위치 |
|---|---|---|:---:|---|---|
| Y-1 | **보조 yaml SHACL/pydantic 확장** — extractors.yaml / system_taxonomy.yaml / plants.yaml | 미적용 (6 핵심 yaml 만 PASS) | P2 | 별도 모델 추가. 현재 핵심 yaml (entities + relations × 3 도메인) 은 PASS | README §10.17 (c) |
| Y-2 | **Cypher cross-check WARN 강등 (cross-domain reference)** — 예: ip cypher 가 auto.SUPPLIED_BY 참조 | wired (WARN 강등) | P3 | strict 모드 결정 필요 — cross-domain reference 를 ERROR 로 강등할지 WARN 유지할지 | scripts/audit/ontology_validate.py |

---

## 트리거 그룹별 요약 (병렬 실행 가능)

### KEY 발급 (1회 사용자 액션, 다수 항목 unblock)

| 키 | unblock 항목 |
|---|---|
| `DATA_GO_KR_API_KEY` | D-1, D-5, EV-1, EV-2, G-1, PG-1, G-4 (KOTSA 한글 리콜 경로) |
| `KIPRIS_API_KEY` | D-2, IP-1, IP-2, IP-4, IP-5, IP-6 |
| `KOSIS_API_KEY` | D-8 |
| `BIGDATA_TIC_CLIENT_ID/SECRET` | (KATRI / bigdata-tic) 별도 항목 |
| `KNCAP_API_KEY` | N-2 |

### LLM 키 (다수 측정 unblock)

| 작업 | unblock 항목 |
|---|---|
| `make eval-full / eval-auto / eval-cross` | E-1, E-2, PG-2 (cross 정확도), Q-2 (calibration), §10.7~10.10 DoD |
| `make audit-eval-matrix --full` | S-4 (축소 매트릭스 full) |

### Bulk 데이터 (무인증, 즉시 가능)

| 다운로드 | unblock 항목 |
|---|---|
| USPTO ODP bulk (data.uspto.gov) | D-3, IP-1, IP-3 |
| CPC scheme subgroup 250K bulk | IP-7 |
| KAMP CSV 15089213 | D-4 |

### 설계·구현 (코드 작업)

| 작업 | unblock 항목 |
|---|---|
| Streamlit 검토 UI (Bridge candidate) | Q-1, Q-3 |
| API 인증 / Rate limit | O-1 |
| Production 배포 가이드 | O-2, O-3, O-5, O-6 |
| CI/CD 파이프라인 | O-4 |
| ADR 작성 | F-3, R-1, R-2 |

---

## 권장 실행 순서 (3 단계)

### 즉시 (1주, P0 차단)

1. **O-1 API 인증** — 외부 노출 전 필수 (보안)
2. **Q-1 Bridge SOP** — 4,792 candidate 영속 누적 위험 (데이터 품질)
3. **O-2 Production guide** — 배포 절차 문서화

### 1개월 내 (P0+/P1)

1. **S-1 + S-2 + S-4 상용 신호 full** — `pip install -e ".[mcp]"` + Langfuse 키 + `make audit-eval-matrix --full`
2. **D-1 + PG-1 ProcessGraph 회사 귀속** — 팩토리온 키 → `PERFORMED_AT` ≥ 30
3. **D-2 + D-3 + IP-1~4 특허 데이터** — KIPRIS/USPTO key 확보 + bulk → ip 보조축 thesis 완성
4. **E-1 + Q-2 평가 + calibration** — LLM 키로 headline 매트릭스 + Platt scaling

### 분기별 (P2)

1. **L6-1~4 배터리·소재** — 데이터 먼저 확보
2. **EV-1~2 EV 충전** — D-1 키 공유
3. **A-1~A-4 도구·HITL 보강** — 운영 데이터 후
4. **F-1~F-2 CONTRIBUTING / TROUBLESHOOTING** — 외부 협력 단계

---

**문서 끝.**

> 본 backlog 는 PR 마지막 단계에서 갱신. 완료 항목은 (완료) 표시 + 다음 PR 에서 제거. P0/P1 신규 발견은 즉시 추가. P2/P3 는 분기별 검토.

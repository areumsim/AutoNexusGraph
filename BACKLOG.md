# BACKLOG — AutoNexusGraph 전수 미완료 항목 SSOT

> **위치**: 루트 단일 SSOT. 모든 "예정 / scaffold / wired-but-disabled / TODO / 미구현 / 데이터 대기 / 키 부재" 항목 전수.
>
> **상위 SSOT**: 요약 + P0+/P1 트래픽라이트는 [README §12 보완 개발 백로그](./README.md#12-보완-개발-백로그-critical-gaps), 정량 게이트 본문은 [README §10 DoD 20항](./README.md#10-dod-definition-of-done--20-항). 본 문서는 **세부 항목 + 활성화 트리거** 풀 카탈로그.
>
> **갱신 주기**: PR 마지막 단계에서 항목 추가·이동·완료. `make audit-dod` 가 자동 반영하는 항목은 (자동) 라벨.
>
> **버전**: v1.2 (2026-06-05, eval matrix 실측 + 신규 런타임 버그 anchor — S-4/PG-2/E-1/E-3 결과 반영 + A-7/A-8/A-9 추가). **89 항목 / 15 카테고리 / P0+/P0/P1/P2/P3 트래픽라이트** (v1.1 86 항목 → +3 신규 / S-4 측정 완료 — thesis 반증 신호).

---

## 0. 요약 통계 + 우선순위 정의

| 카테고리 | 항목수 | P0 | P1 | P2 | P3 |
|---|---:|---:|---:|---:|---:|
| 1. 데이터 인입 (키 / bulk download) | 10 | 2 | 2 | 1 | 5 |
| 2. 그래프·엣지 적재 | 6 | 1 | 1 | 2 | 2 |
| 3. 에이전트·도구·HITL | 9 | 0 | 3 | 4 | 2 |
| 4. 상용 신호 (MCP / Langfuse / SHACL / 매트릭스) | 6 | 0 | 3 | 2 | 1 |
| 5. 운영·보안·배포 | 8 | 2 | 1 | 4 | 1 |
| 6. Bridge·데이터 품질·calibration | 5 | 1 | 1 | 1 | 2 |
| 7. 평가·신뢰성·gold QA | 8 | 0 | 3 | 4 | 1 |
| 8. 문서·DX | 8 | 0 | 0 | 5 | 3 |
| 9. ProcessGraph 회사 귀속 + KAMP + 품질 | 3 | 1 | 1 | 1 | 0 |
| 10. IPGraph 데이터 적재 + bridge join | 7 | 0 | 4 | 1 | 2 |
| 11. 배터리·소재 L5/L6 | 5 | 0 | 0 | 4 | 1 |
| 12. EV 충전 인프라 | 2 | 0 | 0 | 2 | 0 |
| 13. NCAP / Euro NCAP / IIHS | 4 | 0 | 0 | 0 | 4 |
| 14. 라우팅·정책·미정 결정 | 2 | 0 | 0 | 1 | 1 |
| 15. 온톨로지·schema | 2 | 0 | 0 | 1 | 1 |
| **합계** | **89** | **7** | **20** | **31** | **26** |

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
| D-1 | **팩토리온 공장 등록 (15087611)** — 회사·공장번호·산단별 조회 | (부분 적재) — `auto.factoryon_registry` **90행** (현대차·기아·한국지엠·쌍용·르노 OEM 5사 + 현대모비스 27/현대제철 19/현대위아 11 등 tier-1, `DATA_GO_KR_API_KEY` 작동, 2026-06-04 확대 적재) | **P0** | ✅ :Plant 74 승격 + PERFORMED_AT 59 candidate (`load_factoryon_plants.py`). (잔여) 커버리지 추가는 `make ingest-factoryon-company NAME=...` → `make load-factoryon-plants` | README §7, BACKLOG §9 (ProcessGraph #19 직접 의존) |
| D-2 | **KIPRIS Open API** — 한국 특허·출원 | (scaffold, 보조) | **P1** | `KIPRIS_API_KEY` 발급 (공공데이터포털) → `make ingest-kipris` (ingestion/loader/DDL 구현됨, 키·데이터 부재) | docs/ipgraph.md §4, BACKLOG §10 |
| D-3 | **USPTO Open Data Portal (PatentsView 후속)** — 미국 특허·인용·assignee | (scaffold, 보조) | **P1** | bulk download (data.uspto.gov) → `make ingest-uspto-odp` (ingestion/loader/DDL 구현됨, bulk 데이터 부재). PatentsView REST 종료 (2026-03-20, 410 Gone) | docs/ipgraph.md §4 |
| D-4 | **KAMP 제조AI 데이터셋 (15089213)** — 사출/용접/프레스 시계열·불량 | (scaffold) | P1 | CSV 수동 다운 → `make load-kamp-process-metrics`. `auto.process_metrics` (corp_code 컬럼 의도적 부재 = 익명) | docs/process_graph.md §2, BACKLOG §9 |
| D-5 | **자동차 리콜정보 (3048950, CSV)** — 한국 OEM 리콜. 구 오픈API 15089863 폐기 | ✅ **적재 완료** — `auto.events_recalls` **941행** (CSV 전량, source=datagokr_kotsa, 무인증) | P2 | (잔여) 신규 CSV 릴리스 시 재적재 `make load-datagokr-recalls --csv <path>` | README §4, docs/data_sources.md §B1 |
| D-6 | **자동차검사관리 (15155857)** — 사고·침수·도난 검사 | (부분 적재) | P3 | CSV 파일 다운 (무인증) → `make ingest-datagokr-inspections`. **이미 47,171 row 적재 완료 (2016~2025, `auto.events_inspections`) — 이 항목은 신규 채널 보강용** | docs/data_sources.md |
| D-7 | **공정위 기업집단 데이터** | (차단·데이터셋 확정 2026-06-10) — `ingestion/ftc_client.py` 의 기존 `odcloud/15083033` 은 **오설정**(15083033 = 소상공인 상가정보, 기업집단 아님 + UDDI 플레이스홀더). **올바른 소스**: `공정거래위원회_지정된 대규모기업집단 조회 서비스` dataset **15091886**, endpoint `https://apis.data.go.kr/1130000/appnGroupSttusList/appnGroupSttusListApi` (계열 15091898 임원/15091902 참여업종). 현 `DATA_GO_KR_API_KEY` 는 1130000 서비스 **미등록 → 403 Forbidden**. | P3 | (1) data.go.kr 에서 dataset 15091886 활용신청 (2) ftc_client 를 apis.data.go.kr/1130000 포맷으로 재구현(파라미터·응답 파서 상이) (3) → Neo4j Group + BELONGS_TO_GROUP 적재 → FIN-L2-007 기업집단 gold 해금 | README §4, ftc_client.py |
| D-8 | **KOSIS 산업 통계 (광공업동향)** — 제조업 생산지수 by KSIC | (scaffold) | P3 | `KOSIS_API_KEY` 발급 → `make ingest-kosis` → `make load-kosis` → `macro.kosis_series` (ingestion/loader/DDL 구현됨, 키·데이터 부재) | README §4 |
| D-9 | **LAW.go.kr 법령** | (예정) | P3 | open.law.go.kr 키 → `law.laws` | README §4 |
| D-10 | **KAMP CSV ID `15089213` 외부 URL 유효성 검증** (D-4 보조 트리거 분리) | 미검증 (본 세션 발견) | P3 | data.go.kr 접속 → CSV URL 존재성·파일포맷·schema 확인 → `data/raw/kamp/15089213/` 배치 후 D-4 unblock | docs/operations/api_keys_pending.md §6 Bulk 데이터 |

---

## 2. 그래프·엣지 적재

| ID | 항목 | 상태 | 우선순위 | 활성화 트리거 | 위치 |
|---|---|---|:---:|---|---|
| G-1 | **`PERFORMED_AT` (회사 귀속 공정)** ≥ 30 | ✅ **충족 94** — manual_seed 35 validated(`load_performed_at.py`, B 0.85) + factoryon 59 candidate(`load_factoryon_plants.py`, :Plant A등급 + 업종→공정 추론 0.60). :Plant 29→103, OWNS_PLANT 53→60. 산단공 익명 스텝 무오염, 비귀속 위반 0 | (완료) | (잔여) DART 생산·설비 파생 추가 + factoryon 일반부품 업종 공정 매핑 정밀화 | README §10.19, docs/process_graph.md §2 |
| G-2 | **`PRODUCED_BY` (Part→ProcessStep)** | ✅ **46 candidate** — `load_produced_by.py`. :Part 46개 NHTSA system → 공정 카테고리 추론 (파워트레인18/가공15/의장11/프레스2). 산단공 part_id 부재로 deterministic BoP routing 불가 → candidate/0.50, 외주부품=의장(조립 진입). Part→ProcessStep→Process BoP 경로 완성 | (완료) | (잔여) 산단공 part_id 또는 DART 공정도 확보 시 B 격상 | docs/process_graph.md §2 |
| G-3 | **`CONSUMES_MATERIAL` / `USES_EQUIPMENT`** | ✅ **6 / 16** — `load_process_resources.py`. 파워트레인(배터리셀)→L6 소재 6(validated 0.80) + 9 공정유형→표준 제조설비 16(validated 0.50, Equipment 13 신규). ProcessStep→Material→Mineral L6 하향 경로 17 완성 | (완료) | (잔여) 산단공/Wikidata 실 소재·설비 데이터로 확대 | docs/process_graph.md §2 |
| G-4 | **`CAUSED_BY_PROCESS` (Recall→Process)** | ✅ **96 candidate** — `load_recall_process_map.py`. KOTSA 한글 리콜 941행 결함요약 + 공정키워드+결함지시어 deterministic 매칭 (조립71/가공11/용접11/사출2/프레스1), 전부 candidate/0.50 (인과 추론, 단독 근거 금지). 단조(첨단조향) 노이즈 차단. 한글-한글 매칭으로 환각위험 회피 | (완료) | (잔여) LLM P3 cross-validate 정밀화 | docs/process_graph.md §2 |
| G-5 | **`MAPPED_TO` (Assignee→Company, IP→finance 브릿지)** | (scaffold, 보조) — loader(`load_assignee_corp_map.py`)+cypher+ontology 완비, **데이터 0** (`ip.assignee_corp_map`/`ip.patents` 0행) | P3 | KIPRIS/USPTO 키(D-2/D-3) → 특허·assignee 적재 → 매핑. **'BOM↔공정'은 오기 — 실제는 IP assignee 브릿지** | ontology/ip/relations.yaml:88 |
| G-6 | **`USES_PROCESS` (Module → Process)** | ✅ **189** — `load_uses_process.py` + ontology 정의 신규 추가(이전엔 미정의). Module.system_code→공정 매핑(의장144/가공18/프레스15/파워트레인6/사출6), candidate/0.50. PRODUCED_BY 의 모듈 수준 대응 | (완료) | (잔여) 산단공 part_id deterministic 격상 | README §12.5 |
| G-7 | **`DEFECT_MATCHES` Bridge (`:Recall`↔`:DefectType`)** | ✅ **7,417 엣지** — `:DefectType` 50 (NHTSA+KOTSA defect_summary 1,434 → Claude Code Agent 라벨링) + cosine_topk 7,218 (BGE-M3 top-3) + llm_assign 199 (sample 200건 Agent 분류). 정제 SOP 후 590 validated/85 rejected/6,742 candidate. **외부 API 호출 0** (Anthropic 401 우회) | (완료) | EU sample 200건 추가 Agent 분류 → EU validated 확장 / cos≥0.55 회색지대 사람 검토 SOP | docs/data_lineage.md §4.2 |
| G-8 | **`MANIFESTS_AS` (`:FailureMode`↔`:DefectType`) + `SUBJECT_TO` (`:Equipment`↔`:FailureMode`)** | ✅ **MANIFESTS_AS 72** (cosine 36 + llm 36, 정제 후 14 validated) + **SUBJECT_TO 18** (`:Equipment` battery/bearing/igbt 3) — NASA PCoE Bearing/Battery/IGBT readme/논문 1.4GB → Agent 18 `:FailureMode` 추출. 가이드 §1.x 4-홉 회사귀속·회사무관 추적 처음 동작 | (완료) | NASA C-MAPSS/Milling 제외 — ROI 낮음 | docs/data_lineage.md §2.15·§4.2 |
| G-9 | **`master_manufacturers` dedup canonical SOP** | ✅ **21 dup row → 8 canonical** — 한국 OEM (HYUNDAI 5/KIA 4/GENESIS 3) + FORD 10 + COMET/COMMANDER/CONDOR/CORBIN MOTORS/CROWN COACH/MOTOR COACH INDUSTRIES 7. NHTSA vPIC × Wikidata × 자회사 중복 통합. canonical = refs total (recalls+models+complaints+investigations) 최다. cross-jurisdiction 매칭 0→9건 (현대·기아 EU+NHTSA ICCU 글로벌 검출) | (완료) | supplier dedup + person dedup 동일 SOP 적용 가능 | docs/data_lineage.md §4.2.1 |

---

## 3. 에이전트·도구·HITL

| ID | 항목 | 상태 | 우선순위 | 활성화 트리거 | 위치 |
|---|---|---|:---:|---|---|
| A-1 | **`sensitive_decision` HITL trigger 정책** | wired (interrupts.py) + 휴리스틱 활성 (SENSITIVE_KEYWORDS 10종) | P1 | 운영 데이터에서 false-positive 측정 → 키워드 정정. nodes.py:668~688 게이트 활성 | README §7 (HITL sensitive_decision 행) |
| A-2 | **P3 LLM 4종 활성화** — COMPETES_WITH / MANUFACTURED_AT(LLM) / CONTAINS_MODULE / CONTAINS_PART | `enabled:false` | P1 | 비용·환각 위험 검증 후 selectively 활성. validation gate 강화 | README §12.5, ontology/auto/relations.yaml:226-235 |
| A-3 | **HITL `clarification`/`cost_approval` 무한 루프 가드** | wired | P2 | (P2) Streamlit dialog 의 resume 재진입 횟수 cap. 의도적이지만 미구현 | docs/operations/agents.md |
| A-4 | **새 Cypher 템플릿** — recall 전파 · 공급 집중도 · 시점 정합 cross | finance 22 + auto 27 + ip 25 = 74 | P2 | use case 별 신규 템플릿. 자유 Cypher 금지 원칙 유지 | README §12.5 |
| A-5 | **N-domain bridge 일반화** — `bridge.drug_entity` 등 다형 | `bridge.corp_entity` 만 (2-domain 가정) | P3 | 4번째 도메인 추가 시. 또는 `bridge.cross` 다형 1 테이블 | README §12.5 |
| A-6 | **DomainHandler intent allowlist 확장** | finance / auto / ip 각각 정의 | P3 | 새 도메인 추가 시 자동 확장. 신규 intent 추가 시 화이트리스트 갱신 | src/autonexusgraph/agents/_domain_handler.py |
| A-7 | **LangGraph checkpointer Date msgpack 직렬화 실패** | 본 세션 발견 (2026-06-05) — `[run_agent] LangGraph 실행 실패 — 함수 체인 폴백: Type is not msgpack serializable: Date` (eval matrix 30 cells 중 다수). Cypher 결과의 `neo4j.time.Date` 객체가 checkpointer 직렬화 단계에서 실패 → 함수 체인 fallback 으로 우회 (silent degrade) | P1 | tools/graph.py 또는 cypher 결과 변환 단계에서 `Date` → ISO `str` 변환. fallback 통계 (몇 % turn 이 함수체인으로 떨어지는지) 측정. 회귀 가드 추가 | src/autonexusgraph/agents/graph.py · src/autograph/tools/graph.py |
| A-8 | **calculator tool expr 누락 호출 패턴** | 본 세션 발견 (2026-06-05) — `[calculator] failed: expr 필요` (eval log 다수). LLM planner 가 calculator task 생성 시 args 에 expr 누락 → tool 즉시 fail. | P2 | calculator tool args 검증 보강 (expr 부재 시 명확한 에러 + planner 가 retry 유도). 또는 LLM planner prompt 에 calculator 호출 시 expr 필수 명시 + 예시 추가 | src/autonexusgraph/tools/calculator.py · src/autonexusgraph/agents/llm_planner.py |
| A-9 | **planner 화이트리스트 밖 sql:매출 조회 drop** | 본 세션 발견 (2026-06-05) — `[llm_planner] 화이트리스트 밖 N task drop: ['sql:현대모비스 매출 조회', 'research:매출 추이 검색', 'graph:이재용 임원 회사 검색']` 다수. LLM planner 가 자연어 task description 생성 → DomainHandler allowlist (좁은 intent 집합) 와 매칭 안 됨 → 전 task drop → 결과 없음 → grounding fail | P2 | (a) DomainHandler allowlist 를 LLM planner prompt 에 명시 노출 (b) intent 정규화 layer 추가 (LLM 자연어 → intent enum 매핑) (c) drop 률 측정 + 임계 초과 시 alert | src/autonexusgraph/agents/_domain_handler.py · src/autonexusgraph/agents/llm_planner.py |

---

## 4. 상용 신호 (MCP / Langfuse / SHACL / 평가 매트릭스)

| ID | 항목 | 상태 | 우선순위 | 활성화 트리거 | 위치 |
|---|---|---|:---:|---|---|
| S-1 | **MCP 래퍼** — typed tool pool 78 tools (finance 21 + auto 38 + ip 19) | (wired) — `make audit-mcp` SDK 설치 시 **PASS** (build_mcp_server boot + 78 tools, `ListToolsRequest` round-trip), 미설치 시 SKIPPED(fail-soft). ipgraph.tools 19종 discovery 합류 (`mcp/discovery.py` `_DOMAIN_MODULES['ip']`) | **P0+** | `pip install -e ".[mcp]"` 또는 `[all]` extras → `python -m autonexusgraph.mcp` stdio server | README §10.17 (a) |
| S-2 | **Langfuse 실측 ON (turn별 token/cost/replan)** | (wired) — Langfuse 4.x OTEL native. **2026-06-04**: `audit-trace` 가 PG 적재 경로와 Langfuse export 를 분리 — LANGFUSE 키 없이도 PG token/cost/replan 실측 PASS (이전엔 키 부재 시 no-op SKIP). cloud export 만 키 대기 | **P0+** | (PG 경로 ✅) `LANGFUSE_*` 키 → `make audit-trace --full` 로 cloud export 까지 · [runbook Step 3](./docs/operations/api_keys_pending.md#step-3--langfuse-cloud-export-선택-langfuse-키-발급-시) | README §10.17 (b) |
| S-3 | **온톨로지 SHACL/pydantic 검증** | ✅ **완료** — 핵심 6 yaml + **보조 4 yaml(Y-1: `auto`/`finance` extractors · system_taxonomy · plants, `extra='forbid'` strict)** + cypher↔yaml cross-check 모두 PASS. cross-domain ref strict 모드(Y-2 `--strict-cross`). `make audit-ontology`(`ontology_validate.py` + `tests/test_ontology_aux.py` 5건). **잔여**: SHACL 정식 shape 그래프는 pydantic v2 로 대체(의도된 trade-off, PRD §11.1) | (완료) | — | README §10.17 (c) |
| S-4 | **축소 평가 매트릭스 실측 (4 어댑터 × FAST tier 1종 + rerank ablation)** | ✅ **측정 완료** (2026-06-05, Anthropic claude-haiku-4-5, 10 cells × 30 row = 300 evals, total **$0.60**) + **EM 측정 버그 수정** (이 브랜치). 직전 "thesis +0.0%p (둘 다 EM=0)" 은 **측정 artifact** — EM 이 산문 답변 vs 짧은 gold 를 full-string equality 로 비교하고 gold_answer_text 부재 row(26/30)까지 0 으로 평균에 포함 → 전 셀 EM=0 으로 깔림. 수정: span-aware containment EM(gold⊆답변) + scorable-row 한정 평균 + multi-hop gold scorable<5 면 thesis primary→hits 전환(`em_status=insufficient_gold`). 기존 artifact 재채점 결과 vector/sql_vec/hybrid EM **0.0→0.25** (gold 보유 4 row 중 1 정답), graph 0(실제 미응답 — 진짜 결과). **진짜 신호**(thesis primary=hits): hits@k **vector 0.967 > sql_vec 0.900 > hybrid 0.433 > graph 0.300** — hybrid 가 vector 를 못 이김(PRD §10.7 가정 반대, 정직 측정). 원인 가설: gold 30 의 multi-hop gold answer 1/16 + Neo4j sparse. DoD §10.7 ⚠️(gold curation 미완으로 EM 보류·hits 기준 미달) / §10.14 ✅ internal pass=100%. **2026-06-10 정식 재측정** (GPT-4o, BGE-M3 임베딩+리랭커 기동 + LLM-planner schema fix(PR#52) + 예산 헤드룸, $1.25, `audit_eval_matrix_20260610T053334Z.json`): hits@k **vector 0.875 > hybrid 0.5 = −37.5%p ❌**(hybrid 0.5 로 기능 확인 — 이전 무효 run 의 0.0 아님), §10.14 internal 100% ✅, EM insufficient_gold(2/30). 발견 버그 2건: (i) hybrid eval 무효화는 agent 코드 아니라 **24h 세션 비용 가드 $5 소진**, (ii) **OpenAI strict structured-output 이 free-form `args` object 와 비호환** → LLM planner 항상 실패(PR#52 strict=False 로 수정). (잔여: gold QA 확장 + Neo4j 보강 후 thesis 재측정; OpenAI/Google billing 후 8/12 cells) | **P0+** | (1) gold QA 확장 + Neo4j 적재 보강 후 thesis 재검증 (2) OpenAI billing 충전 후 8 cells 추가 (3) `pip install google-generativeai` → 12 cells · [runbook Step 1](./docs/operations/api_keys_pending.md#step-1--평가-매트릭스-full-실측-15-30-분-5-20) | README §10.17 (d), 결과 JSON: `data/reports/audit_eval_matrix_20260605T065225Z.json`; EM 수정: `eval/metrics/em_f1.py::exact_match_contains` |
| S-5 | **§10.12 baseline reset 정책 dashboard 자동 반영** | (wired) — baseline reset 2회 이력 | P1 | `make audit-dod` 출력에 baseline commit + 누적 reset 이력 + "도메인 추가 마다 reset" 명시 (대부분 완료, dashboard 표시만 보강) | README §10.12 |
| S-6 | **api_keys_pending.md §"One-Shot Runbook" ↔ BACKLOG cross-link** | ✅ **완료** (2026-06-05) — 5 row 활성화 트리거에 `[runbook Step N]` cross-link 추가: S-4·E-1 → Step 1, Q-2 → Step 2, S-2 → Step 3, E-3 → Step 4. D-2/D-3/D-8 은 runbook 비대상(LLM 키 외 외부 API) — 미적용. | (완료) | — | docs/operations/api_keys_pending.md §"One-Shot Runbook" |

---

## 5. 운영·보안·배포

| ID | 항목 | 상태 | 우선순위 | 활성화 트리거 | 위치 |
|---|---|---|:---:|---|---|
| O-1 | **API 인증 / Rate limit** | ✅ **구현** (`api/auth.py` + `test_api_auth.py` 12건) — API key 헤더 (`X-API-Key`/`Bearer` + `API_KEYS` env) + thread_id↔user_id 바인딩 (타인 403) + per-identity in-memory rate limit. **잔여 (P2)**: OAuth2/OIDC 발급기관 연동, multi-instance 분산 (redis/reverse proxy) | ~~P0~~ → **P2** (잔여) | (잔여) 외부 IdP 통합 시 | README §12.2 |
| O-2 | **Production 배포 가이드** — `docs/operations/production_deploy.md` | ✅ **작성** (+ `infra/Dockerfile` + `docker-compose.prod.yml` 실행 가능) — 이미지 빌드 / compose prod 오버레이 / health probe / reverse proxy·TLS / k8s / blue-green·canary / 멀티 인스턴스 주의점. dev Quickstart 분리. `.gitignore` `.env.*` 보강. 백업·DR(O-3 ✅) / 모니터링(O-5 ✅) 별도 구현 | (완료) | — | README §12.3 |
| O-3 | **백업·DR** — PG dump + Neo4j backup + RPO/RTO | ✅ **구현** — `scripts/ops/{backup,restore}.sh` + `make backup`/`restore` + [backup_dr.md](./docs/operations/backup_dr.md) (PG pg_dump -Fc / Neo4j community STOP→dump→START / 보존 prune / RPO≤24h / RTO 수분(dump 보유)·수시간(재앙)). **잔여**: off-site 동기화 cron 등록 + 분기 복원 드릴 RTO 실측 | (스크립트·문서 완료) | cron 등록 / 드릴 | README §12.3 |
| O-4 | **CI/CD 파이프라인** | ✅ **구현** — `.github/workflows/ci.yml`: smoke-e2e 게이트 (py3.10/3.11/3.12 matrix, keyless) + lint/mypy informational + DoD dashboard artifact. **잔여**: `audit-dod --strict` 게이트 (§10.7/§10.13 LLM eval 필요 → keyless 불가) + ephemeral PG/Neo4j 통합테스트 (integration 마커 0건) — secrets/self-hosted 후 | (코어 완료) | LLM 키 / self-hosted runner | README §12.3 |
| O-5 | **모니터링·알람** — Prometheus + Grafana | ✅ **구현** — `metrics_exporter.py`(prometheus_client 없이 텍스트 렌더, audit 모듈 조합) `make metrics`/`serve-metrics` + `infra/monitoring/`(prometheus.yml/alerts 6규칙/grafana 8패널) + compose prod metrics/prometheus/grafana 서비스 + [monitoring.md](./docs/operations/monitoring.md). 테스트 5건. 메트릭: up/chunks/nodes/bridge/cost/stale/llm_turns/scrape_errors | (코어 완료) | Alertmanager 발송 채널 연동 | README §12.3 |
| O-6 | **TLS / Secrets / PII 정책** | uvicorn http 만, `.env` 한 곳, PII 정책 미정의 | P2 | nginx/caddy reverse proxy + HSTS + cert renewal. vault / k8s secret. master.persons 9,948 (name, birth_year) GDPR-style 삭제 권리 + log redaction | README §12.2 |
| O-7 | **싱글톤 lru_cache 패턴 audit** — `get_connection`/`get_pool` 외 다른 `@lru_cache(maxsize=1)` 함수도 health check 필요한지 검토 | ✅ **PG conn/pool 완료** (2026-06-05) — `get_connection`/`get_pool` 둘 다 `_open_*` (raw) + 게이트 (health check) 분리, `closed`/`broken` 자동 폐기·재생성. transaction() rollback 실패 시 cache_clear. 회귀 가드 4건. **잔여**: `neo4j.get_driver()` / `qdrant.get_client()` / `llm.get_llm_client()` 등 다른 lru_cache 함수도 동일 audit 필요 (서버 disconnect 시 stale instance 들고 있을 가능성). | (PG 완료) | 다른 lru_cache 함수 audit + 필요 시 동일 패턴 적용 | docs/architecture.md (싱글톤 컨벤션 박스 후속) / `src/autonexusgraph/db/{neo4j,qdrant}.py` / `src/autonexusgraph/llm/base.py` |
| O-8 | **실 운영 검증 매트릭스** — 본 세션 신규 인프라 DB 환경 실측 | (DB 환경 대기) | P2 | DB up 후 1회 sweep: `make load-materials-metals` (L6-2 loader, MADE_OF 매칭률) · `make feedback-stats` (E-4 분포 출력) · `make audit-dod` (S-5 dashboard baseline reset 표시 검증) · `make load-kamp-process-metrics` (F-5 타겟 graceful skip) · `make load-materials-metals-dry` 후 실 적재. | Makefile + 본 세션 commit 추적 |

---

## 6. Bridge·데이터 품질·calibration

| ID | 항목 | 상태 | 우선순위 | 활성화 트리거 | 위치 |
|---|---|---|:---:|---|---|
| Q-1 | **Bridge candidate 4,792 검토 SOP** | ✅ **구현** — `bridge_review.py` (사전 정의 함수) + `ui/bridge_review.py` (Streamlit ✓/✗ UI) + `auto_expire_stale`(6개월 미검토 자동 rejected) + `review_progress_kpi` + `26_bridge_review.sql`(reviewed_at/by 감사 컬럼) + `make bridge-kpi`/`bridge-expire` + 테스트 13건 + [SOP 문서](./docs/operations/bridge_review.md). **잔여**: 4,792 candidate 실제 라벨링은 사람 작업 (UI/cron 준비됨) | (도구 완료) | 사람 검토 실행 / expire cron 등록 | README §12.4 |
| Q-2 | **confidence_score calibration** — A=0.95 / B=0.80 / C=0.50 가 실제 정답률과 단조 미검증 | 측정 인프라 wired (`scripts/audit/calibrate_confidence.py`) | P1 | LLM 키 활성 후 `make eval-full` → `make audit-calibrate` 1회. Platt scaling + 10-bin reliability diagram. systematic 어긋남이면 §4.0 표 재조정 · [runbook Step 2](./docs/operations/api_keys_pending.md#step-2--confidence-calibration-5-분-llm-호출-0) | README §4.0 (Calibration 박스), §12.4 |
| Q-3 | **`master.persons` 동명·동년생 충돌 빈도 측정** | ✅ **측정 routine 구현** — `persons_collision.py` + `make persons-collision` (NULL birth_year 비율 / 동명 다중 row / NULL+비NULL 혼재 / distinct-corp 과다 병합의심 후보). 테스트 4건 | (routine 완료) | 실측 후 충돌률 높으면 (name, birth_year, 회사) 보조 키 도입 | README §12.4 |
| Q-4 | **embedding backfill 진행률 가시화** | ✅ **구현** — `make embed-status` (`embed_status.py`, read-only) — 전체 + `source`별 embedded/total/pct/pending. 테스트 4건. **잔여**: 누락 청크 자동 재시도 cron (`make embed-chunks` 반복) | (도구 완료) | BGE 서버 가동 후 재시도 cron | README §12.4 |
| Q-5 | **데이터 freshness 모니터링** | ✅ **구현** — `freshness.py` + `make freshness` (8 소스: DART/vec.chunks/NHTSA recall·complaint/SEC/IP/bridge/persons — ingest·content 시각 + stale 판정, stale/error 시 exit 1 cron 알람). 소스별 graceful. 테스트 8건 | (도구 완료) | cron 등록 + stale-days 튜닝 | README §12.4 |

---

## 7. 평가·신뢰성·gold QA

| ID | 항목 | 상태 | 우선순위 | 활성화 트리거 | 위치 |
|---|---|---|:---:|---|---|
| E-1 | **12 조합 매트릭스 실측** (4 어댑터 × 3 LLM) | ⚠️ **Anthropic 단일 실측 완료** (cross 층화 코드 unblock — PR #19 `level` 필드 SSOT 동기화) (2026-06-05, total $0.89 across 3 runs) — (1) audit-eval-matrix-full: 10 cells × 30 finance row = $0.60. vector hits 0.97 > sql_vec 0.90 > hybrid 0.43 > graph 0.30. (2) eval-auto: hybrid × 56 row = $0.17 (hits 0.232 / f1 0.003). (3) eval-cross: hybrid × 49 row = $0.13 (hits 0.449 / f1 0.001). **모든 run EM=0 은 측정 artifact** 였음 (산문 답변 vs 짧은 gold full-equality + gold_answer_text 부재 row 평균 포함) — 이 브랜치에서 span-aware EM + scorable-row 한정으로 수정(S-4). 재채점 시 gold 보유 row 에서 EM 측정됨; 실제 약점은 hits@k(hybrid<vector) + gold curation 부족. multi-provider 비교는 OpenAI billing + Google SDK 후 8 cells 보강 | P1 | OpenAI billing 충전 + `pip install google-generativeai` 후 anthropic + openai + google 풀 매트릭스. cross-provider 차이 + thesis 재검증 · [runbook Step 1](./docs/operations/api_keys_pending.md#step-1--평가-매트릭스-full-실측-15-30-분-5-20) | README §12.6, 결과 JSON: `data/reports/audit_eval_matrix_20260605T065225Z.json` · `eval/reports/{auto_20260605_070802,cross_20260605_070808}/` |
| E-2 | **gold QA 확장 + EM scorable 보강** — finance 30 / auto 56 / cross 49 (CD-L1:10/L2:9/L3:18/L4:12) / ip 30 → 각 100 row + 외부 큐레이터 30% | seed 적재 완료. **2026-06-10 finance gold_answer DB 큐레이션 11→14행** (LG화학 자산총계·현대모비스 매출·현대차 자회사 — `anxg_fin`/Neo4j 실값). **⚠️ 핵심 블로커 발견**: thesis multi-hop EM(scorable≥5 필요)이 **gold curation 단독으로 측정 불가** — multi-hop 16행 중 깨끗이 큐레이션 가능 3행뿐. 원인 = **질문↔데이터 불일치/그래프 품질**: 이재용 임원=동명이인(SK/현대해상), SK하이닉스·POSCO corp_code 부재, 기업집단(BELONGS_TO_GROUP) 미적재, 자회사=해외법인(질문 의도 기아/현대모비스와 불일치). 따라서 thesis EM 은 hits primary 유지(insufficient_gold). **2026-06-10 그래프 밀도 점검**: 회사 단위 관계는 조밀(EXECUTIVE_OF 36,399 / MAJOR_SHAREHOLDER_OF 16,725 / SUBSIDIARY_OF 8,661 / 상장 295사 고립 0). 단 **뉴스 그래프 sparse**(NewsEvent 85, CO_MENTIONED 0 → FIN-L2-009 POSCO 공동언급 답 불가) + 관계 유형 1,002종 중 536종이 1건짜리(뉴스 LLM free-form 노이즈). **alias 추가(PR#57)로 FIN-L2-005 현대차-SK하이닉스 최단경로 길이2 해금**, 삼성 사외이사 20명 존재. Person 중복 dedup **적용 완료**(PR#55 코드 + 2026-06-10 DB 적용: 14,536→12,897, **1,639 중복 제거**, 1,161 그룹 병합, distinct (인물,회사) executive 쌍 12,063 **무손실 검증**, 고립 0, UNIQUE 제약 person_name_birth_unique 생성. 논리 백업 `data/backups/neo4j_persons_predupe_20260610.jsonl`). **2026-06-10 후속: 현재 데이터로 답 가능한 multi-hop 2건 추가 큐레이션(사외이사 겸직·최단경로, PR#59) → scorable 3→5 임계 도달 → 실측서 `em_status=ok` 확인**(vector EM 0.40 = hybrid 0.40, #13 메인홉 0.375 ✅도 측정 가능해짐). 단 hits/EM 모두 hybrid 우위 없음(thesis 반증 유지). **2026-06-11 Allganize 외부 벤치 흡수**: `allganize/RAG-Evaluation-Dataset-KO` HF finance 60 → `gold_qa_allganize_v0.jsonl`. **외부 큐레이터 비율 0%→26.7%**(finance 66.7%, self-bias 완화). 단 Allganize 는 자체 PDF 코퍼스 기반이라 **답변 실측엔 원문 PDF 의 vector 적재 필요**(우리 코퍼스=DART) — QA 쌍은 즉시 유효. | P1 | (a) Allganize 원문 PDF 적재(answerability) + 30% 완성(auto/cross/ip 외부) (b) 그래프 데이터 보강 **또는** gold 질문 재작성 | README §12.6, docs/gold_qa_guide.md |
| E-3 | **§10.13/14 trace 메트릭** — hop 수 + tool call sequence | ✅ **구현 + 실측** (2026-06-05) — `agents/hop_metrics.py` (tool_results→hop/seq 파생) → per-turn trace 기록 (Langfuse `end_meta` + PG `chat.messages.agent_trace`) + eval pred_row `hop_count`(cypher 파생) + `main_hop_efficiency` 실제 hop 경로(`hybrid_vs_vector_hops`). 테스트 15건. **simulation → 실측 전환 완료**: §10.13 ❌ (hybrid/vector ev_avg ratio 1.067 > 0.7, audit_eval_matrix_20260605T065225Z.json) / §10.14 ✅ (internal pass=100%) | (완료, 실측) | (잔여) hybrid 가 vector 보다 효율 떨어지는 원인 분석 + 그래프 적재 보강 후 재측정 | README §12.6 |
| E-4 | **답변 사용자 피드백 루프** — 👍/👎/📝 → 저장소 + 분석 | ✅ **분석 routine 완료** (2026-06-05) — `anxg_chat.feedback` 스키마는 `01_schema.sql:132-140` 에 이미 존재 (BACKLOG stale 정정), UI `record_feedback`(ui/storage.py) 도 작동. 본 PR 보강: 마이그 30 (`updated_at` 컬럼 신규 — ON CONFLICT 시 created_at 보존), UI ON CONFLICT 정정, 신규 `feedback_stats.py` (전 기간/최근 N일 분포 + 부정 message 상위), Makefile `feedback-stats`, 회귀 가드 14건. **잔여**: 저주파 retraining loop (분기 단위) 는 비전 단계 — 별도 항목. | (도구 완료) | feedback 누적 후 retraining 정책 수립 | README §12.6 |
| E-5 | **Vector RAG 공정성 검증** — gold QA "Vector 도 풀 수 있는 질문" 비율 | 매트릭스 내 Vector adapter 단독 측정 | P2 | 작성자 편향 완화 — 사람 검증 또는 외부 큐레이터 | README §12.6 |
| E-6 | **performance benchmark** — p50/p95/p99 latency + 평균 토큰·cost/turn | PRD 목표만, 실측 미수행 | P3 | E-1 풀 실측 후 dashboard 구축 | README §12.7 |
| E-7 | **`turn_budget_for_domain` 도메인별 declared field 기본값 ($) 실측 검증** | ✅ **검증 완료** (2026-06-05) — finance/auto/cross_domain declared `0.0` (fallback 상속), ip None (fallback 상속) → 4 도메인 모두 fallback `$0.20` 동일. `docs/architecture.md` §5.1(f) "ip 는 1/10 수준" stale 표현 정정. 도메인별 차등화는 ENV 또는 settings field 양수 지정 시 활성. | (완료) | — | README §0 / docs/architecture.md §5.1 (f) |
| E-8 | **회귀 가드 SSOT 카탈로그** — 본 세션(2026-06-05) 신규 가드 일괄 anchor | ✅ **카탈로그 정리** (이 항목 자체) — 신규 가드 ~57건 (`tests/test_namespace_isolation.py` 19 (PG/Neo4j namespace + 싱글톤 conn/pool health + transaction cache + bare label 검사 + PG schema 검사) · `tests/test_broad_except_hygiene.py` 3 (naked except + noqa 사유 강제 + 사유 ≥ 5자, 검사 범위 `src/+scripts/+tests/`) · `tests/test_evo_alignment.py` 10 (L6-5 EVO 매핑) · `tests/test_materials_metals_seed.py` 8 + `tests/test_load_materials_metals.py` 10 (L6-2 metals) · `tests/test_feedback_stats.py` 14 (E-4 분석)). silent swallow 신규 유입 · bare 라벨/스키마 · 싱글톤 close 호출 · namespace 마이그 drift 등을 자동으로 차단. **잔여**: 향후 추가될 다른 lru_cache 함수 (O-7) 의 health check 가드도 같은 파일에 통합. | (카탈로그) | 신규 가드 추가 시 본 항목 갱신 + count 보강 | tests/test_namespace_isolation.py · test_broad_except_hygiene.py · test_evo_alignment.py · test_materials_metals_seed.py · test_load_materials_metals.py · test_feedback_stats.py |

---

## 8. 문서·DX

| ID | 항목 | 상태 | 우선순위 | 활성화 트리거 | 위치 |
|---|---|---|:---:|---|---|
| F-1 | **CONTRIBUTING.md / SECURITY.md** | ✅ **작성** — 루트 `CONTRIBUTING.md`(개발환경·smoke-e2e 게이트·도메인 불변식 8항·PR 절차) + `SECURITY.md`(비공개 보고 채널·구현 통제·알려진 한계 정직표기) | (완료) | — | README §12.7 |
| F-2 | **TROUBLESHOOTING.md** | ✅ **구현** — `docs/faq.md`(Q1~Q7) 가 단일 SSOT, 루트 `TROUBLESHOOTING.md` 는 발견성 포인터(중복 회피). 4 named 실패 보강: LLM rate limit(Q2.4) / pgvector·Neo4j auth(Q1.1) / DART·data.go.kr 키 만료(Q3.5) | (완료) | — | README §12.7 |
| F-3 | **`docs/design/` ADR** | ✅ **작성** — `docs/design/` 신설 + ADR 4건(0001 LangGraph StateGraph / 0002 DomainHandler plug-in / 0003 Bridge 분리 테이블 / 0004 P1~P4 추출) + index. 각 코드 라인·mental_model 위임 | (완료) | diagram(이미지)은 후속 | README §12.7 |
| F-4 | **GitHub Issue/PR template** | ✅ **작성** — `.github/ISSUE_TEMPLATE/{bug_report,feature_request,data_source}.md` + `config.yml` + `pull_request_template.md` (프로젝트 불변식 체크리스트 내장) | (완료) | — | README §12.7 |
| F-5 | **`make load-kamp-process-metrics` Makefile 타겟 미정의** — 모듈 `src/autograph/loaders/load_kamp_process_metrics.py` 는 존재, Makefile 타겟 부재 (BACKLOG D-4 트리거 인용 stale) | ✅ **완료** (2026-06-05) — Makefile 5줄 타겟 추가 + PHONY 등록. dry-run 검증 (raw 미존재 → graceful skip). | (완료) | — | Makefile + BACKLOG D-4 |
| F-6 | **Mermaid 다이어그램 GitHub 실제 렌더 + Figma 동기화** — 본 세션 신설 2 다이어그램 (README §0 도메인 위계 4축 / autograph §2.5.4 BoM ⟂ BoP 직교) 의 렌더 미실측 | 미검증 (본 세션 발견) | P2 | GitHub PR/main 페이지 접속 후 렌더 캡처 + 옵션 Mermaid live editor 검증 | README §0 / docs/autograph.md §2.5.4 |
| F-7 | **mental_model / learning_guide 본문 잔여 `PRD §X.Y` 인용** — 두 문서 본문 정책 "점진적 갱신 중" (mental_model.md:45, learning_guide.md:51) 으로 갈음 중 | 잔재 30건 (2026-06-05, 어색한 `(구 PRD §7.5).N` 6건 → agents.md anchor 로 정정 완료) | P2 | grep `PRD §` 으로 잔재 모니터링 + 발견 시 다음 PR 에 같이 정리 | docs/mental_model.md / docs/learning_guide.md |
| F-8 | **broad-except 자동 분류 휴리스틱 한계 사례** — R9/R10 자동 사유 부여 정확도 | ✅ **사례 기록** (2026-06-05) — R8~R10 누적 ~470건 사유 명시. v2 휴리스틱(다음 5줄 context)이 1건 silent 오분류 (`extract_defect_types_llm.py:187` 실제는 boundary → rollback + raise) — R10 수동 검토 단계에서 catch. 가드 (`test_broad_except_hygiene`) 도 `dedupe_suppliers_by_name_norm` 신규 위반 1건 catch (의도된 silent swallow 차단 실증). 향후 새 코드 작성 시 reviewer 가 사유 정확성 직접 확인 권장 (자동 휴리스틱은 80~90% 정확). | (사례 anchor) | 사유 verbatim 으로는 prefix `[file_stem]` 또는 `[module.name]` 강제 — 자동 추가 가능 | tests/test_broad_except_hygiene.py · 본 세션 commit history |

---

## 9. ProcessGraph 회사 귀속 + KAMP + 품질

| ID | 항목 | 상태 | 우선순위 | 활성화 트리거 | 위치 |
|---|---|---|:---:|---|---|
| PG-1 | **DoD #19 회사 귀속 인스턴스 `PERFORMED_AT` ≥ 30** | ✅ **충족 94/30** — manual_seed 35 validated + factoryon 59 candidate(A공장/추론공정). :Plant 29→103, OWNS_PLANT 53→60. **ProcessGraph "주요 축" 핵심 게이트 통과** | (완료) | — | README §10.19, docs/process_graph.md |
| PG-2 | **DoD #20 cross 정확도 ≥ 50% — 공정↔재무 / 결함전파** | ⚠️ 부분 — G-1(PERFORMED_AT 94)+G-4(CAUSED_BY_PROCESS 96) 적재로 **결함전파·공정↔재무 경로 구조 완성**. 2026-06-05 measure: matrix (finance) hybrid hits 0.43 / eval-auto hits 0.232 / **eval-cross hits 0.449 (49 row, $0.13)**. 모든 run EM=0 + faith=0 — grounding overlap 0.01~0.07 다수 (cross-domain chunk 적재 sparse). 50% 정확도 목표 미달 | P1 | (a) cross-domain chunk 적재 보강 (gold CD-L1~L4 질문 대응 evidence chunk 수동 채움) (b) `make eval-cross` 재측정. DoD audit 가 eval-auto/cross 결과를 자동 수집하도록 prd_dashboard.py 보강 (현재 ⊘ → 측정 후 ✅/❌ 전환 미작동) | README §10.20, `eval/reports/cross_20260605_070808/` |
| PG-3 | **row 단위 동적 confidence 격상 실측** | ✅ **`compute()` 본문 구현 완료 + tested** — `src/autograph/extractors/process_confidence.py` `compute()` 가 PRD §3.5.1 수식(`clip(0.50 + Σ w·s − 0.20·|conflicts|, 0.30, 1.00)`) + grade 판정 구현, `tests/test_process_confidence.py` 8 케이스 PASS. **남은 것**: 운영 wire-up — `scripts/upgrade_processes_confidence.py` 에서 import + 1회 풀런 ≤ $2 + GPU 1분 (idempotent) + `cross_validate.py::_VALIDATORS["CAUSED_BY_PROCESS"]` 연결. 격상률 15~30% 예상 | P2 | 위 wire-up + 풀런 | README §4.0.1 |
| PG-4 | **KAMP 카탈로그 + 산단공 정규화 사전 적재** | ✅ **`auto.kamp_catalog` 50 row** (data.go.kr 15089213 무인증 다운, 13 industry × 11 process_category, 37 unique 공정 → 33 정규화 매핑 inline `_PROCESS_NORM`) + 신규 OEM/공정 출처 3건 (KAMP catalog + NASA PCoE + EU Safety Gate) — 가이드 우선순위 (KAMP→MaintNet→DEFECT_MATCHES→...) 5/7 완료 | (완료) | KAMP 본체 데이터셋은 **냉철 평가 후 보류 결정** — 출처 익명+단일 라인이라 NHTSA+KOTSA 자체 :DefectType 50 + NASA PCoE :FailureMode 18 보다 한계 효용 낮음 | docs/data_lineage.md §2.14 |

---

## 10. IPGraph 데이터 적재 + bridge join

| ID | 항목 | 상태 | 우선순위 | 활성화 트리거 | 위치 |
|---|---|---|:---:|---|---|
| IP-1 | **`ip.patents` (KIPRIS + USPTO ODP + Google Patents BigQuery)** | 0 row, schema 적용 완료. USPTO ODP는 2026-06-18 이후 X-API-KEY mandatory + bulk SPA 우회 부담 → **GCP BigQuery `patents-public-data.patents.publications` 우선 검토 (P0+, GCP Service Account JSON 발급 필요)** | P1 | **GCP Service Account JSON** ([docs/operations/api_keys_pending.md §1](./docs/operations/api_keys_pending.md)) or KIPRIS_API_KEY or USPTO ODP key — Python google-cloud-bigquery 3.41.0 설치 완료 | README §1.5 |
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
| L6-2 | **알루미늄 합금 / 다이캐스팅 등 공법 ontology** | ✅ **완료** (2026-06-05) — seed `ontology/auto/materials_metals_seed.yaml` 9 alloys (Al 4 / 강 4 / Ti 1) + 13 module mappings (26 flat rows). loader `src/autograph/loaders/load_materials_metals.py` (Anxg_Material UNWIND + MADE_OF 7-key meta, conf 0.50 candidate). Makefile `load-materials-metals[-dry]` 타겟. `MaterialsMetalsFile` strict 검증 + 회귀 가드 18건 (`test_materials_metals_seed.py` 8 + `test_load_materials_metals.py` 10). audit-ontology `auto.materials_metals(9)` PASS. dry-run: 9 materials / 26 made_of rows. **잔여**: 실 적재 (Module 노드 적재 후 매칭률 실측) | (완료) | 실 환경에서 `make load-materials-metals` 1회 + Module 매칭률 확인 | README §12.5 |
| L6-3 | **회사단위 셀↔OEM 소싱 (SUPPLIES)** | grade C candidate (sparse) | P2 | 공개 IR PDF 또는 manual seed. 자동 만료 (6개월 미검토 → rejected) | docs/autograph.md §2.5.4 |
| L6-4 | **무역통계 — 관세청 / K-stat (Li/Ni/Co 한국 수입)** | 0 | P2 | `macro.trade_minerals` 신규 스키마 + ingestion | docs/autograph.md §2.5.4 |
| L6-5 | **EVO 온톨로지 정렬** (arXiv 2304.04893 — 20 클래스·17 객체속성·54 데이터타입) | ✅ **스켈레톤 적재** (2026-06-05) — `ontology/auto/evo_alignment.yaml` 신규 (17 entities + 12 relations 매핑 시드, upstream 메타 20/17/54). 자명한 1:1 매핑은 placeholder 상태로 두고 (false IRI 가 SPARQL 호환성 깨지 않도록), 실제 IRI 채움은 후속 EVO 논문 re-read + ontology review board. 회귀 가드 10건(`tests/test_evo_alignment.py`): 우리 라벨이 entities.yaml/relations.yaml 실재 / iri 가 placeholder 문자열 아닐 것 / applicable=false 일관성. docs/autograph.md §2.5.4 cross-link. | (스켈레톤 완료) | EVO 논문 re-read 후 IRI 점진 채움 → SHACL shape 그래프 등장 시 sh:targetClass 로 reuse | docs/autograph.md §2.5.4 |

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
| Y-1 | **보조 yaml SHACL/pydantic 확장** — extractors.yaml / system_taxonomy.yaml / plants.yaml | ✅ **구현** — `ontology_validate.py` 에 pydantic strict 모델 4개(ExtractorsFile/SystemTaxonomyFile/PlantsFile, extra='forbid') + `AUX_TARGETS` 추가. `make audit-ontology` aux 4 PASS (auto.extractors 15 · finance.extractors 9 · system_taxonomy 19 · plants 30). 테스트 5건(드리프트 reject) | (완료) | seed yaml(materials/part/supplier/standards) 추가 검증은 후속 | README §10.17 (c) |
| Y-2 | **Cypher cross-check WARN 강등 (cross-domain reference)** — 예: ip cypher 가 auto.SUPPLIED_BY 참조 | ✅ **구현** — 기본 WARN(가시화 ⚠️ 출력) + `--strict-cross`(`make audit-ontology ARGS="--strict-cross"`) 로 ERROR 강등 선택. 현 cross-domain ref: ip→`SUPPLIED_BY` 1건. 테스트 1건 | (완료) | strict 를 CI 게이트로 승격할지는 운영 결정 | scripts/audit/ontology_validate.py |

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

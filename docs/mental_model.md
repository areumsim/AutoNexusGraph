# AutoNexusGraph — 멘탈 모델 / 아키텍처 / 열린 질문

> 이 문서는 README/PRD/operations 가이드와 **별도의 역할**을 가진다. "이 시스템이 무엇이고 어떻게 동작하는가"는 그 문서들이 이미 잘 다룬다. 여기서는 **"왜 이렇게 만들었고, 무엇이 확정·잠정·미정이며, 어디에 위험이 있는가"** 를 라벨과 근거로 정리한다.
>
> 시스템은 초기 구현 단계(2026-05 기준 Phase B 마무리)이며, 많은 결정이 잠정적이다. 이 문서는 그 잠정성을 숨기지 않고 드러내어, 새 합류자가 스스로 더 깊이 고민할 수 있는 출발점이 되는 것을 목표로 한다.

---

## 0. 시작하기 — 이 문서의 사용법

### 0.1 이 문서가 다루는 것 / 다루지 않는 것

| 다룬다 | 다루지 않는다 |
|---|---|
| 시스템이 풀려는 **문제와 그 한계** | 데이터 적재량·최신 수치 → `data/README.md`, `docs/data_inventory.md` |
| **핵심 추상화**(개념 사전) | Quickstart / 명령어 → `README §11`, `docs/operations/*.md` |
| 두 패키지의 책임 분리와 한 turn 흐름 (요약) | **구조 SSOT (패키지 토폴로지·LangGraph 노드·SSOT 색인) → `docs/architecture.md`** |
| **설계 의도와 그 트레이드오프 / 대안** | 데이터 소스 라이선스 전수 표 → `README §4`, `docs/data_sources.md` |
| **확정 / 잠정 / 미정** 의 명시적 구분 | autograph 도메인 단독 가이드 → `docs/autograph.md` / ipgraph (도메인3) → `docs/ipgraph.md` |
| 열린 질문·숨은 가정·위험 | 완전한 요구사항·DoD 트래픽라이트 → [README §10 DoD 20항](../README.md#10-dod-definition-of-done--20-항) |
| (결정 카탈로그 — *무엇이* 어디에 왜) | 평가 결과 / 비교 매트릭스 실측값 → `eval/reports/*` / 이론 교재 → `docs/learning_guide.md` |

### 0.2 라벨 컨벤션 (가장 중요)

이 문서의 모든 결정·서술에는 다음 라벨 중 하나가 동행한다:

- **[확정]** — 의도적으로 결정됐고, 코드·PRD·커밋 메시지에 근거 있음. 바꾸려면 명시적 트레이드오프 논의 필요.
- **[잠정]** — 일단 이렇게 해뒀지만 바뀔 수 있음. 왜 임시인지 한 줄 동행.
- **[미정]** — 아직 안 정함. 무엇이 정해져야 결정 가능한지 한 줄 동행.
- **[의도 확인 필요]** — 코드/문서로 "왜"가 안 드러남. 본 문서는 추측하지 않는다.

추가 마커:
- **[가정]** — 명시적으로 적힌 적 없지만 시스템이 작동하기 위해 참이어야 하는 명제 (검증 안 됨).
- **[위험]** — 현재 설계가 깨질 수 있는 시나리오.

### 0.3 읽는 순서

- **처음 보는 사람**: 0 → 1 → 2 → 3 까지 통독. §3 까지면 시스템의 골격을 머릿속에 잡을 수 있다.
- **더 깊이 보고 싶은 사람**: §4 (트레이드오프) → §5 (열린 질문) → §6 (다음 한 걸음).
- **다시 보러 온 시니어**: §5 만 골라 봐도 된다. "내가 어디서 결정을 미뤘는지" 빠르게 회상하는 노트.

### 0.4 인용 규약

- `path/file.py:LINE` — 코드 위치. Read 도구로 즉시 확인 가능.
- `README §N` — README.md (통합 SSOT v3.0) 의 절 번호. (구 `PRD §X.Y` 인용은 README §10 DoD 20항 + §3.X 아키텍처 sub-section 흡수 후 폐기 — 2026-06-02)
- 본 문서의 "확정/잠정/미정 라벨"은 작성 시점(2026-05-29) 기준이며, 코드 변경 시 함께 갱신되어야 한다.

---

## 1. 문제 정의 — 무엇을 왜 푸는가

### 1.1 출발 인식: 단일 도메인 Vector RAG 의 한계

finance 단독으로 검증된 AutoNexusGraph 의 한계 (구 PRD.md §1.1 → README v3.0 흡수):

| 한계 | 의미 |
|---|---|
| 도메인 단일성 | 금융 한 영역. 시스템 일반성 미입증. |
| 관계 평면성 | 자회사/임원/주주가 모두 동일 평면 — "메인 홉"과 "사이드 홉" 구분 없음. |
| 이벤트 빈도 낮음 | 공시·뉴스는 분기/월 단위 — 실시간성 검증 어려움. |
| 물리적 계층 부재 | 모든 엔티티가 법인 — 제품·소재·공정 같은 물리적 계층 없음. |

[확정] 이 4가지 한계를 풀기 위해 자동차 도메인을 추가한다 — 자동차의 **명시적 BOM 계층**(Manufacturer→Model→Variant→System→Module→Part)은 "메인 홉"을 자연스럽게 도입하며, NHTSA 리콜·결함은 일·주 단위 이벤트를 제공한다 (README §0 축 위계 + §1 현황).

### 1.2 시스템의 가치 제안 — 한 줄

`README:3` 의 정의를 그대로 인용:

> 자동차 제품·부품·리콜·공급망 (auto) + 한국 상장사 공시·재무 (finance) 두 도메인을 그래프·정형·벡터 하이브리드로 추론하고, `bridge.corp_entity` 로 Cross-Domain 까지 한 turn 안에 묶는 멀티도메인 GraphRAG 에이전트.

[확정] 사용자 시나리오 예시 (README §1 + §11.3 추론 가치):

1. 도메인 내 멀티홉: "현대 쏘나타의 에어백 리콜과 관련된 공급사는?"
2. Cross-Domain: "현대모비스 매출과 모비스가 공급하는 차종의 최근 리콜은?"
3. Cross-Domain (시점 포함): "2023년 LG에너지솔루션 배터리를 쓰는 OEM 의 KCGS ESG 등급은?"

Vector 단독 RAG 로는 #1 도 일부만, #2/#3 은 사실상 불가능. 그래서 그래프(관계) + 정형(수치) + 벡터(서술) 의 하이브리드가 정당화된다.

### 1.3 비목표 (Non-Goals)

[확정] 다음은 명시적으로 안 한다 (README §9):

- 실시간 주가 예측 / 매매 신호 생성 / 투자 자문
- 비상장사 데이터 (DART 미제공)
- 영문 글로벌 기업 (1차 범위 외; SEC 한국 ADR 은 제한적 보강만)
- 차량 가격 예측 / 중고차 시세
- **공정·라인·설비·원가·생산량** — v3.0 에서 부분 진입 (auto 수직 심화 = ProcessGraph BoP, README §0 축 위계 + §10.18~20 DoD). 회사 귀속 인스턴스는 데이터 대기 (BACKLOG PG-1).
- 비공개 OEM 내부 BOM / 자율주행 안전성 인증 대체 / 실시간 텔레매틱스
- **BOM Level 6 (소재·공법)** MVP 포함 — v3.0 부분 적재 (곁가지: Material 6 / Mineral 5 / DERIVED_FROM 17 / MADE_OF 8, README §11.2 가용성 매트릭스).

### 1.4 시스템 이름의 의미 — FinGraph → AutoNexusGraph

[잠정] 2026 년 초 리네이밍 (커밋 `10680a4`). 의미:

- finance 단일 도메인 시스템이 아니라 **여러 도메인을 묶는 우산** 으로 포지셔닝.
- 현재는 finance + auto 두 도메인 + ip 보조축. **[확정 — 2026-06-02 README v3.0]** ip = 수평 cross 진입 어댑터 (corp_entity 브리지 전용) — `docs/ipgraph.md` SSOT + README §11.1 Phase C + DoD §10.15~17. 4번째~ (의약품/전자제품/에너지/식품) 는 README §9 비목표 강등.

**[의도 확인 필요]**: "AutoNexusGraph" 가 영구적 우산 이름인지, 다음 리브랜딩 가능성이 있는지 — 코드/PRD 만으론 확인 불가. 단, `src/autonexusgraph/__init__.py:1` 가 "finance 코어" 로 자기 정의하고 있어 패키지 이름과 도메인 명칭이 완전히 정합되진 않음 (§3.1 의 [의도 확인 필요] 항목 참조).

---

## 2. 핵심 개념·추상화 — 이걸 모르면 코드가 안 읽힌다

이 절은 **개념 사전**이다. 코드를 읽기 전에 한 번 통독하면, `master.entities` 가 등장했을 때 무슨 의미인지 모르고 헤매지 않게 된다.

### 2.1 Domain 개념 (그래프·데이터 모델 측)

#### 2.1.1 Entity Resolution 마스터 (`master.entities` + `master.entity_map`)

- **정의**: 모든 엔티티(법인·차량·부품·인물 등)에 단일 ID 공간을 부여하는 SSOT.
- **왜 필요**: 같은 회사가 DART 의 `corp_code`, Wikidata 의 `QID`, GLEIF 의 `LEI`, NHTSA 의 `manufacturer_id` 등 여러 식별자를 가짐. 도메인 간 join 을 위해 통합 키 필요.
- **위치**: v2.1 에서 `corp_code` 단일 중심키 → `entity_id + entity_type` 다형 키로 일반화 (README §3.4 ER 마스터 + §3.4.1 마이그레이션 1:1 매핑). 스키마 파일은 `infra/postgres/init/*.sql`.
- **확장 인덱스 테이블**: `master.entity_map` 에 ticker / QID / LEI / CIK / ISIN / 사업자번호 / 법인등록번호 / NHTSA mfr_id / wikipedia_title 등을 매핑 (`README §1.1`).
- [확정] v2.1 에서 entity_id 다형 키 도입.
- [잠정] 현재 finance 엔티티(Company) 와 auto 엔티티(Manufacturer/Supplier) 의 entity_type 분리 — 인물(Person) 통합 여부는 미정 (auto 측 인물 엔티티가 없음).
- **열린 질문**: ER 마스터의 변경 이력(corp_code 재부여, jurir_no 변경) 추적 정책. 현재 `snapshot_year` 로만 시점 분리.

#### 2.1.2 Bridge (`bridge.corp_entity`)

- **정의**: 두 도메인의 ID 를 묶는 다리. `corp_code (finance) ↔ entity_id (auto)` 매칭 테이블.
- **매칭 우선순위**: Wikidata QID > LEI > 사업자번호 > 이름 (README §3.5 Bridge 일반화 명세, `docs/autograph.md §3`, `src/autograph/loaders/load_bridge.py`). 별도로 `sec_cik` 컬럼이 글로벌 OEM 진입점 — `bridge_sec_cik_to_entity` (`src/autograph/tools/bridge.py:64`).
- **신뢰도 라벨링**: 자동 매칭은 `candidate`. 사람이 검토하면 `reviewed` / `rejected`. 신뢰도 0.95 (QID 일치 시) 부터 시작. `match_method` 6종 enum: `qid_exact | lei_exact | business_no_exact | corp_code_exact | fuzzy_name | manual` (README §3.5 SQL schema).
- **현황** (`README §1.1`): **4,806 행** — manufacturer cand 1 + rev 11 + supplier cand 4,790 + rev 4. `strong_match` (confidence ≥ 0.9) = 15/15 = 100%.
- [확정] Bridge 분리 테이블 도입 — 도메인 직접 FK 가 아닌 별도 테이블에 confidence·reviewed_status·source_type 보유.
- [잠정] 자동 매칭 결과의 **검토 프로세스** — `reviewed_status='rejected'` 운영 절차가 코드로 강제되지 않음. **[의도 확인 필요]**.
- **열린 질문**: name 단독 매칭은 false-positive 위험. 영구 candidate 누적이 graph 폭발로 번지는 시나리오 (`§5.3` 참조).

#### 2.1.3 BOM 계층 (Level 0 ~ 6)

- **정의**: 자동차 도메인의 메인 홉 척추. `Manufacturer (L0) → VehicleModel (L1) → VehicleVariant (L2) → System (L3) → Module (L4) → Part (L5) → Material/Process (L6)` (`README §11.2`, `docs/autograph.md §2.5.4`).
- **MVP 가용성** (`README §11.2`):
  - L0~L2: **높음** [확정]. NHTSA vPIC + Wikidata 로 채움.
  - L3: **중간** [확정]. `ontology/auto/system_taxonomy.yaml` 19 시스템 코드 (POWERTRAIN, BRAKE, ADAS, …).
  - L4: **낮음~중간** [잠정 — 부분 포함]. AI Hub + 공급사 시드 + LLM P3.
  - L5: **낮음** [잠정 — MVP 제외, 리콜에 등장한 부품만 부분 포함]. ontology 와 MERGE 경로는 준비됨 (`docs/autograph.md §7.6`).
  - L6: **낮음** [미정 — 본 PRD 의 명시적 non-goal].
- **왜 메인 홉**: 평면 그래프(자회사/임원/주주) 와 달리 BOM 은 **자연스럽게 깊이를 갖는 트리**. Planner 가 깊이 우선 탐색하면 토큰·latency 절감 (`PRD §2.1` "(3) 명시적 계층(메인 홉)으로 그래프 폭발을 통제").
- **열린 질문**: L5/L6 미완은 데이터 본질 문제인가, 수집 채널 부족인가? (`§5.4` 참조).

#### 2.1.4 `edge_required_meta` — 모든 엣지가 가져야 할 메타

- **정의**: auto 도메인의 모든 그래프 엣지에 강제되는 6개 메타 (`README §3.7`, `ontology/auto/relations.yaml:19-26`):

  | 키 | 의미 | 예 |
  |---|---|---|
  | `source_type` | 출처 종류 | `nhtsa_vpic`, `wikidata_p176`, `manual_seed`, `llm_p3` |
  | `source_id` | 출처 식별자 | `rcept_no`, `chunk_id`, `'manual'` |
  | `confidence_score` | 0.0 ~ 1.0 | 0.95 (NHTSA) / 0.50 (LLM P3) |
  | `validated_status` | 검증 상태 | `verified` / `validated` / `candidate` / `needs_review` / `rejected` |
  | `snapshot_year` | 기준 연도 | 2024 |
  | `extraction_method` | 추출 방법 | `deterministic` / `llm` / `wikidata` / `manual` |
  | `schema_version` | 적재 시 PRD 버전 | `v2.0` / `v2.1` |

- **왜 강제**: confidence 와 시점 없는 엣지는 그래프 추론을 신뢰 불가능하게 만든다. P3 LLM 추출과 P2 결정적 적재가 같은 그래프에 섞이므로 출처 추적 필수.
- **검증**: `docs/autograph.md §7.5` 의 "메타 무결성" Cypher 가 `MATCH ()-[r]->() WHERE (r.confidence_score IS NULL OR r.source_type IS NULL OR r.snapshot_year IS NULL) ... RETURN count(*)` 로 0 인지 확인.
- [확정] 의무 메타 7개. v2.1 신규 (v2.0 은 source/snapshot_year 만).
- **열린 질문**: finance 도메인 엣지 (SUBSIDIARY_OF, EXECUTIVE_OF 등) 가 동일 수준으로 강제되는가? **[의도 확인 필요]** — finance ontology 는 `ontology/entities.yaml`, `relations.yaml` 에 있으며 auto 와 같은 강제 정도인지는 본 문서가 검증 안 했음.

#### 2.1.5 출처 신뢰도 등급 (A / B / C)

- **정의**: 모든 그래프 엣지의 `confidence_score` 기본값을 출처에 따라 결정 (`README §4.0`):

  | 출처 | 등급 | 기본 confidence | 적용 |
  |---|---|---|---|
  | NHTSA / 자동차리콜센터 공식 | A | 0.95 | `AFFECTED_BY`, `RECALL_OF` |
  | NHTSA vPIC | A | 0.95 | `MANUFACTURES`, `HAS_VARIANT` |
  | KNCAP / NCAP / Euro NCAP | A | 0.95 | `SAFETY_RATED_BY` |
  | Wikidata | B | 0.80 | 글로벌 ID 매핑, `MANUFACTURES` (보조) |
  | Wikipedia | B~C | 0.70 | 설명 문서, 보조 근거 |
  | 부품사 IR (공시) | B | 0.75 | `SUPPLIED_BY` (후보) |
  | 매뉴얼 / 브로셔 | B | 0.75 | `CONTAINS_*` |
  | LLM 추출 (P3) | C | 0.50 | P4 cross-validate 필수 |
  | 커뮤니티 / 분해자료 | C | 0.40 | 후보 추출만, 확정 금지 |
  | 수동 검토 확정 | A+ | 1.00 | 모든 관계 |

- **승급 정책**: `SUPPLIED_BY` 등 공급 관계는 **A 또는 B 출처 + P4 cross-validate 통과** 시에만 `validated=true`. C 등급 단독은 절대 `validated=true` 금지.
- [확정] 등급·기본값·승급 정책 명시.
- [가정] 0.40 ~ 0.95 의 숫자가 실제 정답률과 단조 관계 — 미검증 (`§5.2` 참조).

#### 2.1.6 3-Store 하이브리드 — 역할 분리

`README §3` 의 표를 그대로 인용:

| 저장소 | 책임 | 예시 질의 |
|---|---|---|
| **Neo4j** | 관계·구조 | "현대차 자회사 중 매출 1조 이상은?" |
| **PostgreSQL** | 정확한 수치 + 메타 (SSOT) | "삼성전자 2023년 매출은?" |
| **pgvector / Qdrant** | 의미·서술 | "삼성전자의 주요 사업 위험 요인은?" |

- [확정 / 핵심 원칙] **재무 수치는 절대 LLM 이 생성하지 않는다 — 반드시 PostgreSQL 조회 결과만 사용** (`README:110`). 이 원칙은 `agents/number_guard.py` 의 pre-synth 가드가 강제.
- [확정] PG 가 SSOT, Neo4j 는 관계의 그래프 미러 (BOM·자회사 관계 등). `vec.chunks` 는 PG 안에 (pgvector) — 100만 청크 이하면 Qdrant 분리 안 함.
- **열린 질문**: 청크가 100만 넘으면 Qdrant 분리 — 운영 분기 시점·절차 (`README §3` 의 "(옵션) Qdrant" 가 [잠정]).

### 2.2 Code / Architecture 개념

#### 2.2.1 AgentState (TypedDict) — 한 turn 의 모든 상태

- **정의**: 한 turn 의 누적 상태. LangGraph 의 StateGraph 가 그대로 받는 형태 (`src/autonexusgraph/agents/state.py:19-72`).
- **주요 필드** (전수 아님):
  - 입력: `thread_id`, `question`, `history`, `domain`, `target_vehicles/models/makes` (auto/cross_domain), `target_companies` (finance, corp_code 목록)
  - 전처리: `question_rewritten` (coreference 해소·시간 정규화 후), `temporal_audit`, `rewrite_audit`, `safety_signals`
  - 결정: `question_kind`, `plan` (legacy flat), `tasks` (DAG)
  - 결과: `task_results`, `tool_results`, `evidence_chunks`, `graph_subgraph`, `fallback_used`
  - 합성: `answer`, `citations`, `visualizations`
  - 검증: `validation_status`, `validation_issues`, `grounding`
  - HITL: `pending_interrupt`, `interrupt_response`, `interrupt_handled`
  - 비용·메타: `llm_usage_usd`, `n_replans`, `aborted_reason`
- [확정] TypedDict 로 정의 (state.py:19). `total=False` 라 모든 필드가 선택적 — 노드가 채워가는 모델.
- [잠정] 일부 필드는 legacy 호환 (`plan` ↔ `tasks`) — DAG 가 메인이고 `plan` 은 폴백 executor 가 사용 (`state.py:41-44`).

#### 2.2.2 DomainHandler 패턴 — 코어 ↔ 도메인 결합

- **정의**: 코어(autonexusgraph)가 외부 도메인 패키지(autograph)를 **직접 import 안 한다**. 도메인 측이 자기 핸들러를 import 시점에 등록 (`src/autonexusgraph/agents/_domain_handler.py:1-24`).
- **인터페이스** (`_domain_handler.py:36-73`):
  - `identify_targets(state, *, question)` — triage 위임
  - `plan_tasks(state, *, question)` — planner DAG 위임
  - `toolbox_modules()` — worker tool 모듈 list
  - `allowed_intents(kind)` — 화이트리스트
  - `fallback_search(state, *, query)` — executor 폴백
  - `retrieve_module()` — research worker 의 retrieve 모듈
- **등록 흐름** (`src/autograph/__init__.py:23` → `src/autograph/agent_handler.py:152-154`):
  ```python
  register_handler(AutoHandler())          # domain='auto'
  register_handler(CrossDomainHandler())   # domain='cross_domain'
  register_router(route_domain)            # 키워드 룰 라우터
  ```
- **의존 방향**: autograph → core (반대 아님). `import autograph` 가 발생하지 않으면 core 는 finance 만 동작 (라우터 등록 없으니 자동 라우팅이 finance 로 폴백 — `_domain_handler.py:117-130`).
- [확정] DomainHandler Protocol + register_handler 가 README §10.12 의 의도 ("core 변경량 < 5%") 인프라.
- **열린 질문 / [의도 확인 필요]**: agent_handler.py 가 protocol 의 메서드를 *모두* 구현하지 않아도 동작 (`_domain_handler.py:40-42`). 핸들러가 어떤 메서드를 누락해도 core 가 깨지지 않는다는 보장이 테스트로 검증되는지.

#### 2.2.3 사전 정의 도구 풀 — LLM 의 권한 경계

- **정의**: LLM 은 함수명 + 파라미터만 결정. SQL/Cypher 직접 생성 금지 (`docs/operations/agents.md (구 PRD §7.5).10`, `README:160`).
- **목록**:
  - `autonexusgraph.tools.financials` — PG 정형 (lookup_company, get_revenue, compare_companies, …)
  - `autonexusgraph.tools.graph` — Neo4j 탐색 (list_subsidiaries, get_executives, find_paths, …)
  - `autonexusgraph.tools.retrieve` — pgvector 하이브리드 검색
  - `autograph.tools.spec` / `graph` / `retrieve` / `bridge` — auto 도메인
- **방어 효과**: SQL injection, 그래프 폭발(`MATCH (a)-[*..*]->(b)`), 토큰 폭발 차단.
- **추가 가드** (다층):
  - `safety/prompt_safety.py` — injection 신호 감지, XML 경계 escape (`agents/nodes.py:40-44`)
  - `safety/cypher_guard.py` — READ-ONLY 강제, 템플릿 매개변수 매칭
  - `safety/language_guard.py` — 한국어 char ratio
  - `agents/number_guard.py` — synth 입력의 수치 화이트리스트 (PG 결과만 인용 가능)
- [확정 / 핵심 원칙] LLM 자유 호출 금지.

#### 2.2.4 Cypher 템플릿 레지스트리

- **정의**: 22개 Cypher 쿼리가 사전 등록 — type/range/regex 검증 + bool reject (`README §7.4.7` 의 Phase 4.7 라인, `src/autonexusgraph/tools/cypher_templates.py`).
- **확장**: auto 템플릿은 `src/autograph/cypher_templates_auto.py` 의 `AUTO_TEMPLATES` 에 등록되어 finance `TEMPLATES` 에 import 시 병합 (`src/autograph/tools/__init__.py`).
- **find_paths**: 1~5 hops 사전 등록. 가변 hops 가 토큰 폭발 위험이라 사전 등록.
- [확정] 자유 Cypher 0건. 모든 그래프 쿼리는 레지스트리 경유.

#### 2.2.5 P1 ~ P4 추출 파이프라인

- **정의**: 데이터 → 그래프 적재의 4단계 (`README §3.6 (4-Pass)/§6.6`, `docs/operations/data_pipeline.md`, `docs/autograph.md §7.4`):
  - **P1 — 정형 직매핑**: raw → PG (XBRL, NHTSA vPIC 표). LLM 0%.
  - **P2 — Deterministic relation**: PG FK / 룰 / 코드 매칭으로 그래프 엣지 (`SUBSIDIARY_OF`, `MANUFACTURES`, `RECALL_OF` 일부 등). 0% LLM.
  - **P3 — Selective LLM**: 서술형 텍스트(리콜 본문, IR, 매뉴얼)에서 관계 추출 (`SUPPLIED_BY`, `COMPETES_WITH` 후보 등). Schema-aware. `auto.staging_relations` 에 적재.
  - **P4 — Cross-validate**: P3 산출 vs P2 SSOT 비교. 일치하면 `validated`, 충돌하면 `rejected` (deterministic 우선), 결정 없음 + 0.80↑ 면 `candidate`, 0.65↑ 면 `needs_review`. Neo4j MERGE 시 `validated_status` 플래그.
- **위치**: `src/autonexusgraph/extractors/` (finance), `src/autograph/extractors/` (auto).
- [확정] Deterministic-first 원칙. 정형은 LLM 안 거침.
- [잠정] auto P3 의 활성 관계는 현재 2종 (`SUPPLIED_BY`, `RECALL_OF`). 4종은 `enabled:false` (`docs/autograph.md §7.6`, `ontology/auto/relations.yaml`).

#### 2.2.6 도메인 라우팅 — `route_domain`

- **정의**: 질문 → `finance` / `auto` / `cross_domain` 판정. 키워드 룰 (LLM 0건).
- **위치**: `src/autograph/policy.py:87-100`.
- **규칙**:
  - hint 명시 → 신뢰
  - `KW_AUTO_GENERIC + KW_RECALL + KW_SUPPLY + KW_SPEC` 중 하나 ↔ `KW_FIN` 동시 등장 → `cross_domain`
  - auto 키워드만 → `auto`
  - 그 외 → `finance` (기본)
- [확정] 키워드 룰. 사용자가 도메인을 명시할 수 있고 (UI 라디오 / API hint), 명시 없으면 룰.
- **열린 질문 / [위험]**: 키워드 누락 (예: "전기차 배터리" 가 auto 도 fin 도 안 잡힘 → finance 폴백). 키워드 사전(`policy.py:29-44`) 확장 정책 미정.

#### 2.2.7 5단계 에이전트 파이프라인

`README §3` 의 그림 + `docs/operations/agents.md` 참고. 한 turn 의 큰 흐름:

```
Triage → Planner(DAG) → Supervisor(Send 병렬) → Workers(4종) → Synthesizer → Validator
                                                                                ↓
                                                                          (replan ≤ 2)
```

- **Triage** (`agents/nodes.py:32`): 안전 가드 + coreference 해소 + 시간 정규화 + question_kind 분류 + 1차 회사/차량 식별. LLM 0건 (룰).
- **Planner** (`agents/nodes.py` 의 planner_node): DAG `tasks` 생성. 룰 기반 (docs/operations/agents.md (구 PRD §7.5).3) — 향후 LLM 업그레이드 가능 (`agents/nodes.py:12`).
- **Supervisor** (`agents/supervisor.py`): 의존성·순환 검증, budget guard, LangGraph `Send` API 로 worker 병렬 디스패치.
- **Workers 4종** (`agents/workers.py`):
  - `research_worker` — pgvector 검색
  - `graph_worker` — Cypher 템플릿 호출
  - `sql_worker` — PG 함수 호출
  - `calculator_worker` — numexpr 안전 evaluator (`workers.py:11-13`)
- **Synthesizer** — 답변 합성. `number_guard` 통과한 수치만 인용.
- **Validator** (`agents/validator.py`) — 출처·환각 검증. 실패 시 replan (최대 2회 — `state.py:71`).

[확정] 5단계 + 4 worker + Send 병렬 + replan ≤ 2. docs/operations/agents.md (구 PRD §7.5) 가 SSOT.

---

## 3. 현재 구조 — 지금 어떻게 구성돼 있는가 (Architecture)

이 절은 **architecture 본문**이다. 컨테이너·데이터·코드·라우팅·외부 의존을 한 번에 본다. 다이어그램은 `docs/autograph.md §2.5` 의 mermaid 가 충분히 상세하므로 여기선 텍스트 위주 + 위치 근거.

### 3.1 패키지 구조와 책임

```
AutoNexusGraph/
├─ src/
│  ├─ autonexusgraph/      # ★ 코어 + finance 어댑터 한 묶음 [잠정 — §3.1.4 참조]
│  │   ├─ agents/          # LangGraph nodes (도메인 무관 + finance 기본)
│  │   ├─ tools/           # finance 사전정의 도구
│  │   ├─ ingestion/       # DART/KRX/ECOS/SEC/GLEIF/Wiki/News
│  │   ├─ loaders/         # raw → PG/Neo4j 멱등 적재
│  │   ├─ extractors/      # P3 LLM (finance)
│  │   ├─ db/              # Neo4j/PG/Qdrant 클라이언트
│  │   ├─ llm/             # Anthropic/OpenAI/Local 어댑터
│  │   ├─ safety/          # prompt/cypher/language 가드
│  │   └─ api/             # FastAPI /chat
│  └─ autograph/           # ★ auto 도메인 어댑터 (코어 무수정)
│      ├─ ingestion/       # NHTSA vPIC/Recalls/Complaints + Wikidata + data.go.kr + KATRI + KNCAP
│      ├─ loaders/         # auto.* PG → Neo4j → bridge → seed/supplier/recall→comp → 청크
│      ├─ extractors/      # P3 auto + cross_validate
│      ├─ tools/           # spec/graph/retrieve/bridge
│      ├─ ontology.py      # ontology/auto/*.yaml 로더
│      ├─ cypher_templates_auto.py
│      ├─ agent_handler.py # AutoHandler/CrossDomainHandler 등록
│      └─ policy.py        # route_domain + plan_auto_tasks
├─ ontology/               # 그래프 스키마 SSOT
│  ├─ entities.yaml / relations.yaml / extractors.yaml   # finance
│  └─ auto/{entities,relations,extractors,system_taxonomy,standards,plants,supplier_seed,manufactured_at_seed}.yaml
├─ infra/postgres/init/    # 스키마 (00~12 sql, 멱등)
├─ scripts/                # 자동화 (Makefile 진입)
├─ eval/                   # 평가 인프라 (adapters/metrics/runners/qa_gold/reports)
├─ docker-compose.yml      # Neo4j + PG (pgvector) 공통 스택
└─ data/                   # raw / processed / state / reports
```

#### 3.1.1 코어 (autonexusgraph) 의 책임

- LangGraph 노드 정의 (`agents/`) — 도메인 무관 구조 + finance 기본값.
- 사전 정의 도구 풀 (`tools/`) — finance 함수들.
- 안전 가드 (`safety/`) — 도메인 무관.
- LLM 어댑터 (`llm/`) — provider 추상화.
- DB 클라이언트 (`db/`) — Neo4j/PG/Qdrant 풀.
- ingestion / loaders / extractors — finance 데이터 파이프라인.
- FastAPI / Streamlit 진입 — UI.

#### 3.1.2 도메인 어댑터 (autograph) 의 책임

- 도메인별 `DomainHandler` (`agent_handler.py:64-148`).
- 도메인별 도구 풀 (`tools/`).
- 도메인별 ingestion / loaders / extractors.
- 도메인별 Cypher 템플릿 (`cypher_templates_auto.py`).
- 도메인 라우터 (`policy.py:87`).
- import 시점 자동 등록 (`__init__.py:23`).

#### 3.1.3 자동 등록의 결과 (의존 그래프)

```
[finance only]         [auto + finance + cross_domain]
                                 ▲
autonexusgraph         autonexusgraph ──┐
   (handler 없음)         ↑              │  (import 시 register_handler)
                       autograph ────────┘
```

- `import autograph` 가 어딘가에서 발생하면 (`__init__.py:23`) 핸들러·라우터가 코어 레지스트리에 등록되어 auto/cross_domain 동작.
- autograph 가 import 안 되면 core 는 finance 만 동작 — handler 미등록이라 분기 자동 폴백 (`_domain_handler.py:117-130`).

#### 3.1.4 코어와 finance 의 분리 — **[잠정] (v2.2 결정 시점 도래)**

- 현재 구조에서 `autonexusgraph/tools/{financials,graph,retrieve}.py` 는 finance 데이터에 강하게 의존 (corp_code 등). agents/ 안의 fallback 도 `lookup_company` 를 직접 import (`agents/nodes.py:34`).
- 즉 **"코어 = 코어 인프라 + finance 어댑터"** 가 한 패키지에 묶여 있다.
- [잠정 / 가능성] 다음 단계에서 `autonexusgraph` = pure core, `fingraph` = finance 어댑터로 분리하는 그림. 현재 그 분리가 안 됨.
- **[확정 — 2026-06-01 PRD v2.2]** 도메인3 (IPGraph, README §11.1 (구 PRD §12.5)) 정식 흡수로 인해 **"코어/finance 분리" 결정 압력 실제 도래**. README §10.12 는 여전히 "코어 변경 < 5%" 만 측정하지만, **DoD #15 (ip 추가 후 baseline reset → 재측정 < 5%)** 가 새 게이트. 따라서:
  - 옵션 A — pure core 분리 (3분할: `autonexusgraph` + `fingraph` + `autograph` + `ipgraph`) 로 가야 "코어 변경" 의 의미가 명확해짐.
  - 옵션 B — 2분할 유지 + baseline reset 정책으로 누적 변화 추적 (현 v2.2 결정).
  - **v2.2 는 옵션 B 채택 (§11.1 baseline reset 정책 본문 승격).** 옵션 A 는 ipgraph 머지 후 누적 변경량이 너무 커지면 재고.

### 3.2 한 turn 의 흐름 (시퀀스 상세)

```
User Question
   │
   ▼
FastAPI /chat (or run_agent direct)            api/main.py
   │
   ▼
_init_state(question, thread_id, domain_hint)  agents/graph.py
   │
   ▼  ① route_domain (키워드 룰)
auto_detect_domain(q, hint) → 'finance' | 'auto' | 'cross_domain'
                                  policy.py:87 (autograph) / _domain_handler.py:117
   │
   ▼  ② Triage
triage_node                                    agents/nodes.py:32
   ├ sanitize_user_input  (prompt_safety)      safety/prompt_safety.py
   ├ rewrite_query        (coreference)        agents/rewriter.py
   ├ normalize_temporal_terms                  agents/temporal.py
   ├ classify_question[_auto]                  agents/policy.py / autograph/policy.py:51
   └ identify_targets                          handler.identify_targets (auto)
                                              or lookup_pg (finance)
   │
   ▼  ③ Planner
planner_node                                   agents/nodes.py
   └ handler.plan_tasks(state, q)              → tasks: list[dict] (DAG)
       finance: agents/policy.plan_tasks
       auto:    autograph/policy.plan_auto_tasks
       cross:   autograph/policy.plan_cross_domain_tasks
   │
   ▼  ④ Supervisor — Send 병렬 디스패치
supervisor_node                                agents/supervisor.py
   ├ DAG topological order, cycle check
   ├ budget guard (turn_budget_exceeded)
   └ langgraph Send → worker 병렬
   │
   ▼  ⑤ Workers (4종, 병렬)
research_worker  graph_worker  sql_worker  calculator_worker
   │              │              │              │
   ▼              ▼              ▼              ▼
toolbox = handler.toolbox_modules()  if registered else [fin tools]
allowed = handler.allowed_intents(kind)
   │              │              │              │
   ▼              ▼              ▼              ▼
search_documents  Cypher template  PG SQL func  numexpr (sandboxed)
   ↑              ↑                ↑
   pgvector       Neo4j            PostgreSQL
   │              │                │
   ▼              ▼                ▼
   evidence_chunks / tool_results / task_results 채움
   │
   ▼  ⑥ Synthesizer (LLM)
synthesizer_node                               agents/nodes.py
   ├ number_guard: 큰 수치는 PG 결과만 인용 가능 (화이트리스트)
   ├ cost_estimator 사전 추정 → HARD_LIMIT 초과 시 interrupt (user approval)
   ├ budget_aware_client (역할별 model 라우팅)
   └ answer + citations + visualizations 채움
   │
   ▼  ⑦ Validator
validator_node                                  agents/validator.py
   ├ verify_answer_grounding (citation ↔ chunk 매칭)
   ├ hallucination 신호 감지
   └ if fail and n_replans < 2: → planner_node (replan)
                              else: 그대로 answer 반환
   │
   ▼
Response (answer + citations + cost + visualizations)
```

[확정] 7단계. 모든 단계에 cost guard. Validator 실패 시 replan ≤ 2.

[잠정] Planner 가 현재 룰 기반 (`agents/nodes.py:13`). LLM 업그레이드 가능성 명시.

### 3.3 Worker 화이트리스트 / Toolbox 라우팅

워커가 호출 가능한 intent 는 도메인별로 사전 정의. **워커가 화이트리스트 밖 함수를 호출하면 실행 거부.**

- finance 화이트리스트 — core 의 SSOT (`agents/workers.py:30-41`):
  - `FIN_GRAPH_ALLOWED` (11종): list_subsidiaries, list_parents, get_executives, get_companies_of_person, get_major_shareholders, find_paths, get_subgraph, list_mentioning_news, list_cooccurring, list_group_members, lookup_person
  - `FIN_SQL_ALLOWED` (7종): lookup_company, get_company_info, get_revenue, get_operating_income, get_balance_sheet_item, compare_companies, list_companies_by_market
  - `FIN_RESEARCH_INTENTS` (3종): search_documents, search_by_metadata, get_chunk

- auto 화이트리스트 — handler 가 보유 (`autograph/agent_handler.py:42-61`):
  - `AUTO_GRAPH_ALLOWED` (9종): lookup_vehicle_graph, lookup_supplier, list_components, list_systems_of_model, list_models_with_system, list_recalls_affecting, list_investigations_affecting, get_investigation_recall_chain, get_suppliers_of_component, get_vehicles_using_component, find_vehicle_component_paths
  - `AUTO_SQL_ALLOWED` (10종): lookup_vehicle, get_vehicle_info, get_spec, compare_vehicles, get_safety_rating, bridge_corp_to_entity, bridge_entity_to_corp, bridge_sec_cik_to_entity, bridge_entity_to_sec_cik, get_oem_financials_sec, cross_query
  - `AUTO_RESEARCH_INTENTS` (3종): search_documents_auto, search_by_metadata_auto, get_chunk_auto

- cross_domain — fin ∪ auto (CrossDomainHandler 가 `super().allowed_intents() | fin` 으로 합집합, `agent_handler.py:139-148`).

[확정] 화이트리스트 강제. workers.py 의 `_allowed_intents()` 가 검증.

**열린 질문 / [잠정]**: finance 와 auto 양쪽에 동명 함수 (`lookup_vehicle`, `lookup_company` 등은 안 겹침). 만일 `search_documents` 가 양쪽에 있게 되면 어느 게 우선? — CrossDomainHandler 가 `toolbox_modules` 에서 **auto 먼저, finance 나중** 으로 우선순위 명시 (`agent_handler.py:133-137`).

### 3.4 데이터 계층 — 저장소별 책임 매트릭스

#### 3.4.1 PostgreSQL (SSOT)

| 스키마 | 역할 |
|---|---|
| `master.*` | 회사/인물/제조사/공급사/차량 마스터 + entity_map |
| `fin.*` | DART filings, XBRL financials |
| `auto.*` | 자동차 마스터·이벤트 (`master_manufacturers`, `master_vehicle_models`, `master_vehicle_variants`, `events_recalls`, `events_complaints`, `events_inspections`, `spec_measurements`, `components`, `staging_relations`) |
| `bridge.*` | `corp_entity` (cross-domain join 키) |
| `wiki.*` | Wikipedia 본문 + Wikidata facts |
| `sec.*` | SEC EDGAR + GLEIF LEI |
| `news.*` | 연합뉴스 메타+요약 |
| `esg.*` | KCGS ratings |
| `macro.*` | ECOS 거시지표 (+ KOSIS 후속) |
| `vec.chunks` | 텍스트 청크 + embedding (pgvector) |
| `chat.*` | 멀티턴 히스토리, LangGraph checkpoint |

[확정] PG 가 모든 정형 데이터의 SSOT. Neo4j 는 미러.

[잠정] auto P3 결과는 `auto.staging_relations` 에 적재 → P4 결정 후 Neo4j 적재. PG 가 staging area 역할도 겸함.

#### 3.4.2 Neo4j (관계 미러)

- finance 노드: `Company`, `Person`, `Group`, `NewsEvent`, `Industry`, `Market`, …
- finance 관계: `SUBSIDIARY_OF`, `EXECUTIVE_OF`, `MAJOR_SHAREHOLDER_OF`, `MENTIONED_IN`, `CO_MENTIONED_WITH`, `BELONGS_TO_GROUP`, `IN_INDUSTRY`, …
- auto 노드: `Manufacturer`, `VehicleModel`, `VehicleVariant`, `System`, `Module`, `Part`, `Supplier`, `Recall`, `Complaint`, `Standard`, `Plant` (`ontology/auto/entities.yaml`).
- auto 관계 (`ontology/auto/relations.yaml`): `MANUFACTURES`, `HAS_VARIANT`, `CONTAINS_SYSTEM`, `CONTAINS_COMPONENT`, `CONTAINED_IN`, `SUPPLIED_BY`, `AFFECTED_BY`, `RECALL_OF`, `REPORTED_IN`, `COMPLIES_WITH`, `SAFETY_RATED_BY`, `MANUFACTURED_AT`, `OWNS_PLANT`, `COMPETES_WITH`.
- 모든 auto 엣지에 `edge_required_meta` 7키 강제 (§2.1.4).

[확정] Neo4j 적재는 PG → Neo4j 방향 (`loaders/load_*_neo4j.py`). 역방향 없음.

#### 3.4.3 pgvector (`vec.chunks`)

- 청크 메타: `chunk_id`, `source`, `corp_code` (finance), `manufacturer_id`/`model_id`/`variant_id` (auto), `fiscal_year`, `section`, `embedding (vector(1024))`.
- finance 청크 ~748K (`README §1.1`); auto 청크 16,242 (모두 embedded — `README §1.2`).
- BGE-M3 1024d cosine 으로 backfill (`make embed-chunks`).

[잠정] `vec.chunks.corp_code` NOT NULL → nullable 로 완화 (auto 청크 추가 시) — `docs/autograph.md §6`. 영구성 [의도 확인 필요].

### 3.5 멱등 데이터 파이프라인 (raw → processed → DB)

```
[수집 (ingestion)]                  [적재 (loader)]                [그래프]
─────────────────                   ────────────────                ────────
DART (corp_code 기준)         ──→   master.companies + fin.* ──→   :Company
KRX 마스터                    ──→   master.companies (보강) ──→   stock_code 속성
ECOS                          ──→   macro.series
Wikidata SPARQL               ──→   master.entity_map + wiki.* ──→   QID 속성
Wikipedia                     ──→   wiki.wikipedia_pages
                                    + vec.chunks (section=wikipedia_ko)
연합뉴스 RSS                  ──→   news.articles ──→   :NewsEvent + CO_MENTIONED_WITH
SEC EDGAR (ADR)               ──→   sec.filings
GLEIF                         ──→   sec.lei + master.entity_map
KCGS (수동 CSV)               ──→   esg.ratings + Company.esg_grade
DART chunks                   ──→   vec.chunks (section=dart_*)

NHTSA vPIC                    ──→   auto.master_* + (P2) :Manufacturer/:Model/:Variant
NHTSA Recalls                 ──→   auto.events_recalls + (P2) :Recall + AFFECTED_BY
NHTSA Complaints              ──→   auto.events_complaints + (P2) :Complaint + REPORTED_IN
NHTSA SafetyRatings           ──→   spec_measurements.safety.* + SAFETY_RATED_BY
Wikidata (auto)               ──→   master.entity_map + (B0.80) :Manufacturer/:Model
data.go.kr 3048950 (CSV)      ──→   auto.events_recalls (941 row) — [확정 — 구 15089863 API 폐기]
data.go.kr 15155857 (CSV)     ──→   auto.events_inspections — [잠정 — manual]
KATRI (bigdata-tic OAuth)     ──→   auto.cert_* — [잠정 — credentials 필요]
KNCAP / Euro NCAP / IIHS      ──→   spec_measurements + :Standard — [부분 — KNCAP만 인터페이스]
AI Hub (부품 결함, 자율주행)  ──→   :Module + CONTAINS_COMPONENT
supplier_seed.yaml (19사 46)  ──→   :SUPPLIED_BY (manual A-grade)
manufactured_at_seed (46)     ──→   :MANUFACTURED_AT

[P3 LLM] (chunks 중 manufacturer_id 보유, source ∈ recall/complaint/wikipedia_auto)
  → AutoRelationExtractor → auto.staging_relations
  → cross_validate (P4) → p4_decision: validated/candidate/needs_review/rejected
  → 결정에 따라 Neo4j MERGE
```

[확정] 모든 loader 는 `ON CONFLICT DO UPDATE` / `MERGE` — 멱등 (`README §2` "재실행 가능한 멱등 파이프라인").

[확정] raw 만 있으면 processed + DB 재생성 가능. raw 는 보존.

[잠정 — 외부 의존] data.go.kr 15155857 / KATRI / KNCAP — 인터페이스만 깔리고 키/raw 부재 시 graceful skip (`docs/autograph.md §5`). (구 15089863 한국 리콜은 폐기 → 3048950 CSV 로 적재 완료 = 확정)

### 3.6 외부 데이터 통합 매트릭스 (확정 / 잠정 / 미정)

| 소스 | 도메인 | 상태 | 근거 |
|---|---|---|---|
| DART Open API | finance | [확정] 활성 | `ingestion/dart_client.py` + `fin.*` 184K rows |
| KRX 마스터 | finance | [확정] 활성 | `master.companies` 295 |
| ECOS | finance | [확정] 활성 | `macro.series` |
| Wikidata SPARQL | both | [확정] 활성 | `wiki.wikidata_facts` 466, `master.entity_map` 보강 |
| Wikipedia (ko) | finance | [확정] 활성 | `wiki.wikipedia_pages` 276 (93.6% 매핑) |
| 연합뉴스 RSS | finance | [확정] 활성 (메타+요약만, 저작권) | `news.articles` 338 |
| SEC EDGAR | finance | [확정] 활성 (한국 ADR 한정) | `sec.filings` 1,857 |
| GLEIF | finance | [확정] 활성 | `sec.lei` 2,700 (LEI 매칭 120) |
| KCGS ESG | finance | [잠정] 수동 CSV (회원 라이선스) | `docs/data_lineage.md §1.8 KCGS ESG` |
| 공정위 기업집단 (data.go.kr) | finance | [미정] 키 확보 후 | `README §4` |
| KOSIS 산업통계 | finance | [미정] 키 확보 후 | `README §4` |
| KIPRIS 특허 | finance | [미정] 키 확보 후 | `README §4` |
| LAW.go.kr | finance | [미정] 키 확보 후 | `README §4` |
| NHTSA vPIC | auto | [확정] 활성 | `auto.master_*` 22K + 6.7K + 237 |
| NHTSA Recalls | auto | [확정] 활성 | 219 (92% mfr/model/variant 매핑) |
| NHTSA Complaints | auto | [확정] 활성 | 16,005 (97% 매핑) |
| NHTSA SafetyRatings | auto | [확정] 활성 | `spec_measurements.safety.ncap.*` |
| AI Hub (부품 결함 71347, 자율 578) | auto | [확정] 활성 | `:Module` + CONTAINS_COMPONENT |
| data.go.kr 3048950 (한국 리콜 CSV) | auto | [확정] 941 row 적재 (구 15089863 API 폐기) | `loaders/load_datagokr_recalls.py --csv` |
| data.go.kr 15155857 (수리검사 CSV) | auto | [잠정] 인터페이스 wired, raw 수동 | `ingestion/datagokr_inspections.py` |
| car.go.kr | auto | [잠정] CSV 파서만, 공식 API 미정 | `ingestion/car_go_kr_recalls.py` |
| KATRI (bigdata-tic) | auto | [잠정] OAuth 인터페이스, credentials 필요 | `ingestion/katri_tic.py` |
| KNCAP | auto | [잠정] 인터페이스 wired, raw 부재 시 skip | `ingestion/kncap.py` |
| Euro NCAP / IIHS | auto | [미정] 채널·약관 검토 후 | `docs/autograph.md §5` |
| KOTSA 수리검사 (자료) | auto | [확정] 인터페이스 + CSV 다운로드 (graceful skip) | `ingestion/datagokr_inspections.py` |

[확정] 활성: 16종 (실데이터 적재됨).

[잠정] 인터페이스만: 5종 (키/credentials/raw 만 보강하면 즉시 활성).

[미정] 채널 협의 후: 5종.

### 3.7 평가·측정 인프라

#### 3.7.1 Gold QA

- `eval/qa_gold/gold_qa_v0.jsonl` — finance, **seed 30** ([잠정] 목표 100, `README §6`).
- `eval/qa_gold/gold_qa_auto_v0.jsonl` — auto, **seed 46** ([잠정] 목표 100).
- `eval/qa_gold/gold_qa_cross_v0.jsonl` — Cross-Domain, **44 row** (level 기준 CD-L1=10 / L2=8 / L3=12 / L4=8 + 6 row IP 결합 변형. qid prefix 기준은 CD-L3- 15 / CD-L4- 11) ([잠정] 확장 대기).
- `eval/qa_gold/gold_qa_ip_v0.jsonl` — ip, **seed 30** (IP-L1/L2/L3 각 10. gold_answer 채우기는 KIPRIS/USPTO 적재 후).
- lint: `make validate-gold-qa` (`scripts/audit/validate_gold_qa.py`).

#### 3.7.2 메트릭

[확정] 4 메트릭 신규 (Phase B):
- `eval/metrics/bridge_quality.py` — Bridge confidence ≥ 0.9 비율 (목표 80%+).
- `eval/metrics/main_hop_efficiency.py` — vector 단독 대비 노드 탐색 수 감소 (목표 −30%).
- `eval/metrics/confidence_weighted.py` — 답변 confidence × accuracy.
- `eval/metrics/latency.py` — 도메인 내 < 8초, Cross < 12초.

기존: `em_f1`, `llm_judge`, `faithfulness`.

#### 3.7.3 비교 매트릭스

[미정 — 실측 미수행] 4 어댑터 × 3 LLM = 12 조합 (`README §6`):
- 어댑터: Vector only / Graph only / Hybrid Agent / SQL+Vector.
- LLM: OpenAI / Anthropic / Local 각각.
- Cross-Domain 은 Hybrid+Bridge 단독 (다른 어댑터는 Bridge 미사용).

#### 3.7.4 DoD (Definition of Done) — 14 항

[확정] PRD §10 의 14 DoD 중 측정 가능한 5 항 완료 (커밋 `e7f1224`, `b1be342`). 나머지는 LLM 실측·trace 필요.

`make audit-dod` 가 14 항 트래픽라이트 종합 리포트 생성 (`eval/reports/dod_v2.1.md`, gitignored).

### 3.8 안전 가드 — 다층 방어

| 가드 | 위치 | 무엇을 막는가 |
|---|---|---|
| **prompt_safety** | `safety/prompt_safety.py` | XML 경계 escape, injection 신호 감지 → `state['safety_signals']` |
| **cypher_guard** | `safety/cypher_guard.py` | READ-ONLY 강제 (CREATE/MERGE/DELETE 금지), 템플릿 매개변수 타입 검증 |
| **language_guard** | `safety/language_guard.py` | 한국어 char ratio (응답이 다른 언어로 새는 것 방지) |
| **number_guard** | `agents/number_guard.py` | synth 입력의 큰 수치는 PG 결과 화이트리스트만 인용 가능. 환각 수치 차단 |
| **cost_estimator** | `agents/cost_estimator.py` | LLM 호출 사전 비용 추정 (replan factor 포함). `LLM_COST_AUTO_APPROVE_USD` 초과 시 user approval interrupt |
| **budget_aware_client** | `llm/budget_aware.py` | 역할별 모델 라우팅 + HARD_LIMIT_USD |
| **DAG cycle / dependency** | `agents/supervisor.py` | task DAG 순환 검증, depends_on 위반 거부 |
| **Calculator sandbox** | `agents/workers.py:11-13` | numexpr 한정 evaluator — exec/eval/import/attribute 금지 |
| **HITL clarification** | `agents/interrupts.py` | 모호 회사명(margin<10%) 사용자 선택 |

[확정] 다층 방어. 한 가드가 뚫려도 다음 층에서 잡히는 설계.

### 3.9 LLM 어댑터 패턴

[확정] `LLMClient` 단일 인터페이스 (`src/autonexusgraph/llm/*_adapter.py`). 환경변수 `LLM_PROVIDER` 한 줄로 백엔드 교체 — Anthropic / OpenAI / Local.

[확정] 역할별 모델 분리 (`llm/config.py:31-39`):
- `llm_model_planner`, `llm_model_graph`, `llm_model_synthesizer`, …
- 각 역할이 다른 모델 사용 가능 (Synthesizer = 강한 모델, Planner = 빠른 모델 등).

[확정] 비용 추적: `llm/cost_tracker.py`. 예산 인식 라우팅: `llm/budget_aware.py`.

[잠정] Local provider 구체 모델은 환경 의존 (.env). 코드는 인터페이스만.

---

## 4. 설계 의도 / 트레이드오프 / 대안

각 박스: **결정 / 의도된 이득 / 비용 / 대안 / 대안의 트레이드오프 / 라벨**.

이 절은 결론을 짓지 않는다. "X 면 Y 를 잃는다" 까지만. 독자가 답을 만들기 위한 자료.

### 4.1 왜 LangGraph multi-agent

- **결정**: LangGraph 의 StateGraph 로 5단계 노드를 명시적 상태로 모델링. Send API 로 worker 병렬.
- **이득**: 재현 가능성·디버깅 가능성. checkpoint 로 multi-turn / replan 자연스러움. tracing(Langfuse/LangSmith) 통합 쉬움.
- **비용**: LangGraph 의존 (`pip install -e ".[agent]"`). state 가 큰 dict 라 직렬화 비용. cyclic graph 디버깅 난이도.
- **대안**:
  - **단일 LLM Chain (ReAct)** — 가볍지만 multi-turn replan 모델링 어려움.
  - **AutoGen / CrewAI** — agent 추상화는 비슷하지만 state 가 implicit.
  - **자체 구현** — LangGraph 의 checkpoint·SSE streaming 을 재구현해야 함.
- **대안 트레이드오프**: ReAct → 추적성 손실. AutoGen → 디버깅 시 state 흐름 불투명.
- [확정] LangGraph 선택. docs/operations/agents.md (구 PRD §7.5) 가 SSOT.
- **열린 질문**: LangGraph 의 lock-in. 만일 LangChain 생태가 stale 되면? — 추상화 깊이가 얕아서 교체 가능성 [잠정].

### 4.2 왜 3-Store 하이브리드

- **결정**: Neo4j(관계) + PostgreSQL(수치·메타) + pgvector(의미). 한 청크가 100만 이하면 Qdrant 안 씀.
- **이득**: 각 저장소가 잘 하는 일만 시킴. 수치는 PG, 관계는 Neo4j, 검색은 pgvector. **재무 수치 환각 차단** = PG only.
- **비용**: 3 저장소 운영 (백업·마이그레이션·동기화). 같은 사실이 PG + Neo4j 양쪽에 (예: SUBSIDIARY_OF 관계가 fin.subsidiaries + Neo4j 양쪽).
- **대안**:
  - **PG + pgvector 단독** — Neo4j 제거. 다홉 그래프 쿼리는 recursive CTE / SQL. 가능하지만 Cypher 대비 표현력 손실, 깊이 N 가변 쿼리 어려움.
  - **Neo4j + pgvector** — PG 제거. 수치도 Neo4j 속성으로. ACID 트랜잭션·집계 성능 손실.
  - **GraphRAG single-store (e.g., Neo4j vector index)** — 단순. 시계열·복잡한 수치 비교 어려움.
- **대안 트레이드오프**: PG+pgvector 단독 → 깊이 1-3 쿼리도 가능하긴 하나, `find_paths` 같은 가변 hops 가 매우 어색.
- [확정] 3-Store. 핵심 원칙: 수치 LLM 생성 금지 → PG only.

### 4.3 왜 사전 정의 도구만 (LLM 자유 SQL/Cypher 금지)

- **결정**: LLM 은 함수명 + 파라미터만 결정. 사전 정의 함수 ~40개.
- **이득**: SQL injection 차단. 그래프 폭발(`MATCH (a)-[*]->(b)`) 방지. 토큰 폭발 방지. 출처 추적 가능.
- **비용**: 새 질문 유형이 등장하면 함수 추가가 필요. LLM 의 "창의적 해결" 봉쇄.
- **대안**:
  - **LLM 자유 SQL/Cypher 생성** — 유연하지만 모든 보안 가드를 LLM 뒤에서 사후 검증해야 함.
  - **DSL 중간층** — LLM 이 DSL 생성 → DSL 컴파일러가 SQL/Cypher 생성. 표현력은 사전 정의보다 높고 자유 SQL 보다 안전.
- **대안 트레이드오프**: 자유 SQL → 1건의 prompt injection 이 전체 DB 노출. DSL → 컴파일러 자체가 또 하나의 시스템.
- [확정] 사전 정의만. docs/operations/agents.md (구 PRD §7.5).10.

### 4.4 왜 Deterministic-first 추출 (LLM 은 selective)

- **결정**: 정형 데이터는 룰 매핑 0% LLM. 서술형 텍스트만 P3 LLM. P3 결과는 P4 cross-validate.
- **이득**: 환각 원천 차단. confidence 라벨링 정량적. 비용 절감.
- **비용**: 룰 작성 노동. 정형의 변경 (예: NHTSA 스키마 변경) 시 ingester 코드 수정 필요.
- **대안**:
  - **LLM full-pass** — 모든 데이터를 LLM 으로 그래프 추출. 빠르지만 confidence 약함, P4 검증 없으면 환각 누적.
  - **Knowledge Distillation** — LLM 으로 생성 후 사람 검토로 룰 학습. 초기 비용 큼.
- **대안 트레이드오프**: full-pass → 비용 + 환각. KD → MVP 속도 저하.
- [확정] README §3.6 (4-Pass) 의 "Deterministic-first + Selective LLM" 가 SSOT.

### 4.5 왜 별도 `autograph` 패키지

- **결정**: auto 도메인을 별도 패키지로. import 시 자동 등록.
- **이득**: 코어 ↔ 도메인 의존 방향 정상화 (autograph → core). autograph 미설치 시 core 는 finance 만 동작. README §10.12 "core 변경 < 5%".
- **비용**: import 시점 부작용(side effect)에 의존. 테스트 격리 어려움 (`import autograph` 만 해도 레지스트리 변경).
- **대안**:
  - **단일 패키지** — `autonexusgraph` 안에 finance / auto 분리. 의존 방향 양방향. README §10.12 미달.
  - **core / finance / auto 3분할** — `autonexusgraph_core` + `fingraph` + `autograph`. 깔끔하지만 패키지 3개 운영.
- **대안 트레이드오프**: 단일 → core 무수정 도메인 추가 불가. 3분할 → finance 어댑터 분리 비용 발생 (3.1.4 의 [의도 확인 필요]).
- [확정 — 현재 구조] 2분할 (autonexusgraph + autograph), import 자동 등록. **v2.2 IPGraph 흡수 후 = 2분할 + ipgraph (코어/finance 는 여전히 미분리, §3.1.4 의 옵션 B 채택).**
- [잠정] 3분할 (pure core 분리) 가능성 — README §11.1 (구 PRD v2.2 §12.5) 본문 + §11.1 baseline reset 정책으로 "옵션 B 우선" 결정. 누적 변경량이 임계 초과 시 옵션 A 재고 (§3.1.4 참조).

### 4.6 왜 ER 마스터 + Bridge

- **결정**: 도메인 직접 FK 가 아니라, `master.entities` (단일 ID 공간) + `bridge.corp_entity` (cross-domain 다리).
- **이득**: 도메인 추가 시 신규 FK 추가 없음. confidence 와 reviewed_status 를 bridge 자체에 저장.
- **비용**: 모든 cross-domain 조회가 bridge 1 hop 추가. bridge 신뢰도가 cross-domain 정답률을 결정.
- **대안**:
  - **도메인 직접 FK** — `auto.manufacturer.corp_code` 같이 직접 참조. 1 hop 절감. 하지만 매칭 confidence 표현 불가, 도메인 N 일 때 FK N(N-1)/2.
  - **글로벌 single graph** — 모든 엔티티가 Neo4j 단일 그래프. 도메인 경계 흐려짐. 권한·테스트 격리 어려움.
- **대안 트레이드오프**: 직접 FK → 다도메인 확장 어려움. single graph → 격리·관리 어려움.
- [확정] Bridge 분리. README §3.5.

### 4.7 왜 한국어 자체 BGE-M3

- **결정**: BGE-M3 (1024d, cosine) 자체 호스팅 + BGE-Reranker-v2-m3 (옵션).
- **이득**: 한국어 성능. 비용 0 (외부 API 없음). 데이터 외부 송신 없음.
- **비용**: GPU 운영. 모델 업그레이드 시 backfill (vec.chunks 748K+).
- **대안**:
  - **OpenAI text-embedding-3-large** — 외부 API. 한국어 성능 차이 (BGE 대비). 비용 발생.
  - **Cohere multilingual-3** — 비슷한 트레이드오프.
- **대안 트레이드오프**: 외부 API → 데이터 송신 + 비용. 모델 종속.
- [확정] BGE-M3. README §8.

### 4.8 왜 LLM 어댑터 패턴

- **결정**: `LLMClient` 인터페이스. provider 환경변수 1줄로 교체.
- **이득**: 의존성 최소화 (Anthropic SDK 직사용 안 함). vendor lock-in 회피.
- **비용**: 각 provider 의 고유 기능 (Anthropic prompt caching, OpenAI tools 등) 활용 시 어댑터 확장 필요.
- **대안**:
  - **LangChain ChatModel** — provider 다양성 비슷하지만 LangChain 의존성 확대.
  - **Direct SDK** — provider 별 분기 코드 도배.
- **대안 트레이드오프**: LangChain → 추상화 비용 + 의존. Direct → 매 노드마다 분기.
- [확정] 자체 어댑터.

### 4.9 왜 Cross-Domain QA 4단계 층화

- **결정**: CD-L1 (제조사↔상장사 직접) / L2 (모델↔제조사↔재무) / L3 (부품·공급사↔OEM↔재무) / L4 (시점 포함 공급망↔ESG).
- **이득**: 난이도별 목표치 명시. L1 = 80%+, L4 = 40%+. PRD v2.0 의 "일률 60%+" 가 너무 거칠다는 비판 해소.
- **비용**: gold QA 큐레이션 시 분류 노동. 분류 경계 (L2/L3) 모호 케이스.
- **대안**:
  - **단일 정답률 목표** — 간단. 하지만 난이도 분포에 따라 의미 변형.
  - **연속 난이도 점수** — hop 수·필요 도구 수 가중. 사람이 분류 안 해도 됨. 그러나 자동 점수의 신뢰성.
- **대안 트레이드오프**: 단일 → 평가 신뢰도 손실. 연속 → 자동 점수가 정답률과 단조가 맞는지 검증 필요.
- [확정] 4단계 층화. README §6 (4단계 층화).

### 4.10 왜 `confidence_score` 0.40~1.00 스칼라 (vs A/B/C 카테고리)

- **결정**: 0.40 ~ 1.00 스칼라 + A/B/C 등급 (등급은 기본값 결정용).
- **이득**: 가중 합·정렬·랭킹 가능. 메트릭 (confidence_weighted_accuracy) 계산 쉬움.
- **비용**: 0.50 vs 0.55 의 의미 차이가 임의적. 정량성 가정 (§5.2).
- **대안**:
  - **카테고리만 (A/B/C)** — 임의성 줄어듬. 그러나 가중 합·랭킹 어려움.
  - **Bayesian 확률 보정** — 출처별 정답률을 사후 추정. 사전 작업 큼.
- **대안 트레이드오프**: 카테고리 → 그래프 랭킹 표현력 손실. Bayesian → MVP 비용.
- [확정] 스칼라 + 등급 기본값.
- [가정] 스칼라가 정답률과 단조 — 미검증 (§5.2).

---

## 5. 열린 질문 / 위험 / 숨은 가정

이 절이 **세미나용 핵심**이다. 답을 정하지 않고 문제만 잘 던지는 게 목적.

### 5.1 도메인 일반성 가정의 미검증

- **[가정]** 3번째 도메인 추가 비용 < 5% 코어 변경.
- 자동차 추가 시 코어 변경 4.47% — 5% 미만 (`README §10.12 회귀 논쟁`). 그러나 그 안에 `agents/nodes.py` 가 `autograph.policy` 를 import 한 흔적 — 진짜 "코어 = autograph 무지" 상태인가? `_domain_handler.py:117-130` 의 자동 폴백이 정말 finance 무지 상태로 동작하는지 통합 테스트 없음 (`docs/autograph.md §6` 의 "통합 테스트(pytest -m integration)는 마커가 부여된 케이스가 코드베이스에 없어 0개 실행").
- **[위험]** 3번째 도메인 추가 시 비슷한 4% 가 추가로 발생 → 누적 9% → 5% 가정 깨짐.
- **[열린 질문]** "코어 변경 0%" 가 가능한 인터페이스 (e.g. handler 가 더 많은 메서드 보유) 가 무엇인가?

### 5.2 confidence_score 의 정량성

- **[가정]** 0.40 / 0.50 / 0.70 / 0.80 / 0.95 가 실제 정답률과 단조 관계 (`README §4.0`).
- 출처 등급은 "전문가 직관" 으로 정해짐. 검증된 적 없음.
- **[위험]** LLM-extracted edge (C, 0.50) 와 deterministic edge (A, 0.95) 가 같은 척도 (scalar 0~1) 로 비교돼도 되는가? 두 분포는 의미가 다를 수 있다 (deterministic 의 0.95 ≠ LLM 의 0.95).
- **[열린 질문]** confidence_score 의 사후 검증 — gold QA 정답 ↔ 사용된 edge 의 confidence 분포로 calibration 가능. `confidence_weighted_accuracy` 메트릭이 이걸 측정할 수 있는가?
- 관련 메트릭: `eval/metrics/confidence_weighted.py`.

### 5.3 Bridge 자동 매칭의 false positive

- 매칭 우선순위: QID > LEI > 사업자번호 > name. 앞 셋은 정확하지만 **name 매칭은 false-positive 위험**.
- 한글 정규화: "현대자동차(주)" / "현대차" / "Hyundai Motor Company" 가 같은 회사인가? 동음이의 (예: "한국타이어" vs "한국타이어앤테크놀로지")?
- 정책: name 단독 매칭 → `candidate` 만. `validated` 승급은 사람 검토 필요.
- **[위험]** 영구 candidate 누적이 graph 쿼리에서 노이즈 — `WHERE reviewed_status <> 'rejected'` 필터링하지만, candidate 도 통과.
- **[열린 질문]** candidate 의 자동 만료 정책 (예: 6개월 미검토 → 자동 rejected)?
- **[미정]** 운영 검토 프로세스 (누가, 얼마나 자주, 어떤 UI 로 검토) — 코드/PRD 에 명시 없음.

### 5.4 BOM Level 5/6 데이터 본질 문제

- L5 (Part) 는 리콜 본문 LLM 추출로만 자연 발생. L6 (Material/Process) 는 non-goal.
- **[열린 질문]** L5 의 미완은:
  - (a) **데이터 본질 부재** — 공개 채널 자체가 없음 (예: OEM 내부 BOM 비공개)
  - (b) **수집 비용** — 채널은 있지만 (부품사 IR, 분해 자료) 비용·약관 문제
  - (c) **모델링 부재** — Part 의 정체성 정의 어려움 (같은 부품 번호가 OEM 별로 다름)
- (a) 와 (c) 는 본질, (b) 는 시간이 풀어줌. 어느 쪽인가?
- **[미정]** 부품사 IR을 selective LLM 으로 긁는 것이 정당화되는가 (라이선스·정확도 양면).

### 5.5 LLM 비용 가드의 실측 한계

- `HARD_LIMIT_USD` 가드 + `LLM_COST_AUTO_APPROVE_USD` interrupt + replan ≤ 2.
- **[위험]** turn 당 비용 = (planner + N workers + synth) × (1 + replan). replan = 2 라면 3 배. tasks DAG 가 큰 경우 (cross_domain) 더 곱셈.
- **[가정]** `cost_estimator` 의 사전 추정이 실제 비용과 ±20% 이내. 검증 없음.
- **[열린 질문]** budget guard 가 turn 중간에 발동하면 — 이미 시작된 worker 의 sunk cost 처리?
- **[열린 질문]** HARD_LIMIT 도달 시 사용자 경험 — "예산 초과로 답변 불가" 가 신뢰를 어떻게 깎는가?
- 관련: `agents/cost_estimator.py`, `llm/budget_aware.py`, `docs/operations/agents.md (구 PRD §7.5).6`.

### 5.6 동명이인 / 다중 식별자 충돌

- **finance**: `master.persons` 는 (name, birth_year) 키로 동명이인 분리 (`README §1.1`).
- **[열린 질문]** `birth_year` 가 없는 인물 (DART 비공개) — 동명이인 묶을 키 없음. 현재 어떻게 처리?
- **회사**: corp_code 는 안정적이지만 `jurir_no` (법인등록번호) 가 재부여될 수 있음. snapshot_year 로 시점 분리하지만 — 같은 corp_code 가 다른 jurir_no 인 경우?
- **[열린 질문]** 자동차 측 인물 데이터 (예: 부품사 CEO) — 통합 ER 마스터의 entity_type 에 Person 이 들어가는가? auto ontology 에는 Person 없음.

### 5.7 평가셋의 자기충족 위험

- gold QA 30+42+30 행 — 작성자가 시스템에 익숙해서 "잡힐 만한" 질문만 골랐을 가능성.
- **[위험]** Multi-hop 정답률 측정의 ground truth 가 시스템 그래프에 의존. 그래프에 없는 관계는 질문도 못 만듦.
- **[열린 질문]** Vector RAG 비교 매트릭스가 의미가 있으려면, gold QA 가 "Vector 도 풀 수 있는 질문" 을 포함해야 함. 그렇지 않으면 비교가 불공평.
- **[미정]** 외부 작성 gold QA (블라인드 큐레이터) 도입 여부.

### 5.8 Cross-Domain QA 의 "정답" 정의

- CD-L4 (시점 포함 공급망 ↔ ESG): 예) "2023년 LG에너지솔루션 배터리를 쓰는 OEM 중 KCGS B+ 이상".
- **[열린 질문]** 어떤 snapshot_year 의 SUPPLIED_BY 가 정답인가? 부품사가 분기마다 공급 비율을 바꾸면?
- **[열린 질문]** Bridge.corp_entity 가 후기 매칭 (2026년 검토) 이지만 SUPPLIED_BY 는 2023년 시점 — 시점 일관성 어떻게?
- 관련: `ontology/auto/relations.yaml` 의 `snapshot_year` 메타.

### 5.9 코어와 도메인의 진짜 경계

- `register_handler` 가 import 시점 부작용 (`autograph/__init__.py:23`).
- **[위험]** 테스트에서 `import autograph` 하면 다른 테스트의 핸들러 레지스트리 오염. `unregister_handler` 함수는 있음 (`_domain_handler.py:97`) 이지만 자동 사용 안 됨.
- **[열린 질문]** 코어 단독 테스트 (`tests/autonexusgraph/`) 가 `import autograph` 없이 통과하는가? README §6 의 310 unit 테스트가 어떻게 격리되는가?
- **[열린 질문]** `agents/nodes.py:34` 가 `from ..tools.financials import lookup_company as lookup_pg` — 이게 도메인 무지 위반인지 (finance 가 코어 안에 있으니 무관인지) 의 경계가 모호.

### 5.10 `[의도 확인 필요]` 리스트 (코드만으론 안 풀림)

- `_legacy/v2/` 폴더의 운명 — 삭제 예정인가, 보존인가?
- `vec.chunks.corp_code` nullable 완화의 영구성 — auto 청크 위해 완화됐는데, finance 청크에 영향 0이라 사실상 영구로 보임 (`docs/autograph.md §6`).
- `bridge.corp_entity.reviewed_status='rejected'` 운영 프로세스 — 누가, 얼마나 자주.
- DomainHandler 의 메서드 누락 허용 (`_domain_handler.py:40-42`) — 디자인 의도인가 임시 구현인가.
- `agent_handler.py:99-100` 의 "target_makes/vehicles 는 호환 시그니처가 없어 미적용" — TODO 인가 의도된 보수성인가.

### 5.11 우선순위가 큰 미정 사항 5개 (세미나 토론용 — §5.12 production ordering 과 분리)

> **본 절 = 세미나 토론용 historical snapshot**. 운영용 11 건 우선순위는 [§5.12 통합표](#512-11-열린-질문--우선순위진행-상태-통합표-p1-7-p2-9) (2026-06-02 갱신). 본 §5.11 의 5 개 ≠ §5.12 의 P0 3 개. 차이 사유는 §5.12.1.

1. 코어와 finance 어댑터의 분리 (§3.1.4) — **v2.2 옵션 B (baseline reset 정책) 채택**. ipgraph 머지 후 누적 변경량이 임계 초과 시 옵션 A (pure core 분리) 재고.
2. confidence_score 의 calibration (§5.2) — 평가 메트릭이 신뢰 가능한지의 전제.
3. Bridge candidate 의 검토 운영 (§5.3) — graph quality 가 시간이 갈수록 떨어짐.
4. BOM Level 5 의 채널 정책 (§5.4) — non-goal vs deferred 의 경계.
5. 외부 작성 gold QA (§5.7) — 평가 자기충족 위험.

### 5.12 11 열린 질문 — 우선순위·진행 상태 통합표 (P1-7, P2-9)

> 사용자 cold review (2026-06-02) P1-(7) + P2-(9) 항목 반영. §5.1~§5.10 의 11 열린 질문을 (a) 시급도, (b) 진행 상태, (c) cross-link (data_inventory B-issue / README §11 백로그 / system_review.md) 와 함께.

| 우선순위 | 질문 | 정의 절 | 진행 상태 | cross-link | 해결 가능 시점 |
|---:|---|---|---|---|---|
| ⭐⭐⭐ P0 | confidence_score calibration | [§5.2](#52-confidence_score-의-정량성) | **미실행** — 측정 가능 (gold QA 120 row 충족) | learning_guide §11.4.0 (Platt routine) + PRD §3.5 (cross-link 완료 2026-06-02) | LLM 키 활성 + `make eval-full` 후 5분 |
| ⭐⭐⭐ P0 | 외부 작성 gold QA (자기충족 위험) | [§5.7](#57-평가셋의-자기충족-위험) | **wired (2026-06-02)** — 측정 routine `make audit-external-ratio` (실측 0/150 = 0.0%) + 변환 routine `make convert-allganize` 신규. **Allganize 흡수 후 즉시 30%+ 가능** | gold_qa_guide.md §6.3-6.4 (wired) + `scripts/audit/{convert_allganize_gold,external_curator_ratio}.py` | (a) `git clone allganize/RAG-Evaluation-Dataset-KO` → `make convert-allganize` 5분, (b) 별도 외부 큐레이터 발주는 후속 |
| ⭐⭐⭐ P0 | Bridge candidate 검토 운영 SOP | [§5.3](#53-bridge-자동-매칭의-false-positive) | **미설계** (4,790 supplier candidate 영속 누적) | README §11.4 (P1 운영) / data_inventory §3 B10 | Streamlit 검토 UI + 6개월 자동 만료 정책 |
| ⭐⭐ P1 | Cross-Domain QA "정답" 정의 | [§5.8](#58-cross-domain-qa-의-정답-정의) | **부분** — `snapshot_year` 필드 강제로 일부 해소 | gold_qa_guide §2.3 (정답 무결성 표) | snapshot_year 필드 추가 + valid_until 도입 |
| ⭐⭐ P1 | LLM 비용 가드 실측 한계 | [§5.5](#55-llm-비용-가드의-실측-한계) | **wired** — `agents/cost_estimator.py` 측정 routine 있음 | README §11.1 (P0+ 상용 신호) | `make eval-full` 후 cost_estimator ±20% 정확도 검증 |
| ⭐⭐ P1 | 코어와 finance 어댑터 분리 (P0+) | [§5.1](#51-도메인-일반성-가정의-미검증), [§5.9](#59-코어와-도메인의-진짜-경계) | **옵션 B (baseline reset) 채택** — 정직 review 추가 완료 | `eval/reports/core_diff_baseline_ledger.md §D` (정직 review 신설 2026-06-02) | ipgraph 후 도메인4 추가 시 inflection 비교 |
| ⭐⭐ P1 | 동명이인 / 다중 식별자 충돌 | [§5.6](#56-동명이인--다중-식별자-충돌) | **부분** — (name, birth_year) 키 사용, HITL clarification interrupt 활성 | api_reference.md §1.2 (lookup_person), faq.md Q6.3 | (name, birth_year, 회사) 보조 키 추가 |
| ⭐⭐ P1 | BOM L5/L6 채널 정책 | [§5.4](#54-bom-level-56-데이터-본질-문제) | **L6 부분 진입** (USGS MCS 5 + materials 6 + DERIVED_FROM 17) / L5 sparse | README §10.2 / autograph.md §2.5.4 (배터리·소재 부록) | data.go.kr 키 발급 + Wikipedia plant 문서 ingestion |
| ⭐ P2 | 도메인 일반성 가정의 미검증 | [§5.1](#51-도메인-일반성-가정의-미검증) | **부분** — ip 도메인 적용 후 §10.15 코어 변경 0% 측정 완료 | README §10.15 / core_diff_baseline_ledger | ip + 4번째 도메인 (Phase D/E) 측정 후 |
| ⭐ P2 | DomainHandler 메서드 누락 허용 정책 | [§5.10](#510-의도-확인-필요-리스트-코드만으론-안-풀림) | **[의도 확인 필요]** — 핸들러가 일부 메서드만 구현해도 동작 | architecture.md §6 plug-in 등록 메커니즘 | 의도 확정 + 테스트 추가 |
| ⭐ P2 | 추출 파이프라인 LLM 비활성 P3 4종 | [§5.10](#510-의도-확인-필요-리스트-코드만으론-안-풀림) | **wired-but-disabled** (COMPETES_WITH 등 4종) | README §7 미구현 표 / autograph.md §5.1 SUPPLIED_BY 정직 표시 | 비용·환각 위험 검증 후 selective 활성 |

**B-issue (`data_inventory.md §3`) cross-link**:
- B7 (Wikidata P176 rate-limit) ↔ §5.3 (Bridge candidate) ↔ §5.4 (BOM L5/L6) — **공급망 자동 추출 부재의 뿌리**
- B10 (Supplier 중복) ↔ §5.3 (Bridge candidate 누적) — **같은 뿌리 = name_norm dedup 정책 부재**
- B11 (NHTSA complaint 짧은 카테고리) — §5.4 (BOM 채널 정책) 와 partial 관련

**README §11 백로그 cross-link**:
- §11.1 상용 신호 (P0+) — MCP / Langfuse / SHACL / 축소 평가 매트릭스 = §5.5 (비용 가드), §5.7 (gold QA) 연결
- §11.4 데이터 품질·운영 (P1) — §5.3 (Bridge candidate SOP), §5.6 (동명이인 충돌)
- §11.6 평가·신뢰성 (P1) — §5.7 (자기충족), §5.8 (Cross-Domain 정답 정의)

**시급도 종합** (2026-06-02):
- 측정 가능한데 미실행: **3 건 (P0)** — calibration / 외부 gold / Bridge candidate SOP
- 진행 중 / 부분 해결: **6 건 (P1)**
- 장기 / 측정 대기: **2 건 (P2)**
- 진행률: 3/11 = 27% 가 즉시 실행 가능. 통합 우선순위 표 + 자랑 vs 실제 → [system_review.md](system_review.md) (이미 존재 — §1.2 한계 통합표 / §2 B-issue / §3 자랑 vs 실제 / §4 시급도 매트릭스).

### 5.12.1 각 row 의 rationale — 왜 이 우선순위? (P2-9)

> 사용자 cold review (2026-06-02) P2-(9) 항목 반영: §5.11 의 5 개 vs §5.12 의 P0 3 개 차이 정합화 + 후순위 6 개의 강등 사유 명시. 우선순위 판정 기준 = **(영향 × 즉시 실행 가능성)** — 영향 크고 즉시 측정 가능하면 P0, 영향 작거나 외부 의존이면 P1/P2.

| 순번 | 항목 | 우선순위 판단 사유 |
|---:|---|---|
| P0-1 | **confidence calibration** | 가장 자주 인용되는 시스템 자랑 (PRD §3.5) 의 정량 근거. 측정 도구 wired (`calibrate_confidence.py`), 데이터 충족 (gold 120 row), LLM 키만 있으면 5 분 — **즉시 실행성 최고** |
| P0-2 | **외부 작성 gold QA** | 평가 매트릭스 전체의 신뢰성을 좌우. 현재 0% 외부 = sanity check 수준 (gold_qa_guide §6.1). 변환 routine wired (2026-06-02), `git clone allganize/...` + `make convert-allganize` 1 회로 30%+ 가능 — **즉시 실행성 최고** |
| P0-3 | **Bridge candidate 운영 SOP** | 4,790 row supplier candidate 가 영구 누적 (data_inventory §3 B10). 시간이 지날수록 graph quality 저하 — **방치 시 시스템 가치 자체 위협**. 단 Streamlit UI 필요 = 즉시 실행 못함 → P0 이지만 "측정/디자인 우선" |
| P1-1 | **Cross-Domain QA "정답" 정의** | snapshot_year 필드로 일부 해소 (gold_qa_guide §2.3). 완전 해소엔 `valid_until` 등 시계열 정합 추가 필요 — 외부 데이터 의존 (재무·리콜 시점 매칭). 즉시 실행 불가 → P1 |
| P1-2 | **LLM 비용 가드 실측 한계** | `cost_estimator.py` wired, 측정 routine 도 wired. 단 ±20% 정확도 검증은 `eval-full` 결과 필요 — LLM 키 의존 → P0 가 아닌 P1 |
| P1-3 | **코어 ↔ finance 분리** | baseline reset (옵션 B) 채택 완료 + 정직 review (`core_diff_baseline_ledger §D`) 추가 완료. 추가 작업 = 도메인4 추가 후 inflection 재측정 = **외부 도메인 추가 의존** → P1 |
| P1-4 | **동명이인 / 다중 식별자** | `(name, birth_year)` 키 + HITL clarification 으로 부분 해소 (faq.md Q6.3). 완전 해소엔 (name, birth_year, 회사) 보조 키 + DB 마이그레이션 필요 — 작은 인프라 변경 → P1 (작업량 < P0 이지만 영향도 작음) |
| P1-5 | **BOM L5/L6** | L6 부분 진입 완료 (USGS 5 + materials 6 + DERIVED_FROM 17). **§5.11 에 P0 로 표기되었지만 §5.12 에선 P1 로 강등 사유**: (a) data.go.kr 키 + Wikipedia plant ingestion 등 **외부 데이터 의존**, (b) PRD v2.2 §2.3 명시 "회사단위 셀↔OEM 소싱은 sparse → grade C candidate 만" — **본 단계 비목표**. §5.11 의 "BOM Level 5 = 우선순위 큰 미정" 표현은 v2.1 시점 — v2.2 의사결정 (PRD §13 의사결정 표) 으로 강등됨 |
| P2-1 | **도메인 일반성 가정** | ip 도메인 적용 후 §10.15 코어 변경 0% 측정 완료 → 부분 해소. 완전 해소엔 **도메인4** (의약품/전자/에너지/식품) 측정 필요 — PRD v2.2 §2.3 "본 단계 비목표" → P2 (장기) |
| P2-2 | **DomainHandler 메서드 누락 허용 정책** | `[의도 확인 필요]` (code-derived 아닌 설계 의도 문제). 영향 작음 (현재 작동 중) + 즉시성 없음 → P2 |
| P2-3 | **추출 P3 LLM 비활성 4종** | wired-but-disabled 상태로 안정. 활성 시 비용·환각 위험 → 보수적 결정. 영향 작음 (P2 LLM 0% 추출이 메인) → P2 |

**§5.11 vs §5.12 차이 — 4 건 분류 변경 (2026-06-02)**:
- §5.11 #1 (코어-finance 분리) → §5.12 P1 강등 (baseline reset 옵션 B 채택으로 결정됨)
- §5.11 #4 (BOM Level 5) → §5.12 P1 강등 (PRD v2.2 비목표 결정 + 외부 의존)
- §5.12 신규 P0-3 (Bridge candidate SOP) — §5.11 미언급 (영향 평가가 v2.2 검토에서 격상됨)
- §5.12 신규 P0 = (calibration / 외부 gold) — 둘 다 §5.11 #2/#5 와 동일하지만 wired 상태 갱신됨

---

## 6. 다음 한 걸음 — 심화 고민용 출발점

> 이론적 설명·아키텍처·예상 청중 질문은 별도 문서 `docs/learning_guide.md` (심화 세미나 가이드) 에 정리. 이 절은 코드 진입점·체크리스트·세미나 질문만 짧게.

### 6.1 코드 읽기 추천 순서

새로 합류한 사람이 멘탈 모델을 잡는 최단 경로:

1. `src/autonexusgraph/agents/state.py` — 한 turn 의 모든 필드 (TypedDict 33 필드).
2. `src/autonexusgraph/agents/_domain_handler.py` — DomainHandler Protocol + 라우터 + ENV `AUTONEXUSGRAPH_DOMAIN_PLUGINS` soft-import.
3. `src/autograph/agent_handler.py` — auto/cross_domain 구현체.
4. `src/autograph/policy.py:1-100` (10분) — 키워드 라우팅 / question kind 분류.
5. `src/autonexusgraph/agents/nodes.py` (Triage / Planner / Synthesizer) — 각 노드의 진입 로직.
6. `src/autonexusgraph/agents/workers.py:1-100` (10분) — 4 worker + 화이트리스트.
7. `src/autonexusgraph/tools/financials.py` 와 `src/autograph/tools/spec.py` 비교 — 도메인별 도구의 동일 형태.
8. `ontology/auto/relations.yaml` (15분) — 그래프 스키마 SSOT + `edge_required_meta`.
9. `src/autograph/extractors/__init__.py` (P3 + cross-validate 진입) — 추출 파이프라인.

여기까지면 시스템의 골격 + 데이터 모델 + 한 turn 의 흐름이 머릿속에 잡힌다.

### 6.2 직접 돌려보면 좋은 것

`README §11` Quickstart 그대로. 최소 시나리오:

```bash
# 1. 인프라
make up && make health

# 2. finance 최소 데이터
make ingest-step1 && make load-companies && make load-entity-map

# 3. 자동차 최소 데이터
make ingest-auto-vpic MAKES=HYUNDAI YEARS=2024
make load-auto-all

# 4. 임베딩
make serve-embeddings  # 별도 터미널
make embed-chunks

# 5. 에이전트
python -c "from autonexusgraph.agents import run_agent; \
           print(run_agent('현대 그랜저 2024 변속기는?', domain='auto')['answer'])"
```

도메인 라우팅 동작 확인은:

```bash
# 1. 키워드 자동 판정
curl -sX POST localhost:8000/chat -H 'content-type: application/json' \
  -d '{"message":"Tesla Model Y 2023 리콜 사례 알려줘"}' | jq '.domain'
# 기대: "auto"

# 2. Cross-domain
curl -sX POST localhost:8000/chat -H 'content-type: application/json' \
  -d '{"message":"현대자동차 2024년 매출과 그랜저 리콜 건수는?"}' | jq '.domain'
# 기대: "cross_domain"
```

### 6.3 새 도메인 어댑터를 만든다면 — DomainHandler 구현 체크리스트

(가상의 예: 의약품 도메인 `pharmagraph`)

```python
# src/pharmagraph/agent_handler.py
class PharmaHandler:
    domain = "pharma"

    def identify_targets(self, state, *, question):
        # state에 target_drugs, target_companies 등 채움
        ...

    def plan_tasks(self, state, *, question):
        # task DAG 반환
        return [{"id": "...", "agent": "sql", "intent": "lookup_drug", ...}]

    def toolbox_modules(self):
        from . import tools as ph_tb
        return [ph_tb]

    def allowed_intents(self, kind):
        return {
            "graph":    PHARMA_GRAPH_ALLOWED,
            "sql":      PHARMA_SQL_ALLOWED,
            "research": PHARMA_RESEARCH_INTENTS,
        }.get(kind, set())

    def fallback_search(self, state, *, query):
        ...

    def retrieve_module(self):
        ...

# src/pharmagraph/__init__.py
from . import agent_handler  # 등록 부작용
```

체크리스트:
- [ ] `domain` 문자열 결정 (소문자, 영문).
- [ ] `ontology/pharma/{entities,relations,extractors}.yaml` 작성 + `edge_required_meta` 보유.
- [ ] PG 스키마 `pharma.*` 신설 + `bridge.corp_entity` 매칭 전략 결정.
- [ ] Cypher 템플릿 레지스트리 (`cypher_templates_pharma.py`) 작성, `__init__` 에서 병합.
- [ ] 사전 정의 도구 (`tools/spec.py`, `tools/graph.py`, `tools/retrieve.py`, `tools/bridge.py`).
- [ ] 화이트리스트 3종.
- [ ] `policy.py` 의 키워드 사전 + `route_domain` 의 cross_domain 룰.
- [ ] P1/P2 loader + P3/P4 extractor.
- [ ] gold QA seed (예: 30 row) + 메트릭에 도메인 추가.
- [ ] 코어 변경량 측정 (`scripts/audit/dod_audit.py` 의 §10.12 항).

[잠정] 위 체크리스트는 현재 코드 패턴에서 추론. PRD 에 명시 없음.

### 6.4 세미나에서 던질 만한 질문 10개

§5 의 열린 질문 중 토론 가치가 큰 것:

1. **"코어 = 코어 + finance" 의 분리를 정말 안 해도 되는가?** (§3.1.4, §5.1)
2. **confidence_score 의 calibration 없이 confidence-weighted accuracy 가 의미 있는가?** (§5.2)
3. **Bridge 의 영구 candidate 가 graph quality 를 어떻게 깎는가, 검토 운영을 누가 책임지나?** (§5.3)
4. **BOM Level 5 가 데이터 본질 문제인가, 수집 비용 문제인가 — 어느 쪽이면 무엇을 다르게 해야 하나?** (§5.4)
5. **gold QA 의 자기충족성 — 시스템이 풀 수 있는 질문만 평가하면 정답률이 의미를 잃지 않는가?** (§5.7)
6. **L4 Cross-Domain (시점 ↔ ESG) 의 정답 정의 — snapshot_year 일관성을 어떻게?** (§5.8)
7. **3번째 도메인 추가 시 핸들러 메서드 추가가 필요해질 가능성 — DomainHandler 가 적절한 추상화 깊이인가?** (§5.1, §5.9)
8. **LLM 비용 가드의 사용자 경험 — HARD_LIMIT 도달이 신뢰를 깎는 문제, 어떻게 완화?** (§5.5)
9. **Vector RAG 비교의 공정성 — Vector 가 풀 수 있는 질문이 평가셋에 충분한가?** (§5.7)
10. **자유 SQL 금지의 한계 — 새 질문 유형마다 함수 추가가 정말 지속 가능한가, DSL 중간층의 비용은?** (§4.3)

---

## Appendix A. 키워드 / 약어 사전

| 용어 | 뜻 | 더 읽을 곳 |
|---|---|---|
| **AgentState** | LangGraph TypedDict 상태. 한 turn 의 모든 누적 필드 | `src/autonexusgraph/agents/state.py:19` |
| **AutoGraph** | 자동차 도메인 어댑터 패키지 (`src/autograph/`) | `docs/autograph.md` |
| **AutoNexusGraph** | 우산 시스템 이름 + finance 코어 패키지 (`src/autonexusgraph/`) | `README.md`, `PRD §1.3` |
| **BGE-M3** | 한국어 임베딩 모델 1024d cosine | `README §8` |
| **BGE-Reranker** | 한국어 재랭킹 모델 (옵션) | `README §8` |
| **BOM** | Bill of Materials. 자동차 도메인의 계층 척추 (L0~L6) | `README §11.2`, `docs/autograph.md §2.5.4` |
| **Bridge** | Cross-domain 매칭 테이블 `bridge.corp_entity` | `README §3.5` |
| **CD-L1~L4** | Cross-Domain QA 난이도 4단계 | `PRD §2.2` |
| **Cypher template registry** | 사전 정의 22개 Cypher | `src/autonexusgraph/tools/cypher_templates.py` |
| **DAG** | Directed Acyclic Graph. Planner 가 만드는 task 의존 그래프 | `docs/operations/agents.md (구 PRD §7.5).3` |
| **DART** | 대한민국 금융감독원 전자공시. corp_code SSOT | `README §4` |
| **DoD** | Definition of Done. 14항 트래픽라이트 | `PRD §10` |
| **DomainHandler** | 코어가 도메인을 위임하는 Protocol | `src/autonexusgraph/agents/_domain_handler.py:36` |
| **edge_required_meta** | auto 엣지 의무 7키 (source_type, confidence_score, …) | `README §3.7`, `ontology/auto/relations.yaml:19` |
| **Entity Resolution (ER) 마스터** | `master.entities` + `master.entity_map`. 다형 ID 공간 | `PRD §4.5` |
| **GLEIF** | Global Legal Entity Identifier Foundation. LEI 공급 | `README §4` |
| **gold QA** | 평가용 정답 큐레이션 데이터 | `eval/qa_gold/README.md` |
| **HITL** | Human-in-the-loop. clarification / cost approval interrupt | `docs/operations/agents.md (구 PRD §7.5).6` |
| **idempotent (멱등) 파이프라인** | 재실행해도 같은 결과. raw → DB 모든 단계 | `README §2` |
| **KATRI** | 자동차안전연구원. bigdata-tic.kr OAuth | `docs/autograph.md §5` |
| **KCGS** | 한국기업지배구조원. ESG 등급 공급 | `docs/data_lineage.md §1.8 KCGS ESG` |
| **KNCAP** | 한국 신차 안전도 평가. car.go.kr | `PRD §3.2`, `docs/autograph.md §5` |
| **KOTSA** | 한국교통안전공단. 수리검사 데이터 | `README §4`, `docs/autograph.md §5` |
| **LangGraph** | Multi-agent StateGraph 프레임워크 | `docs/operations/agents.md (구 PRD §7.5)` |
| **LEI** | Legal Entity Identifier (GLEIF 발급) | `README §4` |
| **MERGE (Cypher)** | Neo4j 의 upsert. 멱등 적재의 핵심 | `loaders/load_*_neo4j.py` |
| **NHTSA** | National Highway Traffic Safety Administration (US). vPIC/Recalls/Complaints | `README §4` |
| **number_guard** | synth 입력 큰 수치를 PG 결과만 인용 가능하게 화이트리스트 | `src/autonexusgraph/agents/number_guard.py` |
| **P1/P2/P3/P4** | 추출 단계: 정형 직매핑 / deterministic 엣지 / LLM 추출 / cross-validate | `README §3.6 (4-Pass)/§6.6`, `docs/autograph.md §7.4` |
| **pgvector** | PostgreSQL 의 벡터 인덱스 확장 | `README §3` |
| **prompt_safety** | injection 신호 감지 + XML 경계 escape | `src/autonexusgraph/safety/prompt_safety.py` |
| **QID** | Wikidata 의 엔티티 ID (Q123…) | `PRD §3.2` |
| **RAG** | Retrieval-Augmented Generation | `PRD §1` |
| **replan** | Validator 실패 시 Planner 로 복귀. 최대 2회 | `state.py:71`, `docs/operations/agents.md (구 PRD §7.5).5` |
| **route_domain** | finance/auto/cross_domain 키워드 룰 라우터 | `src/autograph/policy.py:87` |
| **Send (LangGraph)** | Supervisor 의 worker 병렬 디스패치 API | `docs/operations/agents.md (구 PRD §7.5).7` |
| **snapshot_year** | 엣지의 기준 연도 메타. 시점 분리 | `ontology/auto/relations.yaml:23` |
| **SSOT** | Single Source of Truth | 전반 |
| **stage_relations** | P3 LLM 산출 임시 테이블 (`auto.staging_relations`) | `docs/autograph.md §7.4` |
| **vPIC** | NHTSA Vehicle Product Information Catalog. 제원·VIN 디코드 | `README §4` |
| **Wikidata** | CC0 글로벌 지식 그래프. QID·LEI 공급 | `README §4` |
| **XBRL** | eXtensible Business Reporting Language. DART 의 재무 표준 | `README §1.1` |

---

## Appendix B. 핵심 진입점 파일 가이드

| 영역 | 파일 | 용도 |
|---|---|---|
| 에이전트 상태 | `src/autonexusgraph/agents/state.py:19` | TypedDict 정의 |
| 에이전트 진입 | `src/autonexusgraph/agents/graph.py` | StateGraph 조립 + `run_agent` |
| 노드 | `src/autonexusgraph/agents/nodes.py` | Triage / Planner / Synthesizer |
| Supervisor | `src/autonexusgraph/agents/supervisor.py` | DAG 디스패치 + Send |
| Workers | `src/autonexusgraph/agents/workers.py` | 4 worker + 화이트리스트 |
| Validator | `src/autonexusgraph/agents/validator.py` | grounding + replan 판정 |
| Domain handler protocol | `src/autonexusgraph/agents/_domain_handler.py` | Protocol + registry + auto_detect_domain |
| 도메인 라우팅 | `src/autograph/policy.py:87` | `route_domain` |
| 도메인 핸들러 | `src/autograph/agent_handler.py:64` | AutoHandler / CrossDomainHandler |
| 자동 등록 | `src/autograph/__init__.py:23` | `from . import agent_handler` |
| 사전 정의 도구 (finance) | `src/autonexusgraph/tools/{financials,graph,retrieve}.py` | LLM 호출 대상 |
| 사전 정의 도구 (auto) | `src/autograph/tools/{spec,graph,retrieve,bridge}.py` | LLM 호출 대상 |
| Cypher 템플릿 | `src/autonexusgraph/tools/cypher_templates.py` + `src/autograph/cypher_templates_auto.py` | 사전 등록 22+ |
| 안전 가드 | `src/autonexusgraph/safety/{prompt_safety,cypher_guard,language_guard}.py` | 다층 방어 |
| number_guard | `src/autonexusgraph/agents/number_guard.py` | synth 수치 화이트리스트 |
| cost_estimator | `src/autonexusgraph/agents/cost_estimator.py` | LLM 사전 비용 추정 |
| LLM 어댑터 | `src/autonexusgraph/llm/{anthropic_adapter,openai_adapter,local_adapter}.py` | Provider 추상화 |
| LLM 라우팅 | `src/autonexusgraph/llm/budget_aware.py` | 역할별 모델 + HARD_LIMIT |
| DB 클라이언트 | `src/autonexusgraph/db/{neo4j,postgres,qdrant}.py` | 풀 관리 |
| Ontology SSOT | `ontology/{entities,relations,extractors}.yaml` (finance), `ontology/auto/*.yaml` (auto) | 그래프 스키마 SSOT |
| 인프라 스키마 | `infra/postgres/init/*.sql` (멱등 init) | PG 스키마 |
| Ingestion (finance) | `src/autonexusgraph/ingestion/*.py` | DART/KRX/ECOS/Wikidata/Wikipedia/SEC/GLEIF/News |
| Ingestion (auto) | `src/autograph/ingestion/*.py` | NHTSA/Wikidata/data.go.kr/KATRI/KNCAP |
| Loaders (finance) | `src/autonexusgraph/loaders/*.py` | raw → PG/Neo4j |
| Loaders (auto) | `src/autograph/loaders/*.py` | raw → PG/Neo4j/bridge/chunks |
| Extractors (P3/P4) | `src/autonexusgraph/extractors/` + `src/autograph/extractors/` | LLM 추출 + cross-validate |
| 평가 | `eval/{adapters,metrics,runners,qa_gold,reports}/` | 12 조합 매트릭스 |
| FastAPI | `src/autonexusgraph/api/main.py` | `/chat`, `/chat/stream`, `/threads` |
| Streamlit UI | `bin/` or scripts (`make serve-ui`) | 채팅 UI |
| Makefile | `Makefile` | 모든 진입점 자동화 |

---

## Appendix C. 본 문서의 한계

- 본 문서는 2026-05-29 시점 코드/PRD/커밋을 근거로 작성. 코드 변경 시 라벨이 stale 될 수 있다.
- 핸들러 메서드 누락 허용 / 테스트 격리 / `_legacy/v2/` 운명 등 일부 `[의도 확인 필요]` 항목은 코드만으로 확정 불가 — 설계자 인터뷰가 필요.
- `confidence_score` calibration / Bridge candidate 검토 운영 / Vector 비교 공정성 등 §5 의 열린 질문은 본 문서가 답하지 않는다. 그것이 의도다.
- 운영 절차 (Docker 가동·환경변수·.env 키) 는 `docs/operations/*.md` 에 위임. 본 문서는 멘탈 모델·트레이드오프·열린 질문에 집중.

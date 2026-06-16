# AutoNexusGraph — 통독 세미나 교재 (LEARNING)

> 이 문서 하나를 처음부터 끝까지 읽으면 시스템 전체를 이해하고, 코드를 짚어가며
> "왜 이렇게 했는가"에 답하는 심화 세미나를 진행할 수 있도록 작성됐다.
>
> **서술 규약.** (1) 사실어·기술 표현만 쓴다 — 비유·은유를 쓰지 않고 메커니즘·자료구조·
> 유도·반례로 설명한다. (2) 모든 수치는 정본(`docs/research/*`, `README.md`, `eval/reports/*`)
> 또는 코드 실측에서 인용하며 출처를 단다. (3) **배선됨(wired)** 과 **계획(planned)**,
> **측정됨** 과 **미측정**을 명시적으로 구분한다. (4) 코드 인용은 `파일:심볼` 을 쓴다 —
> 줄 번호는 stale 되므로 **심볼 이름이 우선**, grep 으로 찾는다.
>
> 본 교재는 구(舊) `docs/learning_guide.md`(이론 교재)를 흡수·재구성한 것이다. 구본은
> git 히스토리에 보존된다. 결정의 라벨([확정]/[잠정]/[미정])과 트레이드오프 카탈로그는
> 여전히 `docs/mental_model.md` 가 SSOT 이며, 본문에서 결정 사실을 인용할 때 그쪽을 가리킨다.
>
> 측정 기준일: 본문 수치는 별도 표기가 없으면 README v3.0 스냅샷(2026-06-02) 또는
> thesis 재측정(2026-06-15) 기준이다. 재현 명령(`make audit-*` / `wc -l` 등)을 함께 둔다.

---

## 0. 읽는 길 — 이 문서의 척추

이 교재는 **구체에서 추상으로** 한 방향으로만 깊어진다. 각 부는 바로 앞 부의 결론 위에
쌓이며, 어디서 멈추든 그 지점까지의 이해가 완결된다.

| 부 | 제목 | 여기까지 읽으면 안다 |
|---|---|---|
| 1 | 한 질문을 끝까지 추적 | 시스템이 입력 한 줄을 받아 답 한 줄을 내기까지 무슨 일이 일어나는가 |
| 2 | 무엇을 입력받아 무엇을 내놓는가 | 풀려는 문제의 형태와 산출물 스키마 |
| 3 | 핵심 개념 | 1부에 등장한 용어들의 정확한 정의 |
| 4 | 메커니즘(노드 단위) | 에이전트 파이프라인이 코드 레벨에서 어떻게 도는가 |
| 5 | 평가·측정 | 우위를 어떻게 숫자로 증명하는가 |
| 6 | 데이터셋·검증 | 어떤 데이터가 실재하고 어떤 것이 게이트인가 |
| 7 | 핵심 발견과 이론적 유도 | **왜** hybrid 가 이기는가, 그 상한과 반례 |
| 8 | 코드 구조 | 유지·실험을 위해 어디를 건드리는가 |
| 9 | 운영 | 설치·최소 실행·새 도메인 온보딩 |
| 10 | 메타 검토 | 흔한 혼동과 미해결 지점 |
| 11 | 부록 | 진입 경로·FAQ·읽는 순서·문서 지도·연구 계보 |

용어는 **처음 나오는 자리에서 정의**한다. 별도 용어표를 앞에 두지 않는다.

---

## 1. 한 질문을 끝까지 추적 — finance 멀티홉

> 여기까지 읽으면: 시스템의 입력→출력 한 사이클과, 같은 질문에서 벡터 검색이 왜 실패하는지를 안다.

추상 설명에 앞서 **실제로 측정에 쓰인 질문 하나**를 끝까지 따라간다. 아래는 가상의 예가
아니라 thesis gold 셋 `eval/qa_gold/gold_qa_graph_multihop_v0.jsonl` 의 실재 항목
`FIN-L3-GMI001` 이다(JSON 1행, `wc -l` = 62행 중 하나).

```
qid:        "FIN-L3-GMI001"
question:   "김명균이(가) 임원으로 재직하는 회사의 자회사는 무엇인가? 모두 답하라."
hop_count:  2
requires_multi_hop: true
gold_answer_text: ["(주)모보", "이지전선㈜", "㈜디케이씨", "㈜모보", "㈜지앤피우드", ...]
```

이 질문은 두 개의 관계(hop)를 **연쇄**해야 답이 나온다.
- **hop 1**: 인물 `김명균` → 그가 임원인 회사(`EXECUTIVE_OF` 관계)
- **hop 2**: 그 회사 → 그 회사의 자회사(`SUBSIDIARY_OF` 관계)

### 1.1 단계별 산출물

한 turn 은 LangGraph `StateGraph` 의 11개 노드를 통과한다
(`src/autonexusgraph/agents/graph.py` 의 `_build_langgraph_app`, `add_node` 11회).
각 단계가 공유 상태 객체 `AgentState`(`agents/state.py:AgentState`, TypedDict)를 갱신한다.

```
입력: "김명균이 임원으로 재직하는 회사의 자회사는?"
  │
  ▼  triage_node            (agents/nodes.py:triage_node)
     · prompt injection 검사 → 통과
     · 도메인 라우팅 → "finance"
     · 엔티티 식별: PG lookup_company("김명균") = []  (인물은 회사 테이블에 없음)
       → Neo4j 폴백(lookup_person) → state["target_persons"] = ["김명균"]
  │
  ▼  planner_node           (agents/nodes.py:planner_node + agents/llm_planner.py:try_llm_plan)
     · question_kind = "structural" (자회사·임원 키워드, agents/policy.py:classify_question)
     · task DAG 2개 생성:
         t1: get_companies_of_person(person="김명균")        [graph worker]
         t2: list_subsidiaries(corp_code=$from(t1))          [graph worker, t1 의존]
  │
  ▼  supervisor → worker_graph   (agents/workers.py:graph_worker)
     · t1 실행 → Cypher 템플릿(tools/cypher_templates.py) → corp_code 00104768 (가온전선)
     · t2 의존 해소 후 실행 → list_subsidiaries(00104768) → [㈜모보, 이지전선㈜, ...]
     · 결과는 state["tool_results"] 에 누적(_concat_dedup_by("task_id") reducer)
  │
  ▼  synthesizer_node       (agents/nodes.py:synthesizer_node)
     · tool_results + evidence_chunks 를 LLM 에 넣어 답 합성
     · number_guard 로 미승인 수치 마스킹
  │
  ▼  validator_node         (agents/validator.py)
     · grounding·언어비율·환각수치 6검사 → 통과(아니면 replan, 최대 2회)
  │
  ▼  finalize
출력: answer + citations(corp_code·노드ID) + confidence + cost
```

핵심은 **hop 2 가 hop 1 의 출력(corp_code 00104768)을 입력으로 받는다**는 점이다.
이 의존 바인딩(`$from`)을 `agents/workers.py` 의 `resolve_arg_bindings` 가 해소한다.

### 1.2 같은 질문에 벡터 검색은 왜 실패하는가

이 질문을 순수 벡터 RAG(`eval/adapters/vector_adapter.py`, `search_documents` top-k)로
풀면, thesis 재측정에서 **벡터 어댑터는 "SK이노베이션…" 으로 완전 환각**한다
(`docs/research/thesis_hybrid_routing.md` §1, S-7 정밀 진단). 이유는 메커니즘에서 나온다:

- 벡터 검색은 질문 임베딩과 의미가 가까운 청크 top-k 를 반환한다.
- 정답(자회사 목록)이 한 청크 안에 `김명균`·`가온전선`·`㈜모보` 와 **함께 적혀 있어야**
  벡터가 답할 수 있다. 공시 표에서 이 세 사실은 서로 다른 문서·다른 표에 흩어져 있다.
- 즉 정답은 **여러 문서의 사실을 cross-product** 해야 나오는데, 벡터 검색은 cross-product
  연산이 없다 — 의미 유사도 정렬만 한다.

이 한 예시가 시스템 전체의 존재 이유다: **명시적 관계 그래프 traversal 이 필요한
질문**을 단일 벡터 검색이 구조적으로 못 푼다. 7부에서 이를 측정값과 상한·반례로 정식화한다.

### 1.3 이 한 예시를 어떻게 채점하는가

평가 시 이 질문의 답을 gold entity 집합과 비교한다.
- **EM(Exact Match)**: 답이 gold 엔티티를 정확히 포함하는가(`eval/metrics/em_f1.py`).
- **hits@k**: 답 엔티티가 gold 엔티티와 겹치는 비율(`eval/metrics/hits_at_k.py`).

`FIN-L3-GMI001` 이 속한 GMI 패턴(person→company→subsidiary)에서 측정값은 hybrid EM 0.625,
단발·반복 벡터 EM 0.000 이다(전체 벡터 EM 은 0.048, 7부 표). 이 한 예시의 채점이 모여
thesis 의 헤드라인 수치가 된다.

---

## 2. 무엇을 입력받아 무엇을 내놓는가

> 여기까지 읽으면: 프로젝트가 풀려는 문제의 형태와 응답 산출물의 구조를 안다.

### 2.1 한 줄 정체 (정본 인용)

`README.md:3` 의 정의(verbatim):

> 자동차/제조 (auto + BoP 공정) + 한국 상장사 재무·지배구조 (finance) 를 그래프·정형·벡터
> 하이브리드로 추론하고, `anxg_bridge.corp_entity` + `anxg_ip.assignee_corp_map` 로 특허(ip
> 보조축) 까지 한 turn 안에 묶는 산업·기업 인텔리전스 그래프.

입력은 **자연어 질문 1개**(+ 선택적 멀티턴 history, 도메인 힌트)이고, 출력은
**근거가 달린 답변 1개**다.

### 2.2 단일 벡터 RAG 가 못 푸는 4종 질문

시스템이 표적으로 삼는 질문은 README §0 가 명시한 4종으로, 모두 단일 store 로는
구조적으로 풀 수 없다.

| 유형 | 예 | 단일 벡터로 못 푸는 이유 |
|---|---|---|
| 멀티홉 | "김명균이 임원인 회사의 자회사는?" | 관계 연쇄 = cross-product, 벡터에 없음 |
| Cross-Domain | "현대모비스 매출 + 모비스 공급 차종의 리콜" | bridge 매핑이 청크 안에 없음 |
| 시점 포함 공급망 | "2023년 LG엔솔 배터리 쓰는 OEM" | 시점·관계 동시 제약 |
| BoM ⟂ BoP 직교 | "이 부품을 만드는 공정" | 물리 계층(부품)과 공정 계층의 직교 결합 |

### 2.3 산출물 스키마

응답은 `src/autonexusgraph/api/main.py`(FastAPI `POST /chat`)와 에이전트 반환값에서
다음 필드를 담는다(`AgentState` 합성·검증 키, `agents/state.py`):

- `answer` — 자연어 답변.
- `citations` — 출처 목록. 각 인용은 `chunk_id` / `corp_code` / `rcept_no` / Neo4j 노드ID 중
  하나로 추적 가능하며 confidence 등급을 동반한다.
- `validation_status` / `grounding` — 검증 통과 여부와 grounding 신호.
- `llm_usage_usd` / `llm_tokens_used` — 이 turn 의 비용.

원칙(`README §3`): **재무 수치는 절대 LLM 이 생성하지 않는다** — 반드시 PostgreSQL 조회
결과만 인용한다. 이 원칙은 4부의 number_guard + validator 이중 방어로 강제된다.

---

## 3. 핵심 개념

> 여기까지 읽으면: 1부에 등장한 용어를 정확히 정의할 수 있다.

각 용어를 메커니즘으로 정의한다.

- **3-store 하이브리드.** 세 저장소에 책임을 분리한다. **Neo4j**(LPG: Labeled Property
  Graph) = 관계·구조 traversal. **PostgreSQL** = 정확한 수치·메타(XBRL 재무·spec·마스터).
  **pgvector** = 의미·서술 검색(BGE-M3 1024차원 임베딩). 코드 진입점은 각각
  `tools/graph.py`, `tools/financials.py`, `tools/retrieve.py`.

- **store-aware routing.** 질문의 성격에 따라 어느 store 를 쓸지 planner 가 결정하는 것.
  관계 질문→graph, 수치 질문→SQL, 서술 질문→vector. 이 라우팅이 본 시스템의 연구 기여이며
  7부의 측정 대상이다.

- **LPG 멀티홉.** Neo4j 는 노드와 관계에 속성을 붙이는 그래프 모델이다. `(:Anxg_Person)
  -[:EXECUTIVE_OF]->(:Anxg_Company)-[:SUBSIDIARY_OF]->...` 형태로 관계를 연쇄(다홉)해 답을
  **계산**한다. 벡터 검색이 못 하는 cross-product 가 여기서는 Cypher path 로 환원된다.

- **결정적-우선 추출(deterministic-first).** 데이터 적재 시 LLM 을 가능한 한 쓰지 않는다.
  4단계 패스 P1~P4 중 P1·P2 는 LLM 0%(KRX/DART/XBRL/Wikidata SPARQL 등 정형 소스 직적재),
  P3 만 선택적 LLM, P4 는 rule 기반 cross-check. 재무·지배구조는 전적으로 LLM 우회.

- **whitelist 도구 풀.** 에이전트는 자유 SQL/Cypher 를 생성하지 못한다. 사전 정의된 함수
  (`tools/*.py`)와 정적 Cypher 템플릿(`tools/cypher_templates.py`)만 호출한다. planner 가
  고른 intent 가 도메인별 화이트리스트(`allowed_intents`)에 없으면 드롭된다.

- **fallback(벡터 폴백).** graph/SQL task 가 모두 실패·skip 하면 usable 증거가 0 이 되고,
  이때 벡터 검색으로 폴백한다(`agents/nodes.py:_attempt_fallback_recovery`). 4.5절 참조.

- **confidence 등급.** 인용마다 0.40~1.00 스칼라 신뢰도를 붙인다. 카테고리(A/B/C)가 아니라
  연속 스칼라인 이유는 calibration(Platt scaling)을 적용하기 위함이다(`mental_model.md §4.10`).

- **namespace 격리.** 공유 DB 에서 본 프로젝트 데이터만 분리한다. PG 는 `anxg_` 스키마
  접두, Neo4j 는 `Anxg_` 라벨 접두(관계 타입은 접두 안 함), 모든 Neo4j 세션은 `get_session()`
  단일 진입점을 거친다. 8.4절에서 상술.

---

## 4. 메커니즘 — 노드 단위로 본 추론 흐름

> 여기까지 읽으면: 에이전트 파이프라인이 코드 레벨에서 어떻게 도는가를 설명할 수 있다.

### 4.1 11개 노드와 와이어링

`src/autonexusgraph/agents/graph.py` 의 `_build_langgraph_app` 가 등록하는 노드(실측 `add_node` 11회):

```
triage → planner → supervisor ─┬─(Send 병렬)→ worker_research
                               ├──────────────→ worker_graph
                               ├──────────────→ worker_sql
                               ├──────────────→ worker_calculator
                               └─(tasks 비면)─→ executor_legacy
worker_* ──(fan-in)→ supervisor ──(DAG 소진)→ synthesizer → validator ─┬→ finalize → END
                                                                       └→ planner (replan, ≤2)
```

이 11노드는 README §0 의 "StateGraph 11 노드" 와 일치한다(실측 일치).

**LangGraph 미설치 폴백.** langgraph 가 없으면 같은 `AgentState` 를 받아 순차 함수 체인으로
동작한다(`graph.py:_run_with_fallback_chain`). Send 병렬·PG checkpointer·interrupt 는 빠진다.
의미: 시스템은 LangGraph 에 강하게 종속되지 않으며, 테스트는 두 모드 모두 통과해야 한다.

### 4.2 AgentState — 공유 상태와 fan-in reducer

`agents/state.py:AgentState` 는 한 turn 의 누적 상태를 담는 `TypedDict` 다.

- **필드 수(실측): 42** (`state.py` 의 `Annotated` 멤버를 `class AgentState` 부터 EOF 까지
  카운트). 입력 / 전처리 / triage·planner / 누적 / 합성 / 검증 / HITL / 메타로 분류된다.
- **드리프트 이력(정직)**: 과거 `README.md:85`(39) 와 `docs/architecture.md`(36)·구 learning_guide
  는 더 적은 수를 적었다 — S-7·외부벤치 작업 이전 스냅샷으로, 이후 `target_persons`·
  `target_company_names`·`source` 등이 추가되며 42로 늘었다. 이 정정에서 README·architecture 를
  42로 갱신해 정본을 일치시켰다(2026-06-16).

병렬 worker(Send API)가 같은 상태에 동시 기록할 때 손실·중복을 막기 위해 **필드별 reducer**가
붙는다(`state.py`):
- `_last_wins` — 입력류 필드(entry 에서만 set).
- `_list_extend` — `safety_signals`(모든 분기의 신호를 누락 없이 concat).
- `_concat_dedup_by("task_id" / "id")` — `tool_results` / `evidence_chunks`(키로 멱등 흡수,
  pre-fork 공유 항목 중복 회피 + worker 별 새 항목 누적).
- `_merge_dict_dedup` — `task_results`(replan 시 `_ClearedDict` 마커로 비우기).

### 4.3 Planner — rule vs LLM, 그리고 키워드 게이트

planner 는 질문을 task DAG 로 분해한다. 두 경로가 있다.

- **rule planner**(기본): `agents/policy.py:classify_question` 이 키워드로 question_kind 를
  정하고(`multi_hop > structural > factual > narrative > unknown` 우선순위), kind 별 결정적
  task 묶음을 생성한다.
- **LLM planner**(opt-in, `settings.agent_llm_planner` 기본 off): `agents/llm_planner.py:try_llm_plan`
  이 도구 카탈로그(화이트리스트 intent enum)를 LLM 에 주고 task DAG 를 자율 생성한다.
  생성된 task 는 (1) 화이트리스트 검증(`_validate_tasks` — 미허용 intent 드롭), (2) topological
  무결성(`topologically_valid` — 순환 시 전체 기각), (3) 예산 가드(planner hard_limit
  ≈$0.05)를 통과해야 채택된다. 실패 시 rule planner 로 폴백.

**compare_companies 키워드 게이트(중요).** 수치 랭킹 질문("매출이 가장 큰 회사")에서만
`compare_companies`(다회사 수치 비교) 힌트를 LLM 에 노출한다(`llm_planner.py` 의 `_is_ranking`).
이 게이트가 없으면 LLM 이 비랭킹 질문(GMH/GMI)까지 `compare_companies` 로 라우팅해 회귀가
난다 — cross-store gold 에서 전노출 시 main −24pp 회귀가 측정됐다(thesis external_validity §4
V5, PR #116). 게이트 적용 후 cross-store hybrid 0.000→0.786, main 무회귀.

### 4.4 Worker — 도메인 라우팅과 2단계 화이트리스트

worker 4종(`agents/workers.py`): `research_worker`(벡터), `graph_worker`(Cypher),
`sql_worker`(PG), `calculator_worker`(numexpr 샌드박스).

도구 해소는 2단계 가드를 거친다:
1. `_allowed_intents(state, kind)` — 도메인 핸들러의 intent 화이트리스트(graph/sql/research별).
2. `_resolve_tool(state, intent)` — 도메인 toolbox 모듈(`_toolbox_for`)에서 함수 해소.

도메인별 toolbox: finance = `autonexusgraph.tools`, auto = `autograph.tools`,
cross_domain = `[autograph.tools, autonexusgraph.tools]`, ip = `ipgraph.tools`.

### 4.5 fallback — graph 가 비면 벡터로 폴백

`agents/nodes.py` 의 두 함수가 핵심이다.

- `_has_usable_result(r)` — tool_result 한 건이 usable 증거인지 판정:
  status 가 `done` 이고 결과가 비어있지 않으며 error dict 가 아닐 때만 True. `failed`·`skipped`·
  `{"error": ...}` 는 **무증거**로 친다.
- `_attempt_fallback_recovery(state)` — 모든 tool_result 가 usable 하지 않고(=`all_empty`),
  아직 벡터 검색을 안 했으면, 도메인의 `fallback_search` 로 벡터 검색을 발동해 `evidence_chunks`
  를 채우고 `state["fallback_used"]=True` 로 표시.

이 메커니즘은 V7(문서-우선 gold)에서 측정상 결정적이었다. 수정 전에는 실패 task 의 error dict
가 truthy 라 `all_empty=False` 로 오인돼 폴백이 안 떴고, hybrid EM 0.154 < vector 0.308 였다.
`_has_usable_result` 도입 후(PR #114) hybrid 0.462 > vector 0.308 으로 **+15.4pp 역전**됐다
(`external_validity_protocol.md` §4 V7).

### 4.6 Synthesizer·Validator·Replan — 환각 이중 방어

- **synthesizer**(`agents/nodes.py:synthesizer_node`): tool_results + evidence_chunks 를 LLM 에
  넣어 답을 합성하되, **number_guard** 가 DB 미근거 수치를 입력 단계에서 마스킹한다.
- **validator**(`agents/validator.py`): 답변에 대해 길이·언어비율·grounding·환각수치·
  edge confidence 등 다층 검사. 답변의 큰 숫자가 tool_results/evidence 에 실재하는지 cross-check.
- **replan**: 검증 실패 시 `mark_replan` 이 tasks/results/answer 를 리셋하고 planner 를 다시
  호출한다. 무한 루프 방지 상한 `MAX_REPLANS = 2`(`validator.py`). 2회 초과 실패 시 ⚠️ prefix 를
  달고 부분 답변을 반환한다.

"사전 차단(number_guard) + 사후 검증(validator)" 이중 방어의 의미: 단일 방어는 우회될 수
있으나, 서로 다른 단계의 두 게이트를 동시에 통과해야 미근거 수치가 답에 남는다.

### 4.7 안전·비용 가드

4종 가드(`src/autonexusgraph/safety/` + `agents/number_guard.py`):
- **prompt_safety** — injection 패턴 SSOT 테이블(`safety/prompt_safety.py:_INJECTION_RULES`).
  high_risk 매칭 시 즉시 abort, 저위험은 텔레메트리(`safety_signals`)로만 기록.
- **cypher_guard** — Cypher 정적 read-only 강제(`safety/cypher_guard.py`: write 절·APOC write·
  주석 우회 차단). 자유 쓰기 쿼리 원천 차단.
- **number_guard** — 4.6절.
- **language_guard** — 답변 한국어 비율 강제(데이터 유래 고유명 제외 후 측정).

비용 가드 3-tier(`config.py:Settings`):
- 세션 hard limit `llm_session_hard_limit_usd`(기본 $5).
- 도메인별 turn budget(`turn_budget_for_domain`).
- 사전 추정 + auto-approve 임계 `llm_cost_auto_approve_usd`(기본 $0.50) — 초과 시 HITL 승인.

### 4.8 LLM Provider 추상화

ENV 한 줄로 provider 교체(`config.py`: `llm_provider`, `llm_model`). 모델 prefix 로 자동
dispatch(`gpt-*`→OpenAI, `claude-*`→Anthropic, `gemini-*`→Google, local). 역할×tier 매핑으로
노드별 모델 분리(triage=fast, planner/synthesizer=smart 등). 가격 SSOT 는 `llm/cost.py` 의
PRICING dict. 예산 초과를 던지는 `BudgetAwareLLMClient` 래퍼가 turn budget 을 강제한다.

---

## 5. 평가·측정

> 여기까지 읽으면: hybrid 의 우위를 어떻게 숫자로 증명하는지 안다.

### 5.1 어댑터와 매트릭스

비교군 어댑터(`eval/adapters/`):

| 어댑터 | 코드 | 의미 |
|---|---|---|
| `vector` | `vector_adapter.py` | 순수 벡터 RAG(`search_documents` top-k only) |
| `graph` | `graph_adapter.py` | Cypher 다홉 only |
| `hybrid` | `hybrid_adapter.py` | 제안 시스템(agent 라우팅) |
| `sql_vec` | `sql_vec_adapter.py` | SQL+Vec(그래프 제외) |
| `iter_vector` | `iter_vector_adapter.py` | 반복검색 벡터(Self-Ask/IRCoT) — 벡터의 상한 측정용 |

**축소 매트릭스 = 10 cells**(thesis §1: "10 cells × 30 finance"). 구성:
`enumerate_cells`(`eval/runners/run_matrix_smoke.py`) = 4 base 어댑터 × FAST tier ×
rerank{on,off} = 8 + hybrid 룰/LLM planner ablation × rerank{on,off} = 2.

### 5.2 메트릭과 실행

메트릭(`eval/metrics/`): multi-hop EM/F1(`em_f1.py`), hits@k(`hits_at_k.py`),
faithfulness(`faithfulness.py`), main-hop efficiency(`main_hop_efficiency.py`),
refusal, latency, cost. thesis 헤드라인은 `_thesis.py:compute_diff_pp`(hybrid−vector),
목표 임계는 `_thresholds.py:THESIS_DIFF_PP_TARGET = 30.0`.

재현 명령:
- `make audit-eval-matrix` — 시뮬레이션(LLM 비용 $0, DB/키 불필요). 셀 열거 검증.
- `make audit-eval-matrix-full` — 실측(LLM 호출, 비용 발생).
- `python -m eval.runners.run_qa_eval --gold eval/qa_gold/gold_qa_graph_multihop_v0.jsonl
  --adapters vector,graph,hybrid --run-id <id>` — 직접 실행. 산출물은
  `eval/reports/<run_id>/{manifest.json, summary.md, per_question.csv, *_predictions.jsonl}`.

---

## 6. 데이터셋·검증

> 여기까지 읽으면: 어떤 데이터가 실재하고 어떤 것이 게이트(차단)인지 안다.

### 6.1 Gold 셋 인벤토리 (실측 `wc -l`)

| 파일 | 행수 | 용도 |
|---|---|---|
| `gold_qa_graph_multihop_v0.jsonl` | **62** | thesis 주 gold(finance 57 + auto 5, 진짜 ≥2-hop) |
| `gold_qa_allganize_v0.jsonl` | 60 | 외부 큐레이터(Allganize, 단일문서 finance) |
| `gold_qa_cross_store_v0.jsonl` | 16 | V5 cross-store(graph+numeric) |
| `gold_qa_graph_multihop_docfirst_v0.jsonl` | 13 | V7 문서-우선(circularity 차단) |
| `gold_qa_graph_multihop_novel_v0.jsonl` | 12 | V4 신규 구조(sibling) |
| `gold_qa_auto_v0.jsonl` | 56 | auto 시드 |
| `gold_qa_cross_v0.jsonl` | 49 | cross-domain 시드 |
| `gold_qa_ip_v0.jsonl` | 30 | IP 시드 |
| `gold_qa_v0.jsonl` | 30 | finance 시드(L1/L2/L3) |

thesis 주 gold 는 모델 생성이 아니라 **graph 결정적 traverse**(gold_cypher)로 만든다 —
LLM-judge 순환을 피하기 위해 EM/hits 만 쓴다. 후보를 production `search_documents` 로 검색해
단일 청크가 정답을 공존시키면 기각하는 **non-vector-triviality 필터**를 적용해, 벡터가 trivial
하게 답하는 질문을 제외한다(`scripts/gold/gen_graph_multihop_gold.py`).

### 6.2 Answerability 게이트 (측정 전 선결, 측정됨)

`scripts/audit/graph_answerability.py`(`make audit-graph-answerability`)가 멀티홉 패턴의
Neo4j 경로 instantiation 수로 answerable(≥30) vs data-blocked 를 판정한다
(`data/reports/graph_answerability_*.json`, thesis §7):
- **finance ✅**: sub→parent→임원 **4189**, person→co→자회사 **2196** 경로.
- **auto ✅(단 thin)**: 제조사→리콜모델, 제조사 5곳뿐.
- **cross-domain ⊘ blocked**: bridge manufacturer↔corp **5건 < 30**.
- **auto-supplier ⊘ blocked**: `SUPPLIED_BY` **20 < 30**.

함의: graph 는 희소하지 않으며 finance 멀티홉은 충분히 답 가능하다. cross-domain 은
bridge 데이터 부족으로 게이트 상태다(8부 미해결 지점).

### 6.3 디스크 실데이터 vs 게이트 (README §1 실측)

**실재(적재됨)**:
- `anxg_fin.financials` 184K / `anxg_fin.filings` 4.6K(XBRL, 3년치).
- `anxg_vec.chunks`: finance 748,812 + auto 16,435(모두 BGE-M3 embedded). [thesis V3 는 총
  ≈778K 로 보고 — 인용 시점·집계 범위 차이]
- `anxg_auto.master_manufacturers` 22,145 / `events_recalls` 493.
- `anxg_bridge.corp_entity` 4,806(manufacturer reviewed 11 + supplier candidate 4,790 + reviewed 4).
- `anxg_ip.works`(OpenAlex) 629 / Neo4j `:Process` 410·`:ProcessStep` 550·`PERFORMED_AT` 94.

**게이트(차단·후속)**:
- IP 특허 **본문** 데이터 = 0. 코드(IPGraph)는 완료(audit-ipgraph PASS, CPC 10,695)이나 특허
  본문 적재 경로가 키-프리로 전무하다(USPTO/KIPRIS/GCP 중 키 필요, `project_ipgraph_data_blocked`).
- cross-domain bridge(5건)·auto-supplier(20건) = answerability 임계 미달.

### 6.4 외부 증인 — Allganize(단일문서 RAG)

외부 큐레이터 데이터셋 60문항(단일 문서 사실조회, graph 불요)에서 **vector F1 0.467 > hybrid
0.352, judge correctness 0.575 > 0.477**(`docs/operations/allganize_external_benchmark_report.md`,
thesis §2 인용). 이는 thesis 와 모순이 아니라 store-aware routing 의 반대 축을 실증한다 —
graph 가 필요 없는 질문은 벡터가 일관 우위. 14개 외부 PDF 를 OCR 로 적재했다(보고서 SSOT).

---

## 7. 핵심 발견과 이론적 유도 — 세미나의 심장

> 여기까지 읽으면: **왜** hybrid 가 이기는가, 그 상한과 반례를 유도로 설명할 수 있다.

### 7.1 측정 헤드라인 (정본 인용)

**판정: H1(a) CONFIRMED**(2026-06-15, S-7 ①②③ fix 후). gold = `gold_qa_graph_multihop_v0.jsonl`
(n=62 = finance 57 + auto 5). 출처: `thesis_hybrid_routing.md` §1 + `eval/reports/thesis_s7_layer2_full/manifest.json`.

| adapter | n | EM | hits@k | GMH | AUTO | GMI |
|---|---|---|---|---|---|---|
| **hybrid (S-7 ②③ fix)** | 62 | **0.710** | 0.903 | 0.824 | 1.000 | 0.625 |
| hybrid (S-7 ① only) | 62 | 0.419 | 0.581 | 0.000 | 0.000 | 0.650 |
| vector (baseline) | 62 | 0.048 | 0.532 | — | — | — |

**hybrid − vector = EM +66.2%p**(목표 +30%p 2배 초과). 패턴별 우위(thesis §1 + external_validity
§4 V6): GMH(자회사→모회사→임원) +82.4pp, AUTO(제조사→리콜모델) +100pp(5/5), GMI(인물→회사
→자회사) hybrid 0.625 vs 벡터(단발·반복) 0.000 = +62.5pp.

### 7.2 유도 — 그래프의 가치는 retrieval 이 아니라 computation

핵심 관찰: hits@k 차이(+37.1pp)보다 **EM 차이(+66.2pp)가 훨씬 크다.** 이로부터:

- 벡터는 관련 청크를 **찾기는** 한다(hits 0.532). 그러나 멀티홉 답을 **계산하지** 못한다(EM 0.048).
- hybrid 는 graph traverse 로 정확한 답을 **계산**한다(EM 0.710).
- 따라서 그래프의 기여는 검색(retrieval)이 아니라 **다홉 계산(computation)** 이다.

이것이 1.2절에서 본 cross-product 불가능성의 정량적 귀결이다. 정답이 여러 문서에 흩어진
관계의 연쇄일 때, 의미 유사도 정렬(벡터)은 원리적으로 그 연쇄를 합성할 수 없다.

### 7.3 상한과 반례 — 우위가 사라지는 경계

CONFIRMED 를 과대주장하지 않기 위해, hybrid 우위가 **사라지는** 경계를 측정으로 명시한다.

**반례 1 — 반복검색 ceiling(V6).** 벡터에 다회 검색·질의 재구성을 허용해도(`iter_vector`,
평균 2.1 라운드) GMH/GMI 는 여전히 **0.000**, ALL 0.048(단발과 동일). hybrid 는 0.710.
→ 비국소·비검색성 관계는 반복검색으로도 대체 불가(`external_validity_protocol.md` §4 V6).
단 답이 co-located·중간 hop 검색가능하면(AUTO, sibling) iter-vector 가 따라잡거나 역전한다
(novel sibling iter-vector 0.833 > hybrid 0.750). → **정밀화된 명제**: hybrid 우위는 관계가
**non-local AND 비검색성**일 때 결정적(+62~82pp)이고, 검색가능 prose 면 iter-vector 가 ceiling 에 도달.

**반례 2 — 비-모델 관계(V7).** graph 스키마에 없는 문서-공시 관계(대손충당금·배당금 수령·
용역위탁 등)를 묻는 질문에서는 graph leg 가 무력하다. fallback 수정 전 hybrid 0.154 <
vector 0.308 였다. fallback 수정 후(4.5절) hybrid 0.462 > vector 0.308 으로 역전 —
hybrid 가 graph 무력 시 clean vector 로 폴백해 **두 store 의 상한**을 취한다.

**반례 3 — 단일문서 RAG(Allganize).** graph 가 불필요한 질문은 벡터가 일관 우위
(F1 0.467 > 0.352). 이는 thesis 의 반례이자 동시에 store-aware routing 의 다른 축의 증거다.

종합하면 **단일 hybrid 가 모델 관계·비-모델 관계 양쪽에서 ≥ vector** 이며, 이것이
store-aware routing 의 실증이다.

### 7.4 외부 타당성 — 위협 5종과 판정

CONFIRMED 의 한계를 5개 위협으로 사전등록하고(`external_validity_protocol.md`, SHA `2f0cc1f`)
검증했다.

| 위협 | 검증 | 결과 | 판정 |
|---|---|---|---|
| T4 데이터 가용성 | V3 + V6 iter-vector | 출처 store 존재(778K); 단발 recall 5.8%; iter-vector ceiling GMH/GMI 0.000 | ✅ 강하게 기각 |
| T2 템플릿 artifact | V1 paraphrase | hybrid−vector +59.7pp | ✅ 기각(AUTO n=5 제외) |
| T3 EM 포맷 편향 | V2 judge 재채점 | +55.0pp | ✅ 기각(동일 family caveat) |
| T1 graph-circularity | V4 신규구조 +25pp · V7 문서우선 −15.4pp→fallback fix +15.4pp | 모델·비-모델 모두 hybrid ≥ vector | ✅ 기각(수정 후) |
| T5 소표본·단일도메인 | V5 cross-store | graph+numeric hybrid **+78.6pp**(vector·iter 0.000); 단 cross-domain 데이터 sparse | 🟡 부분(multi-store 우위 실증, 도메인 일반화 잔여) |

**V5 가 가장 직접적이다**: 인물→회사들→매출 랭킹은 graph traverse(N개 회사) + PG 매출 랭킹의
결합으로, 벡터가 원천적으로 불가능하다(vector·iter_vector 0.000, hybrid 0.786). **단 게이트 단서**:
0.786 은 `compare_companies` 랭킹-키워드 게이트가 켜졌을 때만 — 게이트 OFF 기본 hybrid 는 full
cross-store 에서 0.062 < vector 0.125. 패턴-특이적 planner 힌트 의존(일반 라우팅 흡수 잔여).

### 7.5 정직한 한계

- gold 는 여전히 graph-유래(설계상 graph-우호, non-vector-triviality 필터로 완화).
- 단일 도메인셋(finance 멀티홉 + auto 리콜), n=62. AUTO 1.000 은 5문항 소표본.
- judge 는 동일 family(gpt-4o/gpt-4o-mini) — 다-family judge 는 후속.
- H1(b) 수치 환각 감소는 메트릭으로 아직 미노출([제안], thesis §3).

---

## 8. 코드 구조 — 유지·실험을 위한 지도

> 여기까지 읽으면: 무언가를 고치거나 확장할 때 어디를 건드리는지 안다. 구조 SSOT 는
> `docs/architecture.md`.

### 8.1 패키지 토폴로지

```
src/
├─ autonexusgraph/   core — finance + 에이전트·평가·안전·DB·LLM·MCP 프레임워크
├─ autograph/        plugin — auto(차량·리콜·BoP 공정·소재) 도메인
├─ ipgraph/          plugin — ip(특허·CPC·OpenAlex) 도메인 (보조축)
└─ common/           공유 헬퍼
```

핵심 불변식: **core 는 도메인 패키지를 직접 import 하지 않는다.** 도메인이 자기 자신을
side-effect 로 등록한다(`autograph/agent_handler.py`). core 는 ENV
`AUTONEXUSGRAPH_DOMAIN_PLUGINS` 의 모듈을 soft-import 한다(`agents/_domain_handler.py`).
이 의존 방향(domain→core)이 "코어 변경량 < 5%"(README §10.12, `eval/metrics/core_diff.py`)를
가능케 하는 구조다.

### 8.2 핵심 계약·인터페이스

- **`DomainHandler` 프로토콜**(`agents/_domain_handler.py`, 6 메서드): `identify_targets`,
  `plan_tasks`, `toolbox_modules`, `allowed_intents`, `fallback_search`, `retrieve_module`.
  모두 선택적(`hasattr`/`NotImplementedError` skip) — 부분 구현이어도 core 는 finance 기본 동작.
- **Cypher 템플릿 SoT**(`tools/cypher_templates.py:TEMPLATES`): 정적 Cypher 만. 자유 쿼리 금지.
  도메인은 `register_templates` 로 자기 템플릿을 병합.
- **ToolSpec / MCP discovery**(`mcp/discovery.py:build_tool_manifest`): 함수 type hint →
  JSON Schema 자동 변환. 사용자가 스키마를 안 쓴다.
- **AgentState**(4.2절): 노드 간 계약. 새 노드를 더하면 어느 키를 읽고 쓰는지 문서화해야 한다.

### 8.3 확장점 — "새 X 는 어디에 꽂나"

| 추가하려는 것 | 꽂는 위치 |
|---|---|
| 새 도구(intent) | 도메인 `tools/*.py` 에 함수 추가 + `allowed_intents` 화이트리스트 등록 |
| 새 Cypher 패턴 | `cypher_templates.py:TEMPLATES`(또는 도메인 `register_templates`) |
| 새 도메인 | 새 패키지 + `agent_handler.py`(DomainHandler 6메서드) + `ontology/<domain>/*.yaml` + ENV 등록 |
| 새 평가 어댑터 | `eval/adapters/<name>_adapter.py` + `get_adapter` 등록 |
| 새 안전 가드 | `safety/<guard>.py` + triage/validator 훅 |

### 8.4 MCP 도구 노출 — 카운트 드리프트(정직)

`mcp/discovery.py:build_tool_manifest(domain)` 가 도메인별 typed 도구를 MCP 로 노출한다.

- **라이브 카운트(실측)**: finance 21 + auto 40 + ip 19 = **80**(`build_tool_manifest` 길이).
- **정본 카운트(README/PKG-INFO)**: **59**(finance 21 + auto 38), 2026-06-04 PASS 시점.

차이의 원인: 정본 59 는 IP 도메인이 배선되기 **전** 스냅샷이고, 이후 auto 가 38→40,
ip 19 가 추가되며 80 으로 늘었다. `make audit-mcp` 가 SDK 설치 시 `ListToolsRequest` 핸들러
round-trip 으로 라이브 수를 재측정한다. 정본 문서 갱신은 후속.

### 8.5 namespace 격리 규약

공유 DB 에서 본 프로젝트 데이터만 분리한다(`project_db_namespace_isolation`).
- PG: DSN database + 스키마 `anxg_<schema>`(`config.pg_schema`).
- Neo4j: `NEO4J_DATABASE`(Enterprise) + 노드 라벨 `Anxg_<Label>`(`config.neo4j_label`).
  **관계 타입은 접두하지 않는다** — 라벨만으로 노드 소속이 확정되고 관계는 양 끝 노드에 종속.
- 모든 Neo4j 세션은 `db/neo4j.py:get_session()` 단일 진입점을 거친다(누락 시 "보이지 않는
  노드" 버그). Community Edition 은 named DB 가 없어 라벨 접두가 유일한 격리 수단이다.
- 마이그레이션: `scripts/migrate/relabel_neo4j_namespace.py` + `rename_pg_schemas_namespace.sql`
  (둘 다 멱등). 함정: PG 스키마 접두는 정적 SQL 문자열에 박혀 `eval`(패키지)·`reg`(변수) 같은
  동음이의 토큰과 충돌 위험 → 실재 `schema.table` 화이트리스트로만 치환.

---

## 9. 운영 — 설치·실행·온보딩

> 여기까지 읽으면: 시스템을 처음 띄우고, 새 도메인을 붙이는 절차를 안다. 상세는
> `docs/quickstart.md` 와 `docs/operations/*.md`.

### 9.1 의존성 없는 최소 실행 경로 (키·DB 불필요)

다음은 외부 LLM 키·DB 없이 도는 검증 경로다(`Makefile`):
- `make audit-eval-matrix` — 평가 매트릭스 셀 열거 시뮬레이션($0).
- `make audit-mcp` — MCP 도구 discovery(SDK 미설치 시 SKIPPED + discovery 검증).
- `make audit-dod` — DoD 체크리스트(트래픽 라이트 리포트).

### 9.2 풀 스택

1. 설정: `.env`(`config.py:get_settings` 가 Pydantic Settings 로 로드). 키: `DART_API_KEY`,
   `OPENAI/ANTHROPIC/GOOGLE_API_KEY`, `NEO4J_PASSWORD`, `POSTGRES_DSN`,
   `AUTONEXUSGRAPH_DOMAIN_PLUGINS="autograph,ipgraph"`.
2. 적재: `make ingest-*`(raw 다운로드) → `make load-*`(PG/Neo4j 적재) →
   `make build-chunks-* && make embed-chunks`(벡터).
3. 서비스: `make serve-api`(FastAPI :8000) / `make serve-ui`(Streamlit) /
   `python -m autonexusgraph.mcp`(MCP stdio).
4. 한 줄 호출:
   ```python
   from autonexusgraph.agents import run_agent
   print(run_agent("삼성전자 2023년 매출은?", domain="finance")["answer"])
   ```

### 9.3 새 도메인 온보딩 (IPGraph 가 살아있는 레퍼런스)

`src/ipgraph/` 가 plug-in 메커니즘의 실증 사례다. 절차:
1. 새 패키지 `src/<domain>graph/` 생성.
2. `agent_handler.py` 에 `DomainHandler` 6메서드 구현 + `register_handler`/`register_router`.
3. `ontology/<domain>/{entities,relations}.yaml` 작성(Pydantic strict 검증).
4. `tools/*.py`(patents/graph/retrieve/bridge 류) + `allowed_intents` 화이트리스트.
5. bridge: 기존 `anxg_bridge.corp_entity` 변경 없이 신규 join 테이블 추가
   (IP 는 `anxg_ip.assignee_corp_map`) — core/bridge 스키마 변경 0.
6. ENV `AUTONEXUSGRAPH_DOMAIN_PLUGINS` 에 모듈명 추가.
7. 검증: `make audit-<domain>` + `make audit-dod` 로 core_diff < 5% 재측정(DoD #15).

---

## 10. 메타 검토 — 흔한 혼동과 미해결 지점

> 여기까지 읽으면: 입문자가 반복해 막히는 지점과, 연구로 더 파야 할 지점을 구분할 수 있다.

### 10.1 흔한 혼동 (현상 / 원인 / 푸는 법 / 위치)

| 혼동 | 원인 | 푸는 법 | 위치 |
|---|---|---|---|
| "MCP 도구가 59개다" | 정본 README 59 는 IP 배선 전 스냅샷 | 라이브는 80 — `make audit-mcp` 실측 | 8.4절 |
| "AgentState 39/36 필드" | 과거 README(39)·architecture(36) 가 S-7 이전 스냅샷 | 라이브 **42** — `state.py` 카운트(README·architecture 정정 완료) | 4.2절 |
| "vector > hybrid = 아키텍처 실패" | 1차 측정(2026-06-10)은 doc-RAG gold + 엔티티 해소 결함 | graph 어댑터 61/62 거부(`no_company_identified`)였음 — 능력 부재 아닌 식별 결함, S-7 fix 후 역전 | thesis §1 |
| "graph EM 0.000 = 그래프가 무능" | agent 가 그래프를 안 씀(엔티티 미식별) | 도구 직접 체인은 정답(김명균→가온전선→자회사) | thesis §1 S-7 진단 |
| "learning_guide 와 LEARNING 이 둘 다 있다" | LEARNING 이 learning_guide 를 흡수 | learning_guide 는 삭제, 본 문서가 단일 통독본 | 머리말 |
| "Allganize 에서 vector 가 이겨 thesis 반증" | 단일문서 RAG 는 graph 불요 | store-aware routing 의 반대 축 실증(반례 아님) | 6.4·7.3절 |

### 10.2 미해결 지점 (상태 / 처방 / 위치)

| 지점 | 현 상태 | 처방 | 위치 |
|---|---|---|---|
| cross-domain bridge sparse | manufacturer↔corp 5건 < 30(blocked) | bridge 보강(qid/LEI/business_no 매칭 확대) | 6.2·6.3 |
| 도메인 일반화 | finance 멀티홉 단일 도메인셋, n=62 | 타 산업·대규모 gold(데이터 sparse) | 7.5 |
| H1(b) 수치 환각 메트릭 | [제안], 미노출 | number_guard 위반율을 turn metric 으로 노출 | thesis §3 |
| IP 특허 본문 데이터 | 코드 완료, 데이터 0(키 게이트) | USPTO/KIPRIS/GCP 키 발급 | 6.3 |
| 비-모델 관계 graph 흡수 | V7 가 노출(대손충당금·관계기업 등) | document-disclosed 관계를 graph edge 로 흡수(P1) | 7.3 |
| 다-family judge | 동일 family(gpt-4o) caveat | 이종 family judge 재채점 | 7.5 |

---

## 11. 부록

### A. 목적별 진입 경로

- **시스템을 처음 본다** → 1부(한 예시) → 2부 → 7부(왜 이기는가).
- **코드를 고치러 왔다** → 8부(구조·확장점) → `docs/architecture.md`.
- **측정을 재현한다** → 5부(재현 명령) → `eval/runners/run_qa_eval.py` → `eval/reports/*`.
- **연구 주장을 검증한다** → 7부 → `docs/research/thesis_hybrid_routing.md` §1·§7 +
  `external_validity_protocol.md`.
- **새 도메인을 붙인다** → 9.3절 → `src/ipgraph/`(레퍼런스).

### B. FAQ (요지만; 상세 근거는 본문 절 참조)

- **Q. 벡터만으로 같은 걸 못 하나?** 멀티홉(cross-product)·cross-domain(bridge)·정확 수치는
  구조적으로 불가. 7.2절 유도.
- **Q. LangGraph 가 필수인가?** 아니다. 미설치 시 순차 함수 체인으로 동작(4.1절).
- **Q. 재무 수치 환각은?** number_guard(사전 마스킹) + validator(사후 cross-check) 이중 방어(4.6절).
- **Q. provider 종속성은?** ENV 한 줄로 OpenAI/Anthropic/Google/local 교체(4.8절).
- **Q. 도메인 추가 시 코어 변경량은?** < 5%(`core_diff.py`, DoD #15). domain→core 단방향 의존.

### C. 코드 읽는 순서

1. `agents/graph.py`(`_build_langgraph_app`) — 11노드 와이어링.
2. `agents/state.py`(`AgentState`) — 노드 간 계약과 reducer.
3. `agents/nodes.py`(triage/planner/synthesizer) + `agents/workers.py`(worker 4종).
4. `agents/llm_planner.py`(`try_llm_plan`) + `agents/validator.py`(검증·replan).
5. `tools/{financials,graph,retrieve}.py` + `tools/cypher_templates.py`.
6. `eval/adapters/*` + `eval/runners/run_qa_eval.py` — 측정.

### D. 문서 지도

| 문서 | 역할 |
|---|---|
| **본 문서 `LEARNING.md`** | 통독 세미나 교재(단일 통독본) |
| `docs/architecture.md` | 구조 SSOT(패키지·노드·SSOT 색인) |
| `docs/mental_model.md` | 결정 카탈로그([확정]/[잠정]/[미정]·트레이드오프·열린 질문) |
| `docs/research/thesis_hybrid_routing.md` | thesis SSOT(측정·재판정 프로토콜) |
| `docs/research/external_validity_protocol.md` | 외부 타당성 V1~V7 |
| `README.md` | 통합 SSOT v3.0(현황·도구·DoD·로드맵·Quickstart) |
| `docs/autograph.md` · `process_graph.md` · `ipgraph.md` | 도메인 상세 SSOT |
| `docs/operations/*.md` | 운영 런북(Docker·데이터·KCGS·Allganize 벤치) |

### E. 연구 계보 (미적용·참고)

본 시스템이 채택/미채택한 관련 연구는 흐름을 끊으므로 여기 모은다(상세는 구 learning_guide
§11, git 히스토리).
- **GraphRAG 패턴**: Microsoft GraphRAG / LightRAG / HippoRAG — 본 시스템은 store-aware
  routing + schema-governed KGC 로 차별화(자동 ontology induction 은 비목표, thesis §6).
- **임베딩**: BGE-M3(1024d, 한국어) 채택. Qwen3-Embedding / e5-mistral 은 참고.
- **리랭킹**: BGE-Reranker-v2-m3 채택.
- **Confidence calibration**: Platt scaling(`scripts/audit/calibrate_confidence.py` 류) — 연속
  스칼라 confidence 를 쓰는 이유.
- **MCP**: 2026 상호운용 표준(Claude/OpenAI Agents SDK 양쪽 채택) — typed 도구 풀 위 얇은 서버.
- **LLM-as-judge**: `eval/metrics/llm_judge.py`. 자기충족 위험 회피 위해 thesis 주 gold 는
  judge 미사용(EM/hits 만).

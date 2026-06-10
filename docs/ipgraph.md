# IPGraph — 특허·기술혁신 도메인 (보조축 — corp_entity 브리지 전용) · 설계 + 구현 SSOT

> **위계 (README §0):** ip 는 **보조축** — finance/auto 와 같은 본체/대칭 도메인이 아니라, `bridge.corp_entity` + `ip.assignee_corp_map` 으로 **수평 cross 진입 어댑터** 역할. 풀 도메인 어댑터(코드/온톨로지/도구/Cypher 25)는 완료 — "보조"는 데이터 약화가 아니라 **architectural role** (corp_entity 브리지 전용 진입).
>
> 전체 시스템 구조 (3 패키지 토폴로지 · plug-in 등록 메커니즘 · SSOT 색인) 는
> [docs/architecture.md](./architecture.md) 가 SSOT. 본 문서는 **ip 도메인 단독 가이드**.
>
> AutoNexusGraph 3번째 도메인 어댑터. 기존 `autograph` 와 동일 plug-in 패턴
> (`register_handler` 부작용 + `register_router` + `ontology/<domain>/*.yaml` + typed tool pool + `ip_*` Cypher 템플릿 + gold QA seed)
> 으로 추가하여 **§10.12 "코어 변경 < 5%"** 를 보존 (실측 현재 default baseline `414bc1b` 기준 코어 변경 **0/15,396 LOC = 0.00%**, `make audit-dod` 2026-06-01. 누적 reset 이력은 [eval/reports/core_diff_baseline_ledger.md](../eval/reports/core_diff_baseline_ledger.md)).
>
> **현재 구현 상태 (2026-06-01)**
> - **코드**: `src/ipgraph/` 전체 구현 완료. `agent_handler.py` + `policy.py` (route_domain_ip) + `ontology.py` + `cypher_templates_ip.py` (**25 Cypher 템플릿**, `cypher_templates_ip.py:36` dict top-level) + `tools/{bridge,graph,patents,retrieve}.py` (4-tools 미러) + `loaders/{load_cpc,load_openalex}.py` + `ingestion/{cpc_scheme,kipris,uspto_odp,openalex}.py`. `make audit-ipgraph` PASS. wire-up 검증 5종: **handler + router + ontology + 25 Cypher templates + gold (ip 30 + cross_ip 8)**. 별개로 `IPGraphHandler.allowed_intents` whitelist 는 graph 8 + sql 8 (research/sql + bridge 2 + cross_query_ip) + research 3 = **19 intents** (`agent_handler.py:26-42`).
> - **데이터**: 부분 적재 — `ip.cpc_scheme` **10,695 row** + `ip.works` (OpenAlex) **629 row** + `ip.institution` 38 + `ip.work_institution` 638 + Neo4j `:CPCCode` **10,695 노드**. PG 스키마 마이그레이션 (18_ipgraph.sql + 19_ipgraph_bridge.sql) **적용 완료 (2026-06-01)** — `ip.patents / ip.assignees / ip.inventors / ip.patent_assignees / ip.patent_inventors / ip.patent_cpc / ip.citations / ip.assignee_corp_map` 8 테이블 생성됨 (row=0). 후속: KIPRIS_API_KEY 발급 + USPTO ODP bulk dataset → `ingestion/{kipris,uspto_odp}.py` 실행 + assignee → corp_entity 매핑.
>
> **선택 근거:** OpenAlex / **USPTO ODP (data.uspto.gov, PatentsView 후속 — 2026-03-20 이관 완료, REST 종료 → bulk dataset)** / CPC bulk 완전 무료, KIPRIS 로 한국 특허 커버, 거의 전부 정형이라 LLM 예산 거의 무소비.
> CPC 분류는 정식 계층 온톨로지. assignee → 기업 매핑이 cross-domain 진입점.

---

## 0. 통합 위치 (README 반영 지점)

| 위치 | 변경 |
|---|---|
| README 머리말 | 3도메인(finance·auto·ipgraph) 서사 |
| README §1 | `### IPGraph 도메인` 블록 — CPC scheme + OpenAlex works 적재됨 (10,695 + 629), 나머지는 (예정) |
| README §4 | IPGraph 데이터 소스 표 (특허만). 배터리·소재는 **auto** 로 (M-14) |
| README §5 | IPGraph tools outline |
| README §11.1 | Phase C = ip (현 단계 보조축) |
| ENV | `AUTONEXUSGRAPH_DOMAIN_PLUGINS=autograph,ipgraph` |
| PG init | `18_ipgraph.sql` + `19_ipgraph_bridge.sql` (E-1) |

---

## 1. DomainHandler — 실 Protocol 1:1 미러 (M-1)

> SSOT = `src/autonexusgraph/agents/_domain_handler.py:44-81`. `src/autograph/agent_handler.py` 를 1:1 미러링.

```python
# src/ipgraph/agent_handler.py
from autonexusgraph.agents._domain_handler import register_handler

class IPGraphHandler:
    domain = "ip"                                    # 속성

    def identify_targets(self, state, *, question):  # assignee/corp_code/CPC 코드를 state 에 채움
        ...
    def plan_tasks(self, state, *, question):        # IP-L1~L3 + CD task DAG
        ...
    def toolbox_modules(self):                       # -> [ipgraph.tools]
        ...
    def allowed_intents(self, kind):                 # -> set[str]: IP_GRAPH_ALLOWED / IP_SQL_ALLOWED / IP_RESEARCH_INTENTS
        ...
    def fallback_search(self, ...):                  # -> ("search_patents", search_patents, kwargs) | None
        ...
    def retrieve_module(self):                       # -> ipgraph.tools.retrieve
        ...

register_handler(IPGraphHandler())                   # src/ipgraph/__init__.py 의 `from . import agent_handler` 부작용 등록
```

**6 메서드 책임** (Protocol SSOT `_domain_handler.py:44-80`):

| 메서드 | 책임 | 호출 노드 | 반환 |
|---|---|---|---|
| `identify_targets` | 질문 텍스트에서 entity 추출 (assignee 이름 / corp_code / CPC `_CPC_PATTERN`) → state 에 채움 | triage | None (state 부수 효과) |
| `plan_tasks` | 질문 유형별 task DAG 생성 (IP-L1 단순 카운트 / IP-L2 multi-hop CPC + citation / IP-L3 cross-domain assignee↔corp) | planner | None (state["tasks"] 채움) |
| `toolbox_modules` | 도구 함수 풀 모듈 리스트 | supervisor → workers (_toolbox_for) | `[ipgraph.tools]` (`ipgraph/tools/__init__.py` re-export) |
| `allowed_intents(kind)` | kind 별 화이트리스트 — graph/sql/research | workers (_resolve_tool 직전) | `IP_GRAPH_ALLOWED` 8 / `IP_SQL_ALLOWED` 8 / `IP_RESEARCH_INTENTS` 3 |
| `fallback_search(state, query)` | tool 미매칭 또는 빈결과 시 fallback (`search_patents` 일반 검색) | executor/worker_research | `("search_patents", fn, kwargs)` 또는 `None` |
| `retrieve_module` | retrieve 함수 보유 모듈 (vector 검색) | research_worker | `ipgraph.tools.retrieve` |

### 라우팅 — 별도 register_router (M-2)

`detect()` 는 핸들러 메서드가 아니다. autograph 처럼 라우터를 따로 등록.

```python
# src/ipgraph/policy.py
from autonexusgraph.agents._domain_handler import register_router

def route_domain_ip(question: str, hint: str | None) -> str | None:
    # 키워드: 특허, patent, 출원, 발명, 등록특허, CPC, IPC, 인용, 기술분야, R&D, 포트폴리오
    ...

register_router(route_domain_ip)
```

---

## 2. 온톨로지 (`ontology/ip/`) — autograph yaml 컨벤션 정합

### `entities.yaml`

```yaml
schema_version: 1
nodes:
  Patent:
    key: pub_no
    props: [app_no, title, abstract, filing_date, grant_date, kind, jurisdiction]
  Assignee:
    key: assignee_id
    props: [name, name_norm, country, type]       # type: company|individual|university|gov
  Inventor:
    key: inventor_id
    props: [name, name_norm, country]             # (M-8) master.persons 와 분리 유지
  CPCCode:
    key: code
    props: [level, title]                         # (M-6) level: section|class|subclass|maingroup|subgroup
  TechField:
    key: field_id
    props: [label]
  Work:                   # OpenAlex 논문
    key: openalex_id
    props: [title, publication_year, cited_by_count, doi, type]
  Institution:            # 연구기관 — corp_entity 브리지 (기업 R&D)
    key: ror_id
    props: [name, country, type]                  # type: company|education|government
  # 엣지: (Assignee)-[:AFFILIATED_WITH]->(Institution), (Work)-[:AUTHORED_AT]->(Institution)
  # cross: institution(company) → bridge.corp_entity → 특허(assignee) → 재무(R&D비)
```

### `relations.yaml`

```yaml
schema_version: 1
edges:
  ASSIGNED_TO:    {from: Patent,   to: Assignee, grade: A, source: kipris|uspto_odp}
  INVENTED:       {from: Inventor, to: Patent,   grade: A, source: kipris|uspto_odp}
  CLASSIFIED_AS:  {from: Patent,   to: CPCCode,  grade: A, source: cpc_scheme}
  CITES:          {from: Patent,   to: Patent,   grade: A, source: uspto_odp}
  SUBCLASS_OF:    {from: CPCCode,  to: CPCCode,  grade: A, source: cpc_scheme}   # (M-6) 다단계 트리 depth≥4
  enabled_false:
    SIMILAR_TECH:  {from: Patent, to: Patent, grade: C, note: "임베딩 유사 — ablation 후"}
```

모든 엣지 7키 의무 (auto 와 동일). **(M-9) `snapshot_year` = `filing_year` 기본**, `grant_year` 는 prop. Cross-domain "2023년 출원" = filing_year, "2023년 등록" = 별도 표현.

---

## 3. 적재 등급

| 노드·엣지 | 출처 | grade | 비고 |
|---|---|:--:|---|
| Patent / Assignee / Inventor | KIPRIS · USPTO ODP | A (0.95) | 공식 특허청 (USPTO ODP = PatentsView 후속). 현재 row 0 — KIPRIS_API_KEY 발급 + USPTO ODP bulk 적재 대기 |
| CLASSIFIED_AS / SUBCLASS_OF | CPC scheme bulk | A (0.95) | 정식 분류 계층. **CPC scheme 적재 완료 (10,695 row + Neo4j `:CPCCode` 10,695 + `SUBCLASS_OF` 10,686 — 7-key 100%)** |
| CITES | USPTO ODP citations (PatentsView 후속) | A (0.95) | 인용 네트워크. 현재 row 0 — USPTO ODP 적재 대기 |
| Assignee → corp_entity (via `ip.assignee_corp_map`) | name/QID/business_no 매칭 | A/B | strong → mapped, weak → candidate. 현재 row 0 — assignee 적재 후 |
| **Work / Institution / AUTHORED_AT / IS_ENTITY (OpenAlex)** | OpenAlex API | A (0.95) | **적재 완료 — 629 / 38 / 638 / 38**. abstract 423건 → `vec.chunks` (BGE-M3 backfill 대상). KR 38 corp_code 매칭 (현대차/모비스/기아/만도/LG/네이버/효성/금호석유/한미약품/Hyundai Steel …) × 상위 인용 work 20씩 × 2020~ |
| AFFILIATED_WITH (Assignee→Institution) | OpenAlex link | A/B | Assignee 적재 후 cross-domain 활성 |
| SIMILAR_TECH | pgvector 유사 | C | `enabled:false` — ablation 후 활성 검토 |

---

## 4. 에이전트 도구 (`src/ipgraph/tools/*`) — autograph 4-tools 미러

### `tools/patents.py` (PG)
- `lookup_patent(query, limit)` (`patents.py:19`) / `get_patent_info(pub_no)` (`:47`)
- `list_patents_by_assignee(assignee_id, year_range, cpc, limit=50)` (`:80`)
- `count_patents_by_field(assignee_id, cpc_section, year_range)` (`:128`)
- `compare_assignees_patent_volume(assignee_ids, year, cpc)` (`:162`)

### `tools/graph.py` (Neo4j — `ip_*` 템플릿)
- `lookup_assignee_graph(query, limit=10)` (`graph.py:55`) / `list_patents_of_assignee(assignee_id, snapshot_year, limit=50)` (`:60`)
- `get_inventors_of_patent(pub_no, limit=50)` (`:69`) / `find_co_assignees(assignee_id, limit=20)` (`:73`)
- `list_patents_in_cpc(cpc_code, include_subclasses=True)` (`:80`) / `list_assignees_in_field(cpc_code, top_k=20)` (`:87`)
- `get_citation_network(pub_no, depth=1, limit_nodes=300, max_total=1000, direction='both')` (`:94`) — **(M-7) cap 강제** (`cited_by|cites|both`)
- `most_cited_patents(assignee_or_cpc, top_k=10)` (`:125`)

### `tools/retrieve.py`
- `search_patents(query, top_k=8, assignee_id=…, cpc=…, jurisdiction=…)` (`retrieve.py:55`) — abstract+claims pgvector + 메타
- `search_by_metadata_ip(...)` / `get_chunk_ip(chunk_id)`

### `tools/bridge.py` (corp_entity 재사용)
- `bridge_assignee_to_corp(assignee_id)` (`bridge.py:21`) / `bridge_corp_to_assignee(corp_code)` (`:56`)
- `cross_query_ip(corp_code, ...)` (`:95`) — 특허 ↔ finance(R&D비) ↔ auto(부품·리콜)

### Bridge 구현 — `ip.assignee_corp_map` join 테이블 (M-3)

`bridge.corp_entity` **컬럼·데이터 직접 변경 없음.** 별도 join 테이블 추가 → core/bridge 스키마 변경 0 → §10.12 보존.

```sql
-- 19_ipgraph_bridge.sql  (E-1)
CREATE TABLE ip.assignee_corp_map (
    assignee_id      VARCHAR NOT NULL,
    corp_code        VARCHAR NOT NULL,
    match_type       VARCHAR NOT NULL,   -- qid | business_no | lei | name
    confidence_score NUMERIC NOT NULL,
    reviewed_status  VARCHAR DEFAULT 'auto',   -- auto | reviewed | rejected
    schema_version   VARCHAR,
    created_at       TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (assignee_id, corp_code)
);
```

기존 supplier candidate 4,792 row 운영 SOP (검토 승급/거부) 와 **동일 흐름 재사용**.

### Cypher 템플릿 — 25 (M-11)

`naming = ip_*`. lookup / assignee / cpc / citation / cross 카테고리 (실측 25 top-level keys, `cypher_templates_ip.py:36`).
예: `ip_lookup_patent`, `ip_assignee_patents_by_cpc`, `ip_cpc_descendants(code, max_depth=4)` (M-6), `ip_citation_network_d1` / `ip_citation_network_d2` (M-7).
`src/ipgraph/tools/__init__.py:23` 의 `register_templates(_FIN_TEMPLATES, _IP_TEMPLATES)` 가 import 시점에 IP_TEMPLATES 를 finance `TEMPLATES` 에 병합 (autograph `__init__` 은 AUTO 만 등록 — 도메인별 독립 호출).

---

## 5. 데이터 소스 (특허만 — M-14)

> 배터리·소재 표는 **여기 없음**. auto 의 L5/L6 확장이므로 [docs/autograph.md](./autograph.md) §2.5.4 로 이식.

| 데이터 | 출처 | 라이선스 (M-5) | 인증 | 적재 위치 | 상태 |
|---|---|---|---|---|---|
| 한국 특허·출원 | KIPRIS Open API (공공데이터포털) | 검색·서지 무료 / **본문·대량은 KIPRISPLUS 회원·일부 비공개** | `KIPRIS_API_KEY` | `ip.patents` | (예정) — 키 발급 + `ingestion/kipris.py` 실행 |
| 미국 특허·인용·assignee 정규화 | **USPTO Open Data Portal (data.uspto.gov)** — PatentsView 후속 | 공공 (US Gov) | **(M-4) 이관 완료 (2026-03-20)** — `search.patentsview.org` REST 종료 (410 Gone), **ODP bulk dataset + Transition Guide** 채택. REST 가정 코드 모두 폐기 | `ip.patents` + `ip.citations` | (예정) — `ingestion/uspto_odp.py` 구현됨, bulk 데이터셋 적재 대기 |
| CPC 분류 체계 | CPC scheme bulk (USPTO/EPO) | 공공 | 불필요 | `ip.cpc_scheme` | **적재 완료 — 10,695 row + Neo4j `:CPCCode` 10,695 노드** (`loaders/load_cpc.py`) |
| 글로벌 논문·연구 (institution/author 링크) | OpenAlex API | CC0 | **무료 키 (하루 10만 크레딧, 2025-02 이후 필수)** | `ip.works` | **적재 완료 — 629 row** (`loaders/load_openalex.py`). 특허×논문 cross 승격은 institution↔corp_entity 매핑 후 |

`src/autonexusgraph/ingestion/_license.py` 에 KIPRIS 정책 게이트 추가 (최근 commit `b70527a` IR/뉴스룸 license-gate 패턴 재사용).

### 볼륨 추정 (M-10)
- US 특허 (USPTO ODP, PatentsView 후속): Hyundai/Kia 합 ~5K/년, Samsung Group ~10K/년, LG Group ~7K/년, SK Group ~4K/년. KR 출원은 1.5~2배.
- 5 OEM + 5 배터리社 × 2020~2024 = 수십만 row. embedding 대상 = abstract+claims (full text 아님) → BGE-M3 GPU 수 시간.

---

## 6. gold QA seed (E-2)

`eval/qa_gold/gold_qa_ip_v0.jsonl` (**30 row**, IP-L1/L2/L3 각 10) — `gold_qa_auto_v0.jsonl` 스키마 베이스.
`eval/qa_gold/gold_qa_cross_v0.jsonl` (**49 row** 실측) — qid prefix 기준 CD-L1 10 / CD-L2 8 / CD-L3 11 / CD-L4 7 + **IP 결합 8** (`CD-L3-IP` 4 + `CD-L4-IP` 4) + **CD-PROC 5** (공정 결합).

| 레벨 | 예시 | 도구 경로 |
|---|---|---|
| IP-L1 | "삼성전자 2023년 출원 특허 수?" | count_patents_by_field |
| IP-L2 | "현대차 자율주행(CPC G05D) 특허 중 최다 인용?" | list_patents_in_cpc + most_cited_patents |
| IP-L3 | "LG엔솔 특허를 인용한 출원인 중 코스피 상장사?" | get_citation_network + bridge_assignee_to_corp |
| CD-L3 | "현대모비스 R&D비(finance) 대비 ADAS(CPC B60W) 출원 추세(ip)" | cross_query_ip + get_operating_income |
| CD-L4 | "삼성SDI 배터리 특허(H01M) 집중 분야 + 영업이익 + 그 셀 쓰는 OEM 리콜" | bridge_assignee_to_corp → list_patents_in_cpc → get_revenue → list_recalls_affecting |
| CD-L4+ | "삼성SDI 배터리 특허(H01M) + 같은 분야 논문 피인용 + 영업이익" | list_patents_in_cpc + OpenAlex works + get_operating_income |

---

## 7. 라우팅 / 비용 / 평가

- **라우팅:** `route_domain_ip` 등록 (M-2). corp + 특허 + (부품|리콜) 동시 → `cross_domain`.
- **비용 (M-12):** `turn_budget_for_domain("ip")` 기본 **$0.20** — `agent_turn_budget_ip_usd` 필드 기본 0.0 → 공통 기본 `agent_turn_budget_usd=0.20` 상속 (`config.py`, `turn_budget_for_domain` 우선순위 1단계). ip 한도 override 는 `.env` `AGENT_TURN_BUDGET_IP_USD` (Settings 필드 경유). 정형 위주라 실제 소비도 낮음.
- **평가 (M-13):** 4 어댑터 × 저비용 LLM 1종 (Sonnet 4.6 / GPT-4o-mini / Gemini Flash). headline = thesis(§10.7) 만, judge 는 cheap tier. seed ip 30 + CD-L3 4 + CD-L4 4. rerank on/off ablation 1줄.
- **DoD:** 추가 후 `make audit-dod` 코어 변경량 재측정. **(M-15) baseline reset 정책을 README §10.12 본문으로 승격** — `make audit-dod` 출력에 baseline commit + 누적 reset 이력.

---

## 8. 작업 순서 (솔로 · 수 주)

1. ✅ CPC scheme bulk → CPCCode/SUBCLASS_OF (무인증, 온톨로지 골격) — `ip.cpc_scheme` 10,695 row + Neo4j `:CPCCode` 10,695 노드 적재 완료 (`loaders/load_cpc.py`)
2. → **USPTO ODP bulk dataset** 채택 (M-4 — PatentsView REST 종료, ODP + Transition Guide) → US 특허 + 인용 → assignee→corp strong 매칭. **`ingestion/uspto_odp.py` (collect 7종) + `loaders/load_uspto_odp.py` (PG 7-table upsert + Neo4j `:Patent`/`:Assignee`/`:Inventor` 노드 + `ASSIGNED_TO`/`INVENTED`/`CLASSIFIED_AS`/`CITES` 엣지, 7-key edge meta 100%) 구현 완료 (2026-06-02 smoke E2E PASS — 합성 데이터 4 patents/3 assignees/2 inventors/4 link/2 citations 적재 + 멱등 재실행 OK + 7키 무결성 100% + 정리)** — bulk dataset 다운로드 (data.uspto.gov/bulkdata/datasets) 후 `raw/ip/uspto_odp/*.jsonl` 7 파일 배치 → `make load-uspto-odp` 1회로 적재. 18_ipgraph.sql + 19_ipgraph_bridge.sql 마이그레이션 **적용 완료** — `ip` 스키마 12 테이블 (`patents / assignees / inventors / patent_assignees / patent_inventors / patent_cpc / citations / cpc_scheme / assignee_corp_map / institution / work_institution / works`). 데이터 row 는 cpc_scheme=10,695 + works=629 + institution=38 + work_institution=638; 나머지 8 테이블 row=0 (USPTO ODP bulk 데이터 / KIPRIS API 키 대기).
3. → KIPRIS 키 발급 → 한국 특허 (현대차/기아/삼성SDI/LG엔솔/현대모비스 우선) — `ingestion/kipris.py` **XML 파서 완성 (2026-06-02, lxml/stdlib fallback)** + `loaders/load_kipris.py` 신규 (USPTO 헬퍼 source-pluggable 재사용 — `source_type='kipris'`, `jurisdiction='KR'`, `source_prefix='kipris'`). smoke E2E PASS — 합성 XML 2 patents/3 assignees/3 inventors/3 ASSIGNED_TO/3 INVENTED + 7-key edge meta 100% 검증 후 cleanup. `KIPRIS_API_KEY` 발급 → `make load-kipris`. **CPC IPC 매칭 시 PG patent_cpc FK 통과시키려면 `make load-cpc -- --include-subgroups` 먼저** (기본 적재는 subgroup 제외 — KIPRIS IPC 는 통상 subgroup 정밀도 `H01M10/052`).
4. ✅ `ip_*` Cypher 템플릿 + tool pool + 화이트리스트 — `cypher_templates_ip.py` **25 templates** + `tools/{patents,graph,retrieve,bridge}.py` 4-tools + `IPGraphHandler.allowed_intents` 화이트리스트 완료
5. ⚠️ gold seed + CD-L3/L4 → 축소 매트릭스 — `gold_qa_ip_v0.jsonl` 30 row + `gold_qa_cross_v0.jsonl` 의 CD-IP 8 row 시드 완료. 매트릭스 LLM 실측은 (예정)
6. → (옵션) OpenAlex `ip.works` **적재 완료 — 629 row** (`loaders/load_openalex.py`). 배터리·소재 L5/L6 — [docs/autograph.md](./autograph.md) §2.5.4 (auto.master_minerals 5 row 시드만)

---

## 9. 배터리·소재 분리 노트 (M-14)

배터리 셀 chem / 핵심광물 / 광물 수입통계는 **ip 도메인 아님** — auto 의 BOM 하향(L5/L6) 확장.
설계·데이터 소스는 [docs/autograph.md](./autograph.md) §2.5.4 BOM 계층 확장 부록. 회사단위 셀↔OEM 소싱은 공개 sparse → grade C candidate 정직 표기.

---

## 부록 A — 재사용 기존 자산

- `src/autograph/agent_handler.py` — 핸들러 1:1 미러 베이스
- `src/autonexusgraph/agents/_domain_handler.py:44-81` — Protocol SSOT / `:111-150` — `discover_plugins()`
- `src/autograph/policy.py::route_domain` — router 패턴
- `src/autograph/cypher_templates_auto.py` — 명명·검증 패턴
- `src/autograph/tools/{spec,graph,retrieve,bridge}.py` — 4-tools 구조
- `eval/metrics/core_diff.py:38-178` — baseline 정책 + reset
- `ontology/auto/*.yaml` 8종 — ontology/ip 구조 베이스

## 부록 B — 적용하면 좋을 최신 기술 `(미적용, 참고)`

특허·기술혁신 도메인 KG 의 최신 연구. 향후 IPGraph 데이터 적재 (KIPRIS / USPTO ODP) 후 단계적 도입 검토.

- **Patent2Vec / PatentBERT** — 특허 abstract+claims 의 도메인 특화 임베딩. ([Lee et al, "PatentBERT", arXiv:1906.02124](https://arxiv.org/abs/1906.02124)) Patent classification (CPC 자동 할당) + similarity search 정확도 향상. **적용**: 현재 BGE-M3 위에 patent-specific instruction fine-tune. **기대효과**: assignee 분류·유사 특허 검색 정확도↑. **비용**: GPU fine-tune 12GB+ (4B 모델).
- **Citation Graph embeddings** — node2vec / GraphSAGE 로 인용 네트워크 임베딩. ([Han et al, "Heterogeneous Citation Network Embedding", arXiv:2005.06104](https://arxiv.org/abs/2005.06104)) PageRank 대비 multi-modal (cite + author + CPC) 결합. **적용**: `gds.beta.node2vec` (Neo4j GDS) 또는 별도 PyG. **기대효과**: "기술 영향력" 순위 + 유사 특허 클러스터링. **비용**: 적재 후 Neo4j GDS 라이선스 확인 필요.
- **Knowledge-aware patent retrieval** ([Krestel et al, "A Survey on Deep Learning for Patent Analysis", arXiv:2104.13860](https://arxiv.org/abs/2104.13860)) — 특허 본문 + CPC 계층 + citation 결합 retrieval. RAG 형태로 prior art 검색 자동화.
- **LLM 기반 특허 검색·요약 (PaECTER, ChatGPT-Patent)** — Patent claim parsing + 청구항 분해 + 검색. **본 시스템 적용**: synthesizer prompt 에 "특허 claim 인용 시 출처 + claim 번호 명시" 강제 (number_guard 의 patent_no 화이트리스트 확장).
- **assignee disambiguation** — 동일 회사의 다양한 표기 (예: "Hyundai Motor Co.", "현대자동차주식회사", "HYUNDAI MOTOR COMPANY") 매칭. ([Kim & Yoon, "Author name disambiguation in scientific data", 2015](https://doi.org/10.1108/AJIM-05-2014-0061)) → 본 시스템의 `ip.assignee_corp_map` strong/medium/weak 정책의 baseline.

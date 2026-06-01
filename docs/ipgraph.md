# IPGraph — 특허·기술혁신 도메인 (도메인3) · 설계 + 구현 SSOT

> 전체 시스템 구조 (3 패키지 토폴로지 · plug-in 등록 메커니즘 · SSOT 색인) 는
> [docs/architecture.md](./architecture.md) 가 SSOT. 본 문서는 **ip 도메인 단독 가이드**.
>
> AutoNexusGraph 3번째 도메인 어댑터. 기존 `autograph` 와 동일 plug-in 패턴
> (`register_handler` 부작용 + `register_router` + `ontology/<domain>/*.yaml` + typed tool pool + `ip_*` Cypher 템플릿 + gold QA seed)
> 으로 추가하여 **PRD §10.12 "코어 변경 < 5%"** 를 보존 (실측 baseline `bab9411` 기준 코어 변경 0 LOC = 0.00%, `make audit-dod` 2026-06-01).
>
> **현재 구현 상태 (2026-06-01, working tree, uncommitted)**
> - **코드**: `src/ipgraph/` 전체 구현 완료. `agent_handler.py` + `policy.py` (route_domain_ip) + `ontology.py` + `cypher_templates_ip.py` (25 templates) + `tools/{bridge,graph,patents,retrieve}.py` (4-tools 미러) + `loaders/{load_cpc,load_openalex}.py` + `ingestion/{cpc_scheme,kipris,uspto_odp,openalex}.py`. `make audit-ipgraph` PASS (handler+router+ontology+25 cypher+gold ip=30/cross_ip=8).
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
| README §10.1 | Phase C = ip (현 단계) |
| ENV | `AUTONEXUSGRAPH_DOMAIN_PLUGINS=autograph,ipgraph` |
| PG init | `18_ipgraph.sql` + `19_ipgraph_bridge.sql` (E-1) |

---

## 1. DomainHandler — 실 Protocol 1:1 미러 (M-1)

> 이전 design 의 6 메서드(detect/tools/cypher_templates/ontology_path/turn_budget_usd/bridge_resolver) 는 실제 Protocol 과 **0% 일치**였다.
> SSOT = `src/autonexusgraph/agents/_domain_handler.py:44-81`. `src/autograph/agent_handler.py` (167 LOC) 를 1:1 미러링.

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
| Patent / Assignee / Inventor | KIPRIS · USPTO ODP | A (0.95) | 공식 특허청 (USPTO ODP = PatentsView 후속) |
| CLASSIFIED_AS / SUBCLASS_OF | CPC scheme bulk | A (0.95) | 정식 분류 계층 |
| CITES | USPTO ODP citations (PatentsView 후속) | A (0.95) | 인용 네트워크 |
| Assignee → corp_entity | name/QID/business_no 매칭 | A/B | strong → mapped, weak → candidate |
| SIMILAR_TECH | pgvector 유사 | C | `enabled:false` |

---

## 4. 에이전트 도구 (`src/ipgraph/tools/*`) — autograph 4-tools 미러

### `tools/patents.py` (PG)
- `lookup_patent(query, limit)` / `get_patent_info(pub_no)`
- `list_patents_by_assignee(assignee_or_corp, year_range=None, cpc=None, limit=50)`
- `count_patents_by_field(assignee_or_corp, cpc_section, year_range=None)`
- `compare_assignees_patent_volume(assignees, year, cpc=None)`

### `tools/graph.py` (Neo4j — `ip_*` 템플릿)
- `lookup_assignee_graph(query)` / `list_patents_of_assignee(assignee, snapshot_year=None)`
- `get_inventors_of_patent(pub_no)` / `find_co_assignees(assignee)`
- `list_patents_in_cpc(cpc_code, include_subclasses=True)` / `list_assignees_in_field(cpc_code, top_k=20)`
- `get_citation_network(pub_no, depth=2, limit_nodes=300, max_total=1000, direction='both')` — **(M-7) cap 강제** (`cited_by|cites|both`)
- `most_cited_patents(assignee_or_cpc, top_k=10)`

### `tools/retrieve.py`
- `search_patents(query, top_k=8, assignee_id=…, cpc=…, jurisdiction=…)` — abstract+claims pgvector + 메타
- `search_by_metadata_ip(...)` / `get_chunk_ip(chunk_id)`

### `tools/bridge.py` (corp_entity 재사용)
- `bridge_assignee_to_corp(assignee_id)` / `bridge_corp_to_assignee(corp_code)`
- `cross_query_ip(...)` — 특허 ↔ finance(R&D비) ↔ auto(부품·리콜)

### Bridge 구현 — 신규 join 테이블 (M-3)

`bridge.corp_entity` **컬럼·데이터 직접 변경 없음.** 신규 join 테이블 추가 → core/bridge 스키마 변경 0 → §10.12 보존.

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

### Cypher 템플릿 목표 ~25 (M-11)

`naming = ip_*`. lookup 5 + assignee 6 + cpc 6 + citation 4 + cross 4.
예: `ip_lookup_patent`, `ip_assignee_patents_by_cpc`, `ip_cpc_descendants(code, max_depth=4)` (M-6), `ip_citation_network_d1` / `ip_citation_network_d2` (M-7).
`src/autograph/tools/__init__.py:20-22` 의 `register_templates(_FIN_TEMPLATES, _AUTO_TEMPLATES)` 에 `_IP_TEMPLATES` 추가.

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

`eval/qa_gold/gold_qa_ip_v0.jsonl` (신규) — `gold_qa_auto_v0.jsonl` 스키마 베이스.
`eval/qa_gold/gold_qa_cross_v0.jsonl` 에 CD-L3/L4 추가 (30 → 38 row).

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
- **비용 (M-12):** `turn_budget_for_domain("ip")` 기본 **$0.05** (finance $0.50 / auto $0.30 의 1/10 — 정형 위주). ENV `LLM_TURN_BUDGET_IP_USD` override.
- **평가 (M-13):** 4 어댑터 × 저비용 LLM 1종 (Sonnet 4.6 / GPT-4o-mini / Gemini Flash). headline = thesis(§10.7) 만, judge 는 cheap tier. seed ip 30 + CD-L3 4 + CD-L4 4. rerank on/off ablation 1줄.
- **DoD:** 추가 후 `make audit-dod` 코어 변경량 재측정. **(M-15) baseline reset 정책을 README §10.12 본문으로 승격** — `make audit-dod` 출력에 baseline commit + 누적 reset 이력.

---

## 8. 작업 순서 (솔로 · 수 주)

1. ✅ CPC scheme bulk → CPCCode/SUBCLASS_OF (무인증, 온톨로지 골격) — `ip.cpc_scheme` 10,695 row + Neo4j `:CPCCode` 10,695 노드 적재 완료 (`loaders/load_cpc.py`)
2. → **USPTO ODP bulk dataset** 채택 (M-4 — PatentsView REST 종료, ODP + Transition Guide) → US 특허 + 인용 → assignee→corp strong 매칭. **`ingestion/uspto_odp.py` 구현됨, bulk dataset 적재 대기** (PG 스키마 마이그레이션 18_ipgraph.sql 부분 미적용 — `ip.patents` 테이블만 존재, `ip.assignees / ip.citations / ip.patent_assignees / ip.patent_cpc` 7 테이블 부재)
3. → KIPRIS 키 발급 → 한국 특허 (현대차/기아/삼성SDI/LG엔솔/현대모비스 우선) — `ingestion/kipris.py` 구현됨, 키 대기
4. ✅ `ip_*` Cypher 템플릿 + tool pool + 화이트리스트 — `cypher_templates_ip.py` 25 templates + `tools/{patents,graph,retrieve,bridge}.py` 4-tools + `IPGraphHandler.allowed_intents` 화이트리스트 완료
5. ⚠️ gold seed + CD-L3/L4 → 축소 매트릭스 — `gold_qa_ip_v0.jsonl` 30 row + `gold_qa_cross_v0.jsonl` 의 CD-IP 8 row 시드 완료. 매트릭스 LLM 실측은 (예정)
6. → (옵션) OpenAlex `ip.works` **적재 완료 — 629 row** (`loaders/load_openalex.py`). 배터리·소재 L5/L6 — [docs/autograph.md](./autograph.md) §2.5.4 (auto.master_minerals 5 row 시드만)

---

## 9. 배터리·소재 분리 노트 (M-14)

배터리 셀 chem / 핵심광물 / 광물 수입통계는 **ip 도메인 아님** — auto 의 BOM 하향(L5/L6) 확장.
설계·데이터 소스는 [docs/autograph.md](./autograph.md) §2.5.4 BOM 계층 확장 부록. 회사단위 셀↔OEM 소싱은 공개 sparse → grade C candidate 정직 표기.

---

## 부록: 재사용 기존 자산

- `src/autograph/agent_handler.py` (167 LOC) — 핸들러 1:1 미러 베이스
- `src/autonexusgraph/agents/_domain_handler.py:44-81` — Protocol SSOT / `:108-148` — `discover_plugins()`
- `src/autograph/policy.py::route_domain` — router 패턴 (detect 흡수처)
- `src/autograph/cypher_templates_auto.py` (457 LOC) — 명명·검증 패턴
- `src/autograph/tools/{spec,graph,retrieve,bridge}.py` (835 LOC) — 4-tools 구조
- `eval/metrics/core_diff.py:38-178` — baseline 정책 + reset 박을 곳
- `ontology/auto/*.yaml` 8종 — ontology/ip 구조 베이스

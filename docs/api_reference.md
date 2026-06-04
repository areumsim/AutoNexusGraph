# API Reference — 도메인별 tool 시그니처·반환 스키마 통합 SSOT

> **본 문서의 위치**: agent worker 가 호출하는 사전 정의 도구 (Tool Pool) 의 시그니처·반환 스키마 통합 카탈로그. **자유 SQL/Cypher/벡터 호출은 금지** — LLM 은 함수명 + 파라미터만 결정. 본 문서가 SSOT.
>
> §4.4 = finance 시나리오 5개 (operations/rag_tools.md 흡수, stub). §4.5 Auto / §4.6 IP 단일 도메인 시나리오.
>
> 코드 SSOT (정합 우선순위 — 본 문서 ↔ 코드 충돌 시 코드가 SSOT):
> - core (finance): `src/autonexusgraph/tools/{financials,graph,retrieve}.py` + `cypher_templates.py`
> - auto: `src/autograph/tools/{spec,graph,retrieve,bridge}.py` + `cypher_templates_auto.py`
> - ip: `src/ipgraph/tools/{patents,graph,retrieve,bridge}.py` + `cypher_templates_ip.py`

---

## 0. 공통 규약

### 0.1 반환 형식

모든 도구는 `list[dict]` 또는 단일 `dict` 반환. dict 키는 도구별 정의. 빈 결과 = `[]`. 예외는 코드 raise.

### 0.2 안전 가드 (worker 단계에서 자동 적용)

- **화이트리스트 강제** — worker 가 도메인별 `allowed_intents` (`auto`: 31 / `ip`: 19 / `finance`: 21 인텐트) 검증 후 호출. 외부 인텐트는 차단. (코드 SSOT: `workers.py:30-41` / `autograph/agent_handler.py:42-65` / `ipgraph/agent_handler.py:26-42`.)
- **cypher_guard** — 모든 그래프 호출은 `assert_read_only` 경유 (`safety/cypher_guard.py:68`). 쓰기 키워드 + 위험 CALL 차단.
- **param_schema 검증** — Cypher 템플릿은 `type/range/regex/enum/bool reject` (`tools/cypher_templates.py:422 _validate_param`).
- **`reviewed_status='rejected'` 자동 제외** — bridge / graph 호출 모두.
- **number_guard** — synthesizer 단계에서 답변의 비-화이트리스트 큰 숫자 마스킹.

### 0.3 도메인 라우팅

`_init_state` → `auto_detect_domain(question)` → 등록 라우터 (`route_domain_auto` / `route_domain_ip`) 순차 평가 → 첫 match → 핸들러의 `toolbox_modules()` 반환 목록이 worker 의 도구 풀.

---

## 1. Finance 도메인 (`src/autonexusgraph/tools/`)

### 1.1 `tools/financials.py` — PG 정형

| 함수 | 시그니처 | 반환 |
|---|---|---|
| `lookup_company(query, limit=10)` | `query: str` (이름/종목코드/corp_code), `limit: int` | `list[dict]` — `corp_code, name, stock_code, wikidata_qid, wikipedia_title_ko` |
| `get_company_info(corp_code)` | `corp_code: str` | `dict` — 기업 기본 정보 (industry, market, listed_date 등) |
| `get_revenue(corp_code, year)` | `corp_code: str, year: int` | `dict` — `revenue_won, fiscal_year, currency, source_rcept_no` |
| `get_operating_income(corp_code, year)` | `corp_code: str, year: int` | `dict` — `operating_income_won, fiscal_year, currency` |
| `get_balance_sheet_item(corp_code, year, item)` | `item: str` (예: '총자산', '부채총계') | `dict` — `value_won, fiscal_year` |
| `compare_companies(corp_codes, year, metric)` | `corp_codes: list[str]`, `metric: str` | `list[dict]` — `[{corp_code, name, metric_value}, ...]` |
| `list_companies_by_market(market)` | `market: str` ('KOSPI' / 'KOSDAQ' / 'KOSPI200' 등) | `list[dict]` |

### 1.2 `tools/graph.py` — Neo4j 그래프 탐색

Cypher 템플릿 14개 경유 (`cypher_templates.py::TEMPLATES` top-level dict — `find_paths` / `get_subgraph` 등 정적 정의. 동적 hop variants 는 함수 내부 처리).

| 함수 | 시그니처 | 반환 |
|---|---|---|
| `lookup_company(query, limit=10)` | `query: str` | `list[dict]` — Wikidata QID / Wikipedia title 포함 |
| `lookup_person(name, birth_year=None)` | `name: str`, `birth_year: int \| None` | `list[dict]` — 동명이인 안전 매칭 |
| `list_subsidiaries(parent_corp_code, include_related=False, snapshot_year=None)` | `parent_corp_code: str`, `include_related: bool`, `snapshot_year: int \| None` | `list[dict]` — `child_name, child_corp_code, ownership_pct, valid_from/to` |
| `list_parents(corp_code_or_name)` | `corp_code_or_name: str` | `list[dict]` — 모회사 추적 |
| `get_executives(corp_code, role_contains=None, snapshot_year=None)` | `role_contains: str \| None` (substring) | `list[dict]` — `person_name, role, snapshot_year` |
| `get_companies_of_person(name, birth_year=None, role_contains=None)` | | `list[dict]` — 인물 → 임원직 회사 매트릭스 |
| `get_major_shareholders(corp_code, min_pct=0.0, snapshot_year=None)` | `min_pct: float` (0.0~100.0) | `list[dict]` — `shareholder_name, ownership_pct` |
| `find_paths(start_corp_code, end_corp_code, max_hops=3)` | `max_hops: int` (1~5) | `list[dict]` — 두 회사 최단 경로 |
| `get_subgraph(corp_code, depth=1, limit_nodes=50)` | `depth: int` (1~3), `limit_nodes: int` | `dict` — `nodes, edges` |
| `list_mentioning_news(corp_code)` | | `list[dict]` — 뉴스 멘션 |
| `list_cooccurring(corp_code)` | | `list[dict]` — CO_MENTIONED_WITH |
| `list_group_members(group_name)` | `group_name: str` (기업집단명) | `list[dict]` |

### 1.3 `tools/retrieve.py` — Hybrid 검색

| 함수 | 시그니처 | 반환 |
|---|---|---|
| `search_documents(query, top_k=8, corp_code=None, fiscal_year=None, source=None, section_contains=None, rerank=False)` | `query: str`, `top_k: int`, 메타 필터 옵션, `rerank: bool` (DoD #17 (d) 매트릭스 변수) | `list[dict]` — `chunk_id, text, score, corp_code, fiscal_year, source, section` |
| `search_by_metadata(corp_code=None, fiscal_year=None, source=None)` | 임베딩 무관, 결정적 fetch | `list[dict]` |
| `get_chunk(chunk_id)` | `chunk_id: str` | `dict` — 단일 청크 + 메타 |

---

## 2. Auto 도메인 (`src/autograph/tools/`)

도메인 `auto` / `cross_domain` 모드에서만 활성. `AutoHandler.allowed_intents` 화이트리스트로 강제.

### 2.1 `tools/spec.py` — PG SQL (자동차 제원)

| 함수 | 시그니처 | 반환 |
|---|---|---|
| `lookup_vehicle(query, limit=10)` | `query: str` (모델명/VIN/manufacturer) | `list[dict]` — `manufacturer_id, model_id, variant_id, make, model_year` |
| `get_vehicle_info(variant_id)` | | `dict` — 차량 상세 (BOM 계층 L0~L2 포함) |
| `get_spec(variant_id, metric=None)` | `metric: str \| None` (출력/연비/배출 등) | `dict` — `auto.spec_measurements` 의 NHTSA NCAP / EPA / Canadian Specs |
| `compare_vehicles(variant_ids, metric)` | `variant_ids: list[int]`, `metric: str` | `list[dict]` |
| `get_safety_rating(variant_id, agency='NCAP_US')` | `agency: str` (`NCAP_US` / `KNCAP` / `EURO_NCAP` / `IIHS`) | `dict` |
| `get_oem_financials_sec(sec_cik, year)` | `sec_cik: str` (글로벌 OEM), `year: int` | `dict` — SEC EDGAR XBRL facts |

### 2.2 `tools/graph.py` — Neo4j (Cypher 템플릿 `auto_*`)

`AUTO_TEMPLATES` 23개 (`cypher_templates_auto.py:25` dict top-level keys).

| 함수 | 시그니처 | 반환 |
|---|---|---|
| `lookup_vehicle_graph(query)` | `query: str` | `list[dict]` |
| `lookup_supplier(query)` | `query: str` (supplier 이름/QID) | `list[dict]` |
| `list_components(model_id, level=None, max_depth=4, min_confidence=0.7, snapshot_year=None)` | `level: int \| None` (L3/L4/L5), `min_confidence: float` | `list[dict]` — BOM 트리 |
| `list_systems_of_model(model_id)` | | `list[dict]` — L3 System (POWERTRAIN/BRAKE/ADAS 등) |
| `list_models_with_system(system_code)` | `system_code: str` (SCREAMING_SNAKE) | `list[dict]` |
| `list_recalls_affecting(variant_id, year_range=None)` | `year_range: tuple[int,int] \| None` | `list[dict]` — `:Recall` AFFECTED_BY |
| `list_investigations_affecting(variant_id)` | | `list[dict]` — NHTSA ODI PE/EA/DP |
| `get_investigation_recall_chain(investigation_id)` | | `dict` — 조사 → 리콜 전파 chain |
| `get_suppliers_of_component(component_id, snapshot_year=None, min_confidence=0.7)` | | `list[dict]` — `SUPPLIED_BY` |
| `get_vehicles_using_component(component_id)` | | `list[dict]` — Cross-Domain 의 핵심 진입점 |
| `find_vehicle_component_paths(variant_id, supplier_id, max_hops=3)` | | `list[dict]` — 경로 |
| `get_plant_capacity(plant_code, year=None)` | DART 사업보고서 적재 | `list[dict]` |
| `get_oem_production(manufacturer_id, year)` | | `list[dict]` |
| `list_plants_by_oem(manufacturer_id)` | | `list[dict]` |
| `get_macro_production(year)` | KAMA 매크로 | `dict` |
| `get_macro_industry(year_month)` | `year_month: str` ('2024-12') | `dict` |
| `search_processes(query)` | 산단공 합성 공정 사전 | `list[dict]` |

### 2.3 `tools/retrieve.py` — pgvector (auto 메타)

| 함수 | 시그니처 | 반환 |
|---|---|---|
| `search_documents_auto(query, top_k=8, manufacturer_id=None, model_id=None, variant_id=None, source=None, rerank=False)` | `source: str \| None` (`nhtsa_recall` / `nhtsa_complaint` / `nhtsa_tsb` / `wikipedia_auto` / `aihub` / `epa` / `datagokr`) | `list[dict]` |
| `search_by_metadata_auto(manufacturer_id=None, model_id=None, variant_id=None, source=None)` | | `list[dict]` |
| `get_chunk_auto(chunk_id)` | | `dict` |

### 2.4 `tools/bridge.py` — Cross-Domain (`bridge.corp_entity` 기반)

| 함수 | 시그니처 | 반환 |
|---|---|---|
| `bridge_corp_to_entity(corp_code, *, entity_type=None, min_confidence=0.0, include_candidate=True)` | `corp_code: str`, `entity_type: str \| None` ('manufacturer'/'supplier'/'vehicle_model'/'variant'), `min_confidence: float`, `include_candidate: bool` (False → reviewed 만) | `list[dict]` — `entity_id, entity_type, name, wikidata_qid, match_method, confidence_score, reviewed_status, valid_from/to`. `reviewed_status='rejected'` 자동 제외. |
| `bridge_entity_to_corp(entity_id, entity_type, *, include_candidate=True)` | `entity_type` **필수** | `list[dict]` |
| `bridge_sec_cik_to_entity(sec_cik, *, entity_type='manufacturer')` | `sec_cik: str` (10자리 자동 zfill) | `list[dict]` — 글로벌 OEM (Tesla/Ford/GM/Stellantis) 진입점 |
| `bridge_entity_to_sec_cik(entity_id, entity_type='manufacturer')` | | `list[dict]` |
| `cross_query(...)` | finance↔auto join helper | `list[dict]` |

---

## 3. IP 도메인 (`src/ipgraph/tools/`)

도메인 `ip` / `cross_domain` 모드에서만 활성. `IPGraphHandler.allowed_intents` 화이트리스트 19 인텐트 (graph 8 + sql 8 + research 3).

### 3.1 `tools/patents.py` — PG 정형

| 함수 | 시그니처 | 반환 |
|---|---|---|
| `lookup_patent(query, limit=10)` | `query: str` (pub_no / app_no / title) | `list[dict]` — `pub_no, app_no, title, jurisdiction, source` |
| `get_patent_info(pub_no)` | `pub_no: str` | `dict` — abstract, filing_date, grant_date, kind 등 |
| `list_patents_by_assignee(assignee_or_corp, year_range=None, cpc=None, limit=50)` | `assignee_or_corp: str` (assignee_id 또는 corp_code), `cpc: str \| None` (CPC 코드 prefix) | `list[dict]` |
| `count_patents_by_field(assignee_or_corp, cpc_section, year_range=None)` | `cpc_section: str` (예: 'B60W', 'H01M') | `dict` — `count, year_range, top_assignees` |
| `compare_assignees_patent_volume(assignees, year, cpc=None)` | `assignees: list[str]`, `year: int` | `list[dict]` |

### 3.2 `tools/graph.py` — Neo4j (Cypher 템플릿 `ip_*`)

`IP_TEMPLATES` 23개 (`cypher_templates_ip.py:30` dict top-level keys).

| 함수 | 시그니처 | 반환 |
|---|---|---|
| `lookup_assignee_graph(query)` | `query: str` | `list[dict]` |
| `list_patents_of_assignee(assignee_id, snapshot_year=None)` | | `list[dict]` |
| `get_inventors_of_patent(pub_no)` | | `list[dict]` |
| `find_co_assignees(assignee_id)` | | `list[dict]` — 공동 출원인 |
| `list_patents_in_cpc(cpc_code, include_subclasses=True)` | `cpc_code: str` (예: 'B60W30'), `include_subclasses: bool` | `list[dict]` |
| `list_assignees_in_field(cpc_code, top_k=20)` | | `list[dict]` |
| `get_citation_network(pub_no, depth=2, limit_nodes=300, max_total=1000, direction='both')` | `depth: int` (1~2 강제), `limit_nodes: int` (≤300), `max_total: int` (≤1000), `direction: 'cited_by' \| 'cites' \| 'both'` | `dict` — `nodes, edges, depth_reached` |
| `most_cited_patents(assignee_or_cpc, top_k=10)` | | `list[dict]` |

### 3.3 `tools/retrieve.py` — pgvector (ip 메타)

| 함수 | 시그니처 | 반환 |
|---|---|---|
| `search_patents(query, top_k=8, assignee_id=None, cpc=None, jurisdiction=None, rerank=False)` | `cpc: str \| None`, `jurisdiction: str \| None` ('US' / 'KR') | `list[dict]` — abstract+claims pgvector |
| `search_by_metadata_ip(assignee_id=None, cpc=None, jurisdiction=None)` | | `list[dict]` |
| `get_chunk_ip(chunk_id)` | | `dict` |

### 3.4 `tools/bridge.py` — IP ↔ Corp (신규 join `ip.assignee_corp_map`)

| 함수 | 시그니처 | 반환 |
|---|---|---|
| `bridge_assignee_to_corp(assignee_id)` | | `list[dict]` — `corp_code, match_type, confidence_score, reviewed_status` |
| `bridge_corp_to_assignee(corp_code)` | | `list[dict]` |
| `cross_query_ip(...)` | 특허 ↔ finance(R&D비) ↔ auto(부품·리콜) | `list[dict]` |

> `bridge.corp_entity` 컬럼·데이터 **직접 변경 없음**. supplier candidate 운영 SOP 재사용.

---

## 4. Cross-Domain 호출 패턴 (예시)

### 4.1 CD-L1 — 제조사 직접 Bridge

```python
# 질의: "현대차가 제조한 모델의 리콜 건수와 현대차 영업이익을 같이 보여줘"
entities = bridge_corp_to_entity("00164742", entity_type="manufacturer")
manufacturer_id = entities[0]["entity_id"]
recalls = list_recalls_affecting(manufacturer_id)
revenue = get_operating_income("00164742", year=2024)
```

### 4.2 CD-L3 — 부품·공급사 ↔ OEM ↔ 재무

```python
# 질의: "LG에너지솔루션 배터리를 쓰는 차종을 가진 OEM 의 최근 영업이익은?"
supplier_entities = bridge_corp_to_entity("00373220", entity_type="supplier")  # LG엔솔
supplier_id = supplier_entities[0]["entity_id"]
vehicles = get_vehicles_using_component(supplier_id)  # component_id 가 supplier 인 경우의 변형
# 각 vehicle 의 manufacturer 식별 → corp_code 역매핑 → 영업이익 조회
for v in vehicles:
    corps = bridge_entity_to_corp(v["manufacturer_id"], entity_type="manufacturer")
    if corps:
        income = get_operating_income(corps[0]["corp_code"], year=2024)
```

### 4.3 CD-L4-IP — 3 도메인 동시 (특허 + 재무 + 자동차 리콜)

```python
# 질의: "삼성SDI 배터리 특허(H01M) 집중 분야 + 영업이익 + 그 셀을 쓰는 OEM 리콜"
patents = list_patents_in_cpc("H01M", include_subclasses=True)  # ip 도메인
assignee_corps = bridge_assignee_to_corp("samsungsdi_assignee_id")
samsungsdi_corp = assignee_corps[0]["corp_code"]
revenue = get_operating_income(samsungsdi_corp, year=2024)  # finance
samsungsdi_supplier = bridge_corp_to_entity(samsungsdi_corp, entity_type="supplier")
vehicles = get_vehicles_using_component(samsungsdi_supplier[0]["entity_id"])  # auto
for v in vehicles:
    recalls = list_recalls_affecting(v["variant_id"])
```

### 4.4 Finance 단일 도메인 시나리오 (`operations/rag_tools.md` 흡수)

#### A. "삼성전자 2024년 위험요인 요약"

```python
chunks = search_documents(
    "주요 사업 위험요인",
    corp_code="00126380",
    fiscal_year=2024,
    section_contains="위험",
    report_type="annual_business",
    top_k=5,
)
# → 5 chunk text 를 LLM 프롬프트로 주입 → 요약
```

#### B. "삼성전자 자회사 중 ESG 등급 A+ 인 곳"

```python
subs = list_subsidiaries("00126380", limit=200)
for s in subs:
    if not s.get("child_corp_code"):
        continue
    # ESG 는 별도 SQL 조회 (PG esg.ratings — 본 시스템 적재 시점에)
    # 예시: psql SELECT * FROM esg.ratings WHERE corp_code=... AND grade IN ('A+','A')
```

#### C. "이재용이 임원인 회사의 영업이익 합"

```python
from autonexusgraph.tools.financials import get_operating_income
companies = get_companies_of_person("이재용")
# 동명이인이 있으면 triage 가 자동 HITL clarification interrupt 발동
# (agents/interrupts.py — is_ambiguous_company 판정)
total = 0
for c in companies:
    if not c.get("corp_code"):
        continue
    r = get_operating_income(c["corp_code"], 2024)
    if r:
        total += r["value"]
```

#### D. "삼성전자 vs SK하이닉스 연결 경로"

```python
paths = find_paths("00126380", "00164779", max_hops=3)
# → [{"node_path": [...], "rel_types": [...], "hops": 2}]
# multi-hop 그래프 traversal — Vector RAG 로는 불가능
```

#### E. "삼성전자 자회사 중 최근 부정 뉴스 많은 회사"

```python
subs = list_subsidiaries("00126380")
for s in subs:
    if not s.get("child_corp_code"):
        continue
    news = list_mentioning_news(s["child_corp_code"], limit=20)
    # 감성 추출은 P3 (selective LLM) — 현재 wired-but-disabled
    # 향후: news[i]['sentiment'] 활용 (배포 후)
```

### 4.5 Auto 단일 도메인 시나리오

#### A. "쏘나타 1.6T 하이브리드 출력은?"

```python
from autograph.tools.spec import lookup_vehicle, get_spec
candidates = lookup_vehicle("쏘나타 1.6T 하이브리드", limit=5)
# triage 단계 — 여러 trim 매칭되면 HITL clarification interrupt (agents/interrupts.py)
v = candidates[0]
specs = get_spec(v["variant_id"], measure_key="engine_power_ps")
# → [{"measure_key": "engine_power_ps", "value": 180, "unit": "ps"}]
```

#### B. "현대 그랜저 vs 기아 K8 제원 비교"

```python
from autograph.tools.spec import lookup_vehicle, compare_vehicles
g = lookup_vehicle("현대 그랜저 2024", limit=1)[0]
k = lookup_vehicle("기아 K8 2024", limit=1)[0]
diff = compare_vehicles(
    variant_ids=[g["variant_id"], k["variant_id"]],
    measure_keys=["engine_power_ps", "fuel_economy_combined"],
)
# → row 별 측정값 + 단위 + 차이
```

#### C. "쏘나타가 사용한 부품 중 외부 supplier 가 있는 부품의 리콜"

```python
from autograph.tools.graph import (
    lookup_vehicle, list_components, get_suppliers_of_component,
    list_recalls_affecting,
)
# 차량 → 부품 → 공급사 + 차량 → 리콜. 부품-공급사 cross-hop 시연.
v = lookup_vehicle("쏘나타 1.6T", limit=1)[0]
comps = list_components(variant_id=v["variant_id"], limit=10)
# list_components 반환: component_id / kind / name / system_code / confidence / ...

hit = []
for c in comps:
    sups = get_suppliers_of_component(c["component_id"], limit=5)
    if not sups:
        continue   # 공급사 미매핑 부품은 skip (SUPPLIED_BY 30 edges 한계)
    recs = list_recalls_affecting(variant_id=v["variant_id"])    # kwargs-only
    hit.append({
        "component_id": c["component_id"],
        "supplier":     sups[0]["name"],
        "recall_count": len(recs),
    })
# Vector RAG 만으로는 (부품, 공급사, 리콜) 동시 매칭 불가.
```

> NOTE: "OEM corp_code → 차종 직접 enumerate" 단축 도구 (`list_vehicles_by_oem` 류) 는 아직 typed tool 로 wired 안 됨. `(Manufacturer)-[:MANUFACTURES]->(VehicleVariant)` 그래프 모델은 존재하지만 raw Cypher 직접 또는 `list_models_with_system` 우회 사용. 본 시나리오는 단축 도구 의존 없이 multi-hop 시연.

#### D. "현대차 울산 공장의 생산능력 + 가동률 추이 (2020~2024)"

```python
from autograph.tools.spec import get_plant_capacity, list_plants_by_oem
# (1) 생산능력 — typed tool wired
plants = list_plants_by_oem("00164742")
ulsan = next((p for p in plants if "울산" in (p.get("plant_region") or "")), None)
if ulsan:
    capa = get_plant_capacity("00164742",
                                plant_code=ulsan["plant_code"], year=2024)
    # → [{"capacity_units": ..., "unit": ..., "snapshot_year": ..., ...}]

# (2) 가동률 — `auto.plant_utilization` 53 row 적재됨 (dart_production_parser:316 SoT).
#     단 typed tool 함수 미등록 — agent 가 자유 SQL 호출 금지 (PRD 정책).
#     본 시나리오는 미래의 `get_plant_utilization` tool 추가 후 1줄 호출이 목표.
```

> **(미구현 — backlog)** `autograph/tools/spec.py` 에 `get_plant_utilization(corp_code, plant_code=None, year=None)` 추가 + intent 화이트리스트 등록 + `auto_*` cypher template 또는 `query_dicts` 래퍼. 적재된 53 row 의 활용 단축 도구 부재 — 현재는 agent 가 직접 호출 못함 (PRD "자유 SQL 금지" 정책상).

#### E. "EV 시장 점유율 — KOSIS 산업통계 기준"

```python
from autograph.tools.spec import get_macro_industry, get_macro_production
industry = get_macro_industry(year=2024, sector="motor_vehicles")
prod = get_macro_production(year=2024)
# 거시지표 (KOSIS 204 monthly + 21 yearly rows) — finance 의 ECOS 와 cross-ref 가능
```

### 4.6 IP 단일 도메인 시나리오

#### A. "삼성SDI 의 H01M (배터리) CPC 분야 특허 수"

```python
from ipgraph.tools.graph import list_assignees_in_field, list_patents_in_cpc
top = list_assignees_in_field("H01M", top_k=20)
# → [{"assignee_id": ..., "name": "Samsung SDI Co., Ltd.", "n_patents": ...}]
samsungsdi = next(t for t in top if "samsung sdi" in t["name"].lower())
print(samsungsdi["n_patents"])
```

#### B. "현대차 (KR1020...XXX) 의 인용 네트워크 1-hop"

```python
from ipgraph.tools.graph import get_citation_network
net = get_citation_network("KR1012345670000", depth=1, limit=30)
# → {"citing": [...], "cited": [...]}  forward + backward citation
# CITES 엣지의 7키 메타 (source_type='uspto_odp'/'kipris', conf=0.95) 자동 포함
```

#### C. "특정 특허의 발명자 + 같은 발명자가 만든 다른 특허"

```python
from ipgraph.tools.graph import get_inventors_of_patent, list_patents_of_assignee
inventors = get_inventors_of_patent("US11234567B2")
# 같은 inventor → 다른 patent 는 patent_inventors 로 traverse
# (별도 cypher template `ip_inventor_other_patents` — agent intent 의 graph_worker)
```

#### D. "공동 출원 네트워크 — Samsung SDI 의 협력사"

```python
from ipgraph.tools.graph import find_co_assignees
co = find_co_assignees("ASN-SAMSUNG-SDI", limit=20)
# → [{"co_assignee_id": ..., "name": "...", "n_co_patents": 42, "cpc_overlap": ["H01M"]}]
# 공동 출원 = 기술 파트너십 증거
```

#### E. "최다 인용 받은 LFP 양극재 특허 top-10"

```python
from ipgraph.tools.graph import most_cited_patents
top = most_cited_patents("H01M4/58", top_k=10, by="cited_by_count")
# CPC subgroup (H01M4/58 = LFP 계열) → cited_by_count desc
# 기술 영향력 정량 평가 — citation 적재 후 (load_uspto_odp.py 의 CITES)
```

#### F. (Cross 진입점) "Samsung SDI 의 특허 영향력 ↔ 영업이익 상관"

```python
from ipgraph.tools.bridge import bridge_assignee_to_corp
from autonexusgraph.tools.financials import get_operating_income
corp = bridge_assignee_to_corp("ASN-SAMSUNG-SDI")
# → {"corp_code": "00126380", "match_type": "qid", "confidence_score": 0.95}
op = get_operating_income(corp["corp_code"], 2024)
# 본격적 cross-domain 은 §4.1~§4.3 참조 — 본 시나리오는 진입점만 시연
```

---

## 5. 안전 가드 동작 표

| 가드 | 코드 | 동작 | 임계값 / 동작 |
|---|---|---|---|
| **prompt_safety** | `safety/prompt_safety.py` | injection 단발 차단 + low-risk telemetry | high-risk 단발 차단 |
| **cypher_guard** | `safety/cypher_guard.py:35-50, 68 assert_read_only` | 모든 Cypher 호출 전 검사 | `CREATE\|MERGE\|DELETE\|DETACH\|SET\|REMOVE\|LOAD CSV\|DROP` + 위험 CALL (apoc.periodic/trigger/export/import/refactor/merge/create/cypher/lock/schema) 차단 |
| **number_guard** | `agents/number_guard.py` | synthesizer 의 큰 숫자 마스킹 | `tool_results` + `evidence` 의 화이트리스트만 인용 |
| **language_guard** | `safety/language_guard.py:16` | 답변 한국어 비율 검증 | `FINGRAPH_MIN_KOREAN_RATIO=0.30`, `FINGRAPH_MIN_LANG_CHARS=20` |
| **confidence edge guard** | `agents/validator.py:43, 125-162` | 답변 근거 그래프 엣지 confidence 검사 | `LOW_CONFIDENCE_THRESHOLD=0.5`. 전부 < 0.5 → `all_low` hard fail + replan. 일부 → `some_low` soft warning |
| **cost tier 3 계층** | `agents/cost_estimator.py` + `agents/budget_guard.py` | 세션 → 도메인 turn → 호출별 사전 추정 | `LLM_SESSION_HARD_LIMIT_USD` / `config.turn_budget_for_domain` (finance $0.50 / auto $0.30 / ip $0.05) / `LLM_COST_AUTO_APPROVE_USD=0.50` 초과 시 HITL |

---

## 6. 도메인별 인텐트 화이트리스트

각 worker 가 호출 전 검증. 외부 인텐트 호출 시 `RuntimeError`.

| 도메인 | sql_worker | graph_worker | research_worker | 코드 |
|---|---|---|---|---|
| **finance** | 7 (`lookup_company` / `get_revenue` / `get_operating_income` / `get_company_info` / `get_balance_sheet_item` / `compare_companies` / `list_companies_by_market`) | 11 (위 §1.2 모두) | 3 (`search_documents` / `search_by_metadata` / `get_chunk`) | `agents/workers.py:30-41` |
| **auto** | 17 (위 §2.1 + bridge 4 + `cross_query` + macro 2 + plant·process 4) | 11 (위 §2.2 핵심) | 3 (`search_documents_auto` / `search_by_metadata_auto` / `get_chunk_auto`) | `src/autograph/agent_handler.py:42-65` |
| **ip** | 8 (위 §3.1 + bridge 2 + `cross_query_ip`) | 8 (위 §3.2 핵심) | 3 (`search_patents` / `search_by_metadata_ip` / `get_chunk_ip`) | `src/ipgraph/agent_handler.py:26-42` |
| **cross_domain** | finance ∪ auto ∪ ip SQL | finance ∪ auto ∪ ip graph + bridge.* | 세 도메인 research 모두 | `src/autograph/agent_handler.py::CrossDomainHandler` |

---

## 7. 답변 형식 약속

agent 답변은 항상:
- **출처 명시** — `citations` 필드에 `chunk_id` / `corp_code` / `rcept_no` / `nhtsa_campaign_id` / `pub_no` 등 정확한 ID + (있다면) 회계연도 / snapshot_year
- **confidence 노출** — 답변 근거 엣지의 `confidence_score` 가 표시 (Streamlit UI 는 ≥0.9 ✓ / 0.5~0.9 ⚠ / <0.5 ❌ 아이콘)
- **불확실 시** — "정보 부족" 응답 (LLM 이 추측·생성 금지). `validation_status='failed'` + `aborted_reason='insufficient_evidence'` 또는 `'needs_clarification'` 으로 표시
- **재무 수치** — 절대 LLM 생성 금지. 항상 PostgreSQL 조회 결과만 사용 (number_guard 강제)

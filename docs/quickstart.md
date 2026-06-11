# Quickstart — 5분 안에 첫 질의

> **목표**: 환경 구성 → DB 부팅 → 최소 데이터 적재 → 첫 질의·답변 확인 까지 5분.
> 전체 운영·평가·확장은 [README §14 Quickstart](../README.md#14-quickstart) (finance) ·
> [Quickstart — AutoGraph](../README.md#quickstart--autograph-자동차-도메인) ·
> [Quickstart — IPGraph](../README.md#quickstart--ipgraph-특허-도메인) 참조.
>
> **선행 조건**: Docker 24+, Python 3.10+, ~6 GB RAM. GPU 는 BGE-M3 임베딩에 필요하나 본 quickstart 는 미적재 상태로 진행 (임베딩 backfill 은 §6).

---

## 1. 의존성 설치 (1분)

```bash
cd /workspace/arsim/AutoNexusGraph
cp .env.example .env                          # DART_API_KEY 등 키 설정 (DART 키만 있어도 finance 진입 가능)
make install                                  # pip install -e ".[all]" — core + agent + mcp 의존성 일괄
```

DART 키 발급은 https://opendart.fss.or.kr/uss/umt/login/loginPage.do (무료). 키 없이도 본 quickstart 의 §3 `make load-companies` 까지는 빈 상태로 부팅됨.

---

## 2. DB 부팅 + 헬스체크 (1분)

```bash
mkdir -p ~/arsim/DB_FG/{postgres,neo4j/data,neo4j/logs,neo4j/import,neo4j/plugins}
make up                                       # docker-compose up -d — PG 16(+pgvector) + Neo4j 5.18
make health                                   # pg_isready + Neo4j Bolt ping
```

**포트** (호스트):
- Neo4j HTTP `31009` (브라우저 `http://localhost:31009` — 기본 사용자 `neo4j` / `autonexusgraph_dev`)
- Neo4j Bolt `31010`
- PostgreSQL `31011` (pgvector 내장)
- (FastAPI 가동 후) `31020`, Streamlit `31021`

**스키마 자동 적용** — 빈 볼륨이면 `docker-entrypoint-initdb.d` 가 `infra/postgres/init/01~30*.sql` (총 31개, 12a/12b 포함) 를 알파벳 순으로 1회 자동 실행. 기존 볼륨에는 [docs/operations/migrations.md](operations/migrations.md) 의 hot-apply.

---

## 3. 최소 데이터 적재 (2분 — DART 키 있을 때)

DART 키가 없으면 본 단계는 건너뛰고 §4 의 도메인 plug-in 확인만 수행 가능.

```bash
make ingest-step1                             # DART corp 마스터 + KRX 상장사 (~30초)
make load-companies                           # → anxg_master.companies 295 row
make load-entity-map                          # → anxg_master.entity_map 1,979 row (ticker/QID/LEI/CIK)
```

데이터 적재 확인:

```bash
psql -h localhost -p 31011 -U autonexusgraph -d autonexusgraph \
  -c "SELECT COUNT(*) FROM anxg_master.companies;"
# expected: count = 295
```

---

## 4. 도메인 plug-in 활성 확인 (10초)

```bash
# 기본은 autograph 만 활성. ip 도메인 활성화는 ENV 1줄 추가.
grep AUTONEXUSGRAPH_DOMAIN_PLUGINS .env       # 없으면 기본값 "autograph"
echo "AUTONEXUSGRAPH_DOMAIN_PLUGINS=autograph,ipgraph" >> .env   # ip 도메인 추가 (선택)

# 등록된 도메인 핸들러 확인:
python3 -c "
import os
os.environ['AUTONEXUSGRAPH_DOMAIN_PLUGINS'] = 'autograph,ipgraph'
from autonexusgraph.agents._domain_handler import discover_plugins, _HANDLERS
discover_plugins(force=True)
print('등록된 도메인:', sorted(_HANDLERS.keys()))
# expected: ['auto', 'cross_domain', 'ip']
"
```

> `finance` 는 core 내장 도메인으로 항상 활성 (handler 등록 없이 코어 기본). `auto` / `ip` 는 plug-in.

---

## 5. 첫 질의 (1분)

가장 빠른 방법은 Python 직접 호출 (FastAPI / Streamlit 띄울 필요 없음):

```bash
python3 -c "
from autonexusgraph.agents import run_agent

# 도메인 명시 (auto/finance/ip/cross_domain) 또는 None 으로 자동 라우팅
result = run_agent('삼성전자 2023년 매출은?', domain='finance')
print('━━━ 답변 ━━━')
print(result['answer'])
print()
print('━━━ 인용 ━━━')
for c in (result.get('citations') or [])[:3]:
    print(' -', c)
print()
print('replan 횟수:', result.get('n_replans'))
print('LLM 비용 USD:', result.get('llm_usage_usd'))
"
```

> LLM 키 (OpenAI / Anthropic / Google) 가 없으면 `[FAKE LLM]` 응답 모드로 동작. `.env` 의 `OPENAI_API_KEY` (또는 `ANTHROPIC_API_KEY`) 설정 후 실제 LLM 호출.

자동차 도메인 (auto):

```bash
python3 -c "
from autonexusgraph.agents import run_agent
result = run_agent('Hyundai Sonata 2024 리콜 사례', domain='auto')
print(result['answer'])
"
```

Cross-Domain (3 도메인 한 turn):

```bash
python3 -c "
from autonexusgraph.agents import run_agent
# 자동 라우팅 — finance + auto 동시 키워드 감지 시 cross_domain 진입
result = run_agent('현대모비스 매출과 모비스가 공급하는 차종의 최근 리콜은?')
print('도메인 자동 라우팅:', result.get('domain'))
print(result['answer'])
"
```

---

## 6. FastAPI / Streamlit (선택)

```bash
make serve-api                                # FastAPI :31020 — POST /chat (blocking) + /chat/stream (SSE)
pip install streamlit                         # 별도 의존성
make serve-ui                                 # Streamlit :31021 채팅 UI (st.status 노드 진행 표시)
```

브라우저에서 `http://localhost:31021` — 도메인 토글 (finance/auto/cross_domain/ip) + 멀티턴 히스토리.

---

## 7. 다음 단계

| 목표 | 가이드 |
|---|---|
| 자동차 도메인 데이터 전체 적재 (NHTSA/Wikidata/EPA 등) | [README §13 Quickstart — AutoGraph](../README.md#quickstart--autograph-자동차-도메인) |
| 특허 도메인 적재 (CPC + OpenAlex 이미 완료, KIPRIS/USPTO 추가) | [README §13 Quickstart — IPGraph](../README.md#quickstart--ipgraph-특허-도메인) |
| 임베딩 backfill (BGE-M3 GPU) | `make serve-embeddings` + `make embed-chunks` |
| LangGraph 활성화 (PG checkpoint + tracing) | `make install-agent` + `make enable-langgraph` |
| 평가 매트릭스 측정 | `make eval-smoke` (3 row) / `make eval-full` (100 문항) / `make audit-dod` (DoD 20항 트래픽라이트) |
| 도메인 plug-in 새로 추가 | [docs/architecture.md §6.2](architecture.md) |
| 막힐 때 | [docs/faq.md](faq.md) (자주 막히는 지점 + 진단 트리) |
| 도구·tool API 참조 | [docs/api_reference.md](api_reference.md) |

---

## 부록: 환경 변수 빠른 참조

| 변수 | 기본값 | 의미 |
|---|---|---|
| `AUTONEXUSGRAPH_DOMAIN_PLUGINS` | `autograph` | 활성 도메인 plug-in (CSV). `autograph,ipgraph` 로 ip 추가. 빈 값이면 finance only. |
| `DART_API_KEY` | (필수) | finance 핵심 데이터 소스 |
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `GOOGLE_API_KEY` | (선택) | LLM provider — 한 개 이상 필요. 없으면 FAKE LLM |
| `LLM_PROVIDER` | (자동 detect) | `openai` / `anthropic` / `google` / `local` |
| `LLM_SESSION_HARD_LIMIT_USD` | `5.00` | 세션 총 LLM 비용 한도 (`llm/cost.py:140 get_session_limit_usd` 기본값 + `.env.example:81`) |
| `LLM_COST_AUTO_APPROVE_USD` | `0.50` | turn 추정 비용이 이를 초과하면 HITL 승인 |
| `FINGRAPH_MIN_KOREAN_RATIO` | `0.30` | language_guard 한국어 비율 임계 |
| `TRACE_BACKEND` | (none) | `langfuse` / `langsmith` — tracing 활성 시 |
| `KIPRIS_API_KEY` | (선택) | ip 도메인 한국 특허 적재용 |
| `DATA_GO_KR_API_KEY` | (선택) | auto 도메인 팩토리온 / 한국 리콜 / EV 충전소 |

## 8. 도구 사용 예시 + 도메인별 Quickstart (AutoGraph / IPGraph) — README §14 migration

> README §14 에서 이동(2026-06-11) — 일반 setup(§1~8) 외 도구 호출 예시 + 도메인별 빠른 시작.


```bash
# 0. .env 작성 (.env.example 복사 후 DART_API_KEY 채움)
cp .env.example .env

# 1. 의존성 설치
make install

# 2. DB 컨테이너 (PG + Neo4j minimal) — 데이터 폴더 먼저:
mkdir -p ~/arsim/DB_FG/{postgres,neo4j/data,neo4j/logs,neo4j/import,neo4j/plugins}
make up
# 외부 포트:  Neo4j  31009(HTTP) / 31010(Bolt)   PG  31011(pgvector 내장)
make health

# 3. 마스터 + DART 정형 데이터
make ingest-step1     # DART corp 마스터 + KRX 상장사 + targets 매칭
make load-companies   # anxg_master.companies
make load-entity-map  # ticker/jurir_no/business_no entity_map 시드

make ingest-step2     # DART filings + 재무 + 정형 지배구조 (자회사/임원/주주)
make load-all         # PG filings + financials
make load-graph-structural   # Neo4j SUBSIDIARY_OF / EXECUTIVE_OF / MAJOR_SHAREHOLDER_OF
make load-persons     # anxg_master.persons (동명이인 분리)

# 4. 외부 보강 (Wikidata + Wikipedia)
make ingest-step3     # Wikidata SPARQL (~55% 매핑)
make load-wikidata    # entity_map 보강 + Neo4j 속성

make ingest-step4     # Wikipedia 본문 + Infobox (~93% 매핑)
make load-wikipedia
make build-wiki-chunks   # Wikipedia 본문 → anxg_vec.chunks (section=wikipedia_ko)

# 5. 뉴스 + 글로벌 보강
make ingest-step6     # 연합뉴스 RSS
make load-news ; make load-graph-news     # 멘션 + CO_MENTIONED_WITH

make ingest-sec       # SEC EDGAR (한국 ADR — CIK 매핑 회사만)
make load-sec
make ingest-gleif     # GLEIF LEI (한국 jurisdiction 2,700건)
make load-gleif

# 6. 그래프 스키마 정합성 마이그레이션 (1회, 멱등 — 변경 0 이면 이미 적용됨)
make migrate-schema

# 7. KCGS ESG (수동 CSV 다운로드 후)
make ingest-kcgs                # 보도자료 모니터 — 등급 발표 알림
# 등급 CSV 를 data/raw/kcgs/<year>/ratings.csv 에 저장 후
make load-kcgs

# 8. 임베딩 (BGE-M3 GPU 가동 후 backfill)
# 별도 터미널에서:
make serve-embeddings
# 메인 터미널에서:
make embed-chunks         # anxg_vec.chunks.embedding NULL → BGE-M3 1024d 채움

# 9. 검증
make validate-quality     # 3-way cross 검증 + data/reports/quality_<date>.md

# 10. P3 LLM 관계 추출 (embedding 완료 후)
make p3-extract-dry       # 비용 추정 — LLM 호출 0
make p3-extract           # 실제 추출 (HARD_LIMIT $1.0)
make p4-load              # P4 검증 + Neo4j 적재

# 11. LangGraph 활성화 (§7.5.8 — PG checkpoint + tracing)
make install-agent        # pip install -e ".[agent]" — langgraph + langfuse + langsmith
make enable-langgraph     # 헬스체크: _HAS_LANGGRAPH + checkpointer 타입 확인
# (선택) tracing: .env 에 TRACE_BACKEND=langfuse + LANGFUSE_* 키 또는 TRACE_BACKEND=langsmith + LANGSMITH_API_KEY

# 12. API + UI 가동
make serve-api            # FastAPI :31020 — POST /chat (blocking) + /chat/stream (SSE)
pip install streamlit     # (선택) UI 의존성
make serve-ui             # Streamlit :31021 채팅 UI — st.status 노드 진행 표시

# 13. 평가 (gold 큐레이션 후)
make eval-smoke           # 3 row 빠른 검증
make eval-full            # 100문항 4 어댑터 매트릭스
```

### 도구 사용 예시

```python
from autonexusgraph.tools import (
    lookup_company, list_subsidiaries, get_executives,
    get_companies_of_person, find_paths, search_documents,
)

# 1) 회사 식별
lookup_company("삼성전자")
# → [{"corp_code": "00126380", "name": "삼성전자(주)", "stock_code": "005930",
#     "wikidata_qid": "Q20718", "wikipedia_title_ko": "삼성전자"}]

# 2) 자회사 그래프
list_subsidiaries("00126380", snapshot_year=2024, limit=10)
# → [{"child_name": "삼성디스플레이", "ownership_pct": 84.78, ...}, ...]

# 3) 인물 → 임원직 회사 매트릭스
get_companies_of_person("이재용")
# → 동명이인 모두 합쳐 반환 (회사·역할·연도)

# 4) 멀티홉 경로
find_paths("00126380", "00164779", max_hops=3)
# → 삼성전자 ↔ SK하이닉스 최단 경로

# 5) Hybrid RAG
search_documents(
    "반도체 사업 위험요인",
    corp_code="00126380",
    fiscal_year=2024,
    section_contains="위험",
    top_k=5,
)
```

크롤러는 **이어받기·실패추적·Ctrl+C 안전종료** 지원. 로더는 모두 **idempotent**. raw 만 있으면 `data/processed/` 와 DB 는 언제든 재생성 가능.

### Quickstart — AutoGraph (자동차 도메인)

AutoNexusGraph 와 동일 인프라 (PG / Neo4j / pgvector / BGE-M3) 위에 자동차 도메인만 추가.

```bash
# 0. 인프라는 AutoNexusGraph quickstart 와 공유 — 동일 docker 컨테이너에 스키마만 추가
# infra/postgres/init/ 의 01~29 sql (총 30 파일, 12a/12b 별도) 이 멱등이라 hot-apply 가능 (docs/operations/migrations.md).
# 빈 볼륨이면 docker entrypoint 가 01~24 를 순차 자동 실행 — 아래는 hot-apply (이미 부팅된 인스턴스 대상).
make migrate-schema-pg MIGRATE_FILE=07_autograph.sql
make migrate-schema-pg MIGRATE_FILE=08_bridge.sql
make migrate-schema-pg MIGRATE_FILE=09_vec_chunks_auto_meta.sql
make migrate-schema-pg MIGRATE_FILE=10_autograph_bom.sql
make migrate-schema-pg MIGRATE_FILE=11_autograph_staging.sql
make migrate-schema-pg MIGRATE_FILE=12a_autograph_inspections.sql
make migrate-schema-pg MIGRATE_FILE=12b_autograph_investigations.sql
make migrate-schema-pg MIGRATE_FILE=13_autograph_oem_sec.sql
make migrate-schema-pg MIGRATE_FILE=14_master_entities.sql
make migrate-auto-production         # 15_autograph_production.sql (DART 사업보고서 파서)
make migrate-auto-kama               # 16_autograph_kama_macro.sql
make migrate-schema-pg MIGRATE_FILE=17_autograph_oem_news.sql       # IR/뉴스룸 events_oem_news
make migrate-schema-pg MIGRATE_FILE=20_auto_minerals.sql            # USGS 핵심광물 (L6 소재 부록)
make migrate-schema-pg MIGRATE_FILE=21_auto_ev_chargers.sql         # EV 충전 인프라 (예정 — `DATA_GO_KR_API_KEY` 발급 후)
make migrate-schema-pg MIGRATE_FILE=24_auto_factoryon.sql           # 팩토리온 공장등록 (부분 적재 90행)
python -m autograph.loaders.neo4j_init    # CONSTRAINT/INDEX 멱등 — ontology/auto/entities.yaml SSOT

# (옵션) pre-push 정합성 검증 — DB·LLM 없이 동작 (mock 모드)
make smoke-e2e                       # pytest + audit-ontology (cypher cross-check) + audit-eval-matrix sim + audit-mcp + audit-ipgraph + audit-trace sim + gold qa lint

# 1. 인제스션 (.env 의 AUTO_INGEST_MAKES / AUTO_INGEST_YEAR_MIN/MAX 기반)
make ingest-auto-all                # = vpic + recalls + complaints + safety + wikipedia + epa + investigations + sec-oem
# 한국 시장 / KATRI / KNCAP (graceful skip — 키 없으면 0 byte)
make ingest-datagokr-recalls        # data.go.kr 3048950 리콜 CSV (무인증, 수동 다운)
make ingest-datagokr-inspections    # data.go.kr 15155857 (CSV 수동 다운)
make ingest-katri                   # bigdata-tic.kr (BIGDATA_TIC_CLIENT_ID/SECRET 필요)
make ingest-kncap                   # KNCAP (KNCAP_API_KEY 또는 수동 CSV)

# 2. P2 결정적 적재 — raw → PG → Neo4j → bridge → seed/supplier/recall→comp → chunks
make load-auto-all
# 의존 순서: neo4j-init → pg → specs → neo4j → bridge → standards/plants → safety → epa → aihub
#          → nhtsa-taxonomy → supplier-edges → complaints-neo4j → recall-components → complaint-components
#          → investigations → oem-sec → derive-contains-system → wikidata-part-supplies → manufactured-at
#          → build-chunks-auto

# 3. 제조 공정·생산 데이터 (옵션 — manufacturing 어댑터 보강)
make load-sandang-processes         # 산단공 합성 공정데이터 → :Process 사전
make load-dart-production           # DART 사업보고서 본문 파서 → auto.production_*
# 팩토리온 (DATA_GO_KR_API_KEY 발급 후)
make ingest-factoryon-company NAME=현대자동차

# 4. 청크 임베딩 (finance 와 동일 BGE-M3 backfill — generic 작업)
make embed-chunks

# 5. (선택) P3 LLM 관계 추출 — 비용 가드 dry-run 먼저
make extract-auto-p3-cost MFR_IDS=498 P3_LIMIT=50
make extract-auto-p3      MFR_IDS=498 P3_LIMIT=50 P3_HARD_LIMIT=2.0
make validate-auto-p4     # anxg_auto.staging_relations → P4 → Neo4j candidate/validated 적재

# 6. 에이전트 호출 (도메인 명시 또는 자동 판정)
python -c "from autonexusgraph.agents import run_agent;
s = run_agent('Hyundai Sonata 2024 리콜 사례', domain='auto');
print(s['answer'])"

# 7. 평가
make eval-auto                       # eval/reports/auto_<timestamp>/summary.md
make eval-cross                      # CD-L1~L4 30문항 (§8.1)

# 8. DoD 트래픽라이트 (본 문서 §10 — 20 항 — v3.0 IPGraph + ProcessGraph 흡수)
make audit-bom-coverage
make audit-edge-meta
make audit-dod                       # 20 항 종합 — eval/reports/dod_v3.0.md
```

자세한 절차·미구현 영역·회귀 안전성은 [docs/autograph.md](./docs/autograph.md). 도메인 라우팅 흐름은 [docs/operations/agents.md](./docs/operations/agents.md#도메인-라우팅-finance--auto--cross_domain).

### Quickstart — IPGraph (특허 도메인)

상세 시나리오·핸들러·온톨로지·도구 SSOT 는 [docs/ipgraph.md](./docs/ipgraph.md). **코드/스키마 완료, KIPRIS·USPTO 데이터 적재만 사용자 액션 대기.**

```bash
# 0. ENV 에 ipgraph 추가 (도메인 plug-in soft-load 활성)
echo "AUTONEXUSGRAPH_DOMAIN_PLUGINS=autograph,ipgraph" >> .env
# (선택) KIPRIS_API_KEY=…   # 공공데이터포털 발급 후

# 1. 스키마 마이그레이션 (적용 완료 — hot-apply 재실행도 멱등)
make migrate-schema-pg MIGRATE_FILE=18_ipgraph.sql       # anxg_ip.patents/assignees/citations/inventors 등 12 테이블
make migrate-schema-pg MIGRATE_FILE=19_ipgraph_bridge.sql # anxg_ip.assignee_corp_map join 테이블
make migrate-schema-pg MIGRATE_FILE=22_ip_works.sql      # OpenAlex anxg_ip.works/institution/work_institution
make migrate-schema-pg MIGRATE_FILE=23_ip_cpc.sql        # CPC scheme 계층

# 2. 데이터 인제스션 (실제 Makefile 타깃 — `ip` prefix 없음)
make load-cpc                    # ✅ 완료 — 무인증 USPTO/EPO CPC scheme bulk → 10,695 row
make ingest-openalex             # ✅ 완료 — OpenAlex 수집 (OPENALEX_EMAIL ENV 권장, 일 10만 크레딧)
make load-openalex               # ✅ 완료 — works 629 / institution 38 적재
# (대기) KIPRIS_API_KEY 발급 후
make ingest-kipris               # 한국 특허·출원
# (대기) USPTO Open Data Portal bulk (PatentsView 후속, 2026-03-20 이관, 무인증)
make ingest-uspto-odp
# (대기) assignee 적재 후 corp 매핑
make load-assignee-corp-map      # anxg_ip.assignee_corp_map 매칭 (supplier candidate SOP 재사용)

# 3. 평가 + DoD 재측정
make eval-ip                     # gold_qa_ip_v0.jsonl 30 row (IP-L1/L2/L3 각 10)
make eval-cross                  # CD-L3/L4 ip 결합 포함 (cross 49 row — CD-L1~L4 + CD-PROC 5 + IP 결합 변형)
make audit-dod                   # §10.12 코어 변경량 — baseline 831e72d (상용화 P0/P1 reset) 기준 0% ✅
```

---

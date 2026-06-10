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

# LLM 비용 가드 (단일 SSOT)

LLM(특히 OpenAI) 비용을 막는 정책의 **유일한 참조 문서**. 노브·동작·검증을 여기 한곳에 모은다.
관련 코드: `src/autonexusgraph/llm/base.py` (`get_llm_client` auto-wrap + kill-switch) ·
`cost.py` (한도 resolve) · `cost_tracker.py` (가드) · `cost_log.py` (영속 로그) ·
`budget_aware.py` (호출 wrapper) · 루트 `llm_guard.py` (운영 CLI).

## Kill-switch — 즉시 완전 차단

`llm_enabled`(config) / `LLM_ENABLED`(.env) 가 `false` 면 `get_llm_client()` 가
**`LLMError` 로 모든 LLM 호출을 즉시 차단**한다(비용 한도와 무관). 토글:

```bash
make llm-off      # LLM_ENABLED=false  → 이후 모든 호출 차단
make llm-on       # LLM_ENABLED=true   → 허용
make llm-status   # 현재 상태 + 누적/한도/오늘/이번달
make llm-reset    # cost_log.jsonl 아카이브(*.bak.<stamp>) → 누적 window 리셋
#  (= python llm_guard.py <status|on|off|reset>)
```

`on/off` 는 `.env` 의 `LLM_ENABLED` 를 갱신한다. **실행 중 서버**는 설정 캐시
(`get_settings` lru_cache) 때문에 재시작해야 반영되고, 배치/CLI 는 새 프로세스라 즉시 반영.

## 한도는 2겹 — 둘 중 하나라도 도달하면 `BudgetExceeded`

| # | 이름 | 무엇을 막나 | 리셋 | 기준 데이터 |
|---|------|------------|------|-------------|
| 1 | **영속/시간창 누적** | "많이 쓰면 막기"의 실질 브레이크 | **안 됨** (turn·프로세스 무관) | `data/cost_log.jsonl` 시간창 합 |
| 2 | **단일 tracker(turn/배치)** | 한 turn·한 배치의 폭주 | turn/배치마다 | 그 tracker 인메모리 누적 |

가드는 매 LLM 호출 **직전** `tracker.guard()` 에서 동작 (`cost_tracker.py`). 영속 base 는
tracker 생성 시 `cost_log.jsonl` 에서 1회 스냅샷 → 이미 한도를 넘었으면 **그 turn 첫 호출부터** 차단.

## 노브 (전부 `.env` 또는 셸 env — 셸 export 가 우선)

| env / settings | 기본 | 의미 |
|----------------|------|------|
| `LLM_ENABLED` | true | kill-switch — false 면 모든 호출 차단 |
| `LLM_SESSION_HARD_LIMIT_USD` | 5.00 | (1) 영속 누적 한도 |
| `LLM_COST_WINDOW_HOURS` | 24 | (1) 누적 집계 시간창(시간). `0` → 전체 기간 |
| `LLM_SESSION_WARN_AT_USD` | 2.50 | 경고 임계(로그) |
| `LLM_COST_HARD_LIMIT_USD` | 5.00 | (2) 단일 tracker 기본 한도 (배치 진입점) |
| `AGENT_TURN_BUDGET_USD` | 0.20 | (2) 대화 turn 한도(도메인 기본). `AGENT_TURN_BUDGET_<DOMAIN>_USD` 로 도메인별 override |
| `LLM_COST_AUTO_APPROVE_USD` | 0.50 | 배치 사전추정 자동승인 임계 |

> **중요**: `.env` 값은 pydantic `Settings` 로 읽힌다. 한도 resolve 는 `cost.py` 의
> `get_*_usd()` 가 **셸 env → settings(.env) → 코드 기본값** 순으로 처리한다.
> (과거 버그: `os.environ` 만 읽어 `.env` 값이 무시됨 → 안 막힘.)

## 적용 경로 — auto-wrap (모든 LLM 호출이 자동으로 거침)

`get_llm_client()` 가 반환 전 **항상** 두 wrapper 로 감싼다. 호출자가 아무것도 안 해도 가드됨:

```
get_llm_client()
  └ inner(adapter)
      └ BudgetAwareLLMClient   # 호출 前 guard(), 後 record() (stream 포함)
          └ LoggingLLMClient   # cost_log.jsonl append (provider/메서드 무관) [최외곽]
start_turn_context(...)  →  per-turn 한도 = turn budget 자동 주입
```

- `budget_aware_client(...)` 로 **또 감싸도 안전** — 체인에 이미 가드가 있으면 재-wrap 하지
  않고(idempotent) tracker 한도만 tighten 한다 → 같은 tracker 에 record 2회(이중 계산) 방지.
- raw SDK(`openai.OpenAI()`/`anthropic.Anthropic()`) **직접** 호출만 이 경로를 우회하므로 금지.
  새 LLM 호출은 반드시 `get_llm_client()` 경유.

## 사용량 / 비용 보기 (일별·월별)

```bash
python -m autonexusgraph.llm.cost_history              # 월별+일별+한도대비+이번달 예상
python -m autonexusgraph.llm.cost_history --month      # 월별 요약만
python -m autonexusgraph.llm.cost_history --today      # 오늘만
python -m autonexusgraph.llm.cost_history --this-month # 이번 달만
python -m autonexusgraph.llm.cost_history --days 7     # 일별 최근 7일 (0=전체)
python -m autonexusgraph.llm.cost_history --from 2026-06-01 --to 2026-06-30
python -m autonexusgraph.llm.cost_history --json       # 기계 파싱용
```

출력에 포함: 월별/일별 비용 막대, **현재 window 누적 vs 한도(%)**, **이번 달 예상 월비용**
(run-rate), provider/모델/caller 별 비용. 집계 출처는 `data/cost_log.jsonl`(DB 불필요).

## 가드 단위 테스트

```bash
python -m pytest tests/ -k "cost or budget or track or tracing or provider" -q
```

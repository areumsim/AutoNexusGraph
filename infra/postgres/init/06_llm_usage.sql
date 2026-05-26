-- LLM 호출 사용량·비용 트래킹 (ops 스키마).
--
-- 사용자 명시 원칙: 모든 LLM 호출 비용을 dry-run 으로 검토하고, 누적 한도 초과 시
-- 즉시 중단할 수 있어야 한다. 본 테이블은 (1) run 단위 누적 집계 (2) call 단위 상세 두 트랙.

SET client_encoding = 'UTF8';

-- run 단위 (batch 1회 / agent conversation 1회)
CREATE TABLE IF NOT EXISTS ops.llm_usage (
    run_id        UUID         PRIMARY KEY,
    started_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
    ended_at      TIMESTAMPTZ,
    caller        VARCHAR(80)  NOT NULL,        -- 'p3_extract' / 'agent_chat' / 'eval_judge' / ...
    model         VARCHAR(80)  NOT NULL,
    n_calls       INT          NOT NULL DEFAULT 0,
    input_tokens  BIGINT       NOT NULL DEFAULT 0,
    output_tokens BIGINT       NOT NULL DEFAULT 0,
    cost_usd      NUMERIC(10, 4) NOT NULL DEFAULT 0,
    status        VARCHAR(20)  NOT NULL DEFAULT 'running',   -- running | ok | aborted_budget | error
    meta          JSONB        NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS idx_llm_usage_caller_started
    ON ops.llm_usage(caller, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_llm_usage_status
    ON ops.llm_usage(status, started_at DESC);

COMMENT ON TABLE ops.llm_usage IS
  'LLM 호출 run 단위 집계 — 사용자 명시 비용 가드 원칙. status=aborted_budget 은 circuit breaker 발동';

-- call 단위 (옵션 — 디버그용. 운영 시 batch 단위 집계만 필요하면 안 채워도 됨)
CREATE TABLE IF NOT EXISTS ops.llm_calls (
    id            BIGSERIAL    PRIMARY KEY,
    run_id        UUID         NOT NULL REFERENCES ops.llm_usage(run_id) ON DELETE CASCADE,
    called_at     TIMESTAMPTZ  NOT NULL DEFAULT now(),
    model         VARCHAR(80)  NOT NULL,
    purpose       VARCHAR(80),                  -- 'extract_relations' / 'plan' / 'synthesize'
    input_tokens  INT          NOT NULL,
    output_tokens INT          NOT NULL,
    cost_usd      NUMERIC(10, 6) NOT NULL,
    latency_ms    INT,
    truncated     BOOLEAN      NOT NULL DEFAULT FALSE,
    error         TEXT
);
CREATE INDEX IF NOT EXISTS idx_llm_calls_run ON ops.llm_calls(run_id, called_at);

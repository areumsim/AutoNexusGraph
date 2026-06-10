-- AutoGraph — KAMA (한국자동차산업협회 → 산업통상자원부) 매크로 통계.
--
-- 산단공/DART 와 같은 per-OEM/per-plant 수준은 아니지만, 한국 자동차 산업의
-- 매크로 보건 시계열 — DART 분기 매출, ECOS 환율, KOSIS 산업 통계와 함께
-- Cross-Domain "macro" 컨텍스트 보강.
--
-- 원천:
--   data.go.kr 15051116 (산업통상자원부 / KAMA) — 연간 국내·세계 생산량
--   data.go.kr 15051118 (산업통상자원부)         — 월간 내수·수출 + 수출금액
--
-- PRD §3.5: KAMA / 산업통상자원부 공식 통계 = A 등급 → confidence 0.950.
--
-- 멱등: PRIMARY KEY 가 (snapshot_year) 또는 (snapshot_year, snapshot_month).

SET client_encoding = 'UTF8';

CREATE SCHEMA IF NOT EXISTS anxg_auto;

-- ── 1. 연간 국내·세계 생산량 (15051116, 2005~2025, 21 row) ──────
CREATE TABLE IF NOT EXISTS anxg_auto.macro_production_yearly (
    snapshot_year       SMALLINT      PRIMARY KEY,
    domestic_units_k    BIGINT,         -- 국내생산 (1000대 단위)
    global_units_k      BIGINT,         -- 세계생산 (1000대 단위)
    domestic_share_pct  NUMERIC(6,3) GENERATED ALWAYS AS (
        CASE WHEN global_units_k > 0
             THEN ROUND(domestic_units_k::numeric / global_units_k * 100, 3)
             ELSE NULL
        END
    ) STORED,
    source              VARCHAR(40) NOT NULL DEFAULT 'kama_15051116',
    confidence_score    NUMERIC(4,3) NOT NULL DEFAULT 0.950,
    validated_status    VARCHAR(20) NOT NULL DEFAULT 'validated',
    extraction_method   VARCHAR(40) NOT NULL DEFAULT 'csv_direct_map',
    raw                 JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);


-- ── 2. 월간 산업 보건 (15051118, 2009-01~2025-12, 204 row) ───────
CREATE TABLE IF NOT EXISTS anxg_auto.macro_industry_monthly (
    snapshot_year       SMALLINT NOT NULL,
    snapshot_month      SMALLINT NOT NULL,
    domestic_sales      BIGINT,           -- 내수판매(국산차) — 대
    export_units        BIGINT,           -- 수출량 — 대
    export_value_usd_k  BIGINT,           -- 수출금액 — 천달러
    source              VARCHAR(40) NOT NULL DEFAULT 'kama_15051118',
    confidence_score    NUMERIC(4,3) NOT NULL DEFAULT 0.950,
    validated_status    VARCHAR(20) NOT NULL DEFAULT 'validated',
    extraction_method   VARCHAR(40) NOT NULL DEFAULT 'csv_direct_map',
    raw                 JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (snapshot_year, snapshot_month),
    CHECK (snapshot_month BETWEEN 1 AND 12)
);
CREATE INDEX IF NOT EXISTS idx_auto_macro_monthly_year
    ON anxg_auto.macro_industry_monthly(snapshot_year);


-- 권한
GRANT USAGE ON SCHEMA auto TO autonexusgraph;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA auto TO autonexusgraph;

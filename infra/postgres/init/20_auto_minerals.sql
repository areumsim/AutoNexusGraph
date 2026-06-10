-- AutoGraph — USGS Mineral Commodity Summaries (MCS) L6 결정적 SSOT.
--
-- 사용자 의제: 배터리·L6 BOM 하향 — 핵심광물(Li/Ni/Co/Mn/Graphite) 의 세계·미국
-- 5년 통계 (생산/수입/수출/가격/재고/소비). PDF 가 아닌 **CSV 테이블 배포**.
-- 90+ 비연료 광물.
--
-- 원천:
--   USGS Mineral Commodity Summaries (MCS) — 연 1회 발간, CSV 직배포
--   https://www.usgs.gov/centers/national-minerals-information-center/mineral-commodity-summaries
--
-- 라이선스: 공공 (US Gov). 무인증.
--
-- PRD §3.5: USGS 공식 통계 = A 등급 → confidence 0.950.
--
-- 그래프 흡수: (:Material {NCM811})-[:DERIVED_FROM]->(:Mineral {Ni})
--             확신도 0.95, source_type='usgs_mcs'.
--
-- 멱등: PRIMARY KEY (commodity, snapshot_year).
--
-- 상태: 슬롯 (ingestion 코드 미구현, 예정).

SET client_encoding = 'UTF8';

CREATE SCHEMA IF NOT EXISTS anxg_auto;

CREATE TABLE IF NOT EXISTS anxg_auto.master_minerals (
    commodity            VARCHAR(40)  NOT NULL,        -- 'Li' | 'Ni' | 'Co' | 'Mn' | 'Graphite' | …
    snapshot_year        SMALLINT     NOT NULL,
    world_production     BIGINT,                       -- 세계 생산 (metric tons)
    us_production        BIGINT,                       -- 미국 생산 (metric tons)
    us_import_reliance   NUMERIC(5,2),                 -- 수입 의존도 (%)
    us_imports           BIGINT,                       -- 수입 (metric tons)
    us_exports           BIGINT,                       -- 수출 (metric tons)
    us_reserves          BIGINT,                       -- 미국 매장량 (metric tons)
    world_reserves       BIGINT,                       -- 세계 매장량 (metric tons)
    price_usd_per_ton    NUMERIC(14,2),                -- 가격 (USD/metric ton)
    -- 거버넌스
    source               VARCHAR(40)  NOT NULL DEFAULT 'usgs_mcs',
    confidence_score     NUMERIC(4,3) NOT NULL DEFAULT 0.950,
    validated_status     VARCHAR(20)  NOT NULL DEFAULT 'validated',
    extraction_method    VARCHAR(40)  NOT NULL DEFAULT 'csv_direct_map',
    raw                  JSONB        NOT NULL DEFAULT '{}'::jsonb,
    created_at           TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ  NOT NULL DEFAULT now(),
    PRIMARY KEY (commodity, snapshot_year)
);
CREATE INDEX IF NOT EXISTS idx_minerals_year       ON anxg_auto.master_minerals(snapshot_year);
CREATE INDEX IF NOT EXISTS idx_minerals_commodity  ON anxg_auto.master_minerals(commodity);


-- 권한
GRANT USAGE ON SCHEMA auto TO autonexusgraph;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA auto TO autonexusgraph;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA auto TO autonexusgraph;

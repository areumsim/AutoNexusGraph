-- 팩토리온 공장등록 정보 (data.go.kr 15087611) PG 스키마.
--
-- PRD v2.2 §2.3 — 공정·라인·설비·원가 정형 부분 진입 (LLM 0%).
-- 산단공 (한국산업단지공단) 공장등록 raw → 정규화 적재.
-- factoryon_registry.py 가 raw json 만 저장 — 본 SQL 의 ``auto.factoryon_registry``
-- 가 1차 적재 대상.
--
-- 멱등 (IF NOT EXISTS).

SET client_encoding = 'UTF8';

CREATE SCHEMA IF NOT EXISTS auto;

CREATE TABLE IF NOT EXISTS auto.factoryon_registry (
    factory_no        VARCHAR PRIMARY KEY,             -- 공장관리번호 (산단공 부여)
    company_name      VARCHAR NOT NULL,
    business_no       VARCHAR,                         -- 사업자등록번호
    representative    VARCHAR,
    address           TEXT,
    industrial_complex VARCHAR,                        -- 단지명
    industry_code     VARCHAR,                         -- KSIC 분류
    industry_name     VARCHAR,
    products          TEXT,                            -- 생산품 — comma-separated
    capacity          TEXT,                            -- 생산능력 (원문 — 단위 다양)
    employees         INT,
    land_area_m2      NUMERIC,                         -- 부지면적
    building_area_m2  NUMERIC,                         -- 건축면적
    registered_at     DATE,                            -- 등록일
    -- corp_entity 브리지 진입점 (있을 때만).
    corp_code         VARCHAR,
    -- 메타.
    source            VARCHAR DEFAULT 'datagokr_factoryon',
    source_endpoint   VARCHAR,                         -- 'by_company' | 'by_factory_no' | 'by_industrial_complex'
    snapshot_year     INT,
    schema_version    VARCHAR,
    raw_payload       JSONB,
    created_at        TIMESTAMPTZ DEFAULT now(),
    updated_at        TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_factoryon_company
    ON auto.factoryon_registry(company_name);
CREATE INDEX IF NOT EXISTS idx_factoryon_business_no
    ON auto.factoryon_registry(business_no) WHERE business_no IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_factoryon_corp
    ON auto.factoryon_registry(corp_code) WHERE corp_code IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_factoryon_complex
    ON auto.factoryon_registry(industrial_complex)
    WHERE industrial_complex IS NOT NULL;

COMMENT ON TABLE auto.factoryon_registry IS
  '팩토리온 공장등록 (data.go.kr 15087611). 산단공 SSOT. corp_entity 브리지 진입점.';

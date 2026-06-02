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
    industrial_complex VARCHAR,                        -- 단지명 (irsttNm)
    industry_code     VARCHAR,                         -- 대표 업종코드 (rprsntvIndutyCode)
    industry_codes    VARCHAR,                         -- 전체 업종코드 목록 (indutyCodes, comma-separated)
    industry_name     VARCHAR,                         -- 업종명 (indutyNm)
    products          TEXT,                            -- 주생산품 (mainProductCn)
    capacity          TEXT,                            -- 생산능력 (원문 — 단위 다양; API 미제공)
    employees         INT,                             -- 종업원수 (allEmplyCo)
    land_area_m2      NUMERIC,                         -- 부지면적 (API 미제공)
    building_area_m2  NUMERIC,                         -- 건축면적 (API 미제공)
    registered_at     DATE,                            -- 최초공장등록일 (frstFctryRegistDe, YYYYMMDD→DATE)
    charge_org        VARCHAR,                         -- 민원담당기관 (cvplChrgOrgnztNm)
    tel               VARCHAR,                         -- 회사 전화 (cmpnyTelno)
    fax               VARCHAR,                         -- 회사 팩스 (cmpnyFxnum)
    homepage          VARCHAR,                         -- 홈페이지 (hmpadr)
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

-- 기존 DB 멱등 보강 — CREATE TABLE IF NOT EXISTS 는 컬럼을 추가하지 않으므로,
-- 실측 필드(2026-06, getFctry*Service_v2) 기준 신규 컬럼을 개별 ADD.
ALTER TABLE auto.factoryon_registry ADD COLUMN IF NOT EXISTS industry_codes VARCHAR;
ALTER TABLE auto.factoryon_registry ADD COLUMN IF NOT EXISTS charge_org     VARCHAR;
ALTER TABLE auto.factoryon_registry ADD COLUMN IF NOT EXISTS tel            VARCHAR;
ALTER TABLE auto.factoryon_registry ADD COLUMN IF NOT EXISTS fax            VARCHAR;
ALTER TABLE auto.factoryon_registry ADD COLUMN IF NOT EXISTS homepage       VARCHAR;

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

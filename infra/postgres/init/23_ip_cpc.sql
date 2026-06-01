-- IPGraph — CPC (Cooperative Patent Classification) scheme bulk 적재.
--
-- USPTO/EPO 공동 운영 CPC scheme — 정식 분류 계층 (Section → Class → Subclass →
-- Main group → Subgroup). 본 PR 은 section/class/subclass/main_group (depth 0)
-- 까지 적재 — 약 14K row.
--
-- 원천: https://www.cooperativepatentclassification.org/cpcSchemeAndDefinitions/bulk
--       CPCTitleList20YYMM.zip (탭 분리 텍스트, 섹션별 9 파일).
--
-- 라이선스: 공공 (USPTO/EPO 공동, free for any use).
-- PRD §3.5: CPC scheme = A 등급 → confidence 0.95.
--
-- 멱등: PK (code).

SET client_encoding = 'UTF8';

CREATE SCHEMA IF NOT EXISTS ip;

CREATE TABLE IF NOT EXISTS ip.cpc_scheme (
    code              VARCHAR(40)  PRIMARY KEY,        -- 'A' | 'A01' | 'A01B' | 'A01B1/00' | 'A01B1/02'
    parent_code       VARCHAR(40),                      -- 상위 코드 (section 은 NULL)
    level             VARCHAR(20)  NOT NULL,            -- 'section' | 'class' | 'subclass' | 'main_group' | 'subgroup'
    depth             SMALLINT,                         -- subgroup 의 정수 depth (그 외 NULL)
    title             TEXT,
    -- 거버넌스
    source            VARCHAR(40)  NOT NULL DEFAULT 'cpc_scheme',
    confidence_score  NUMERIC(4,3) NOT NULL DEFAULT 0.950,
    validated_status  VARCHAR(20)  NOT NULL DEFAULT 'validated',
    extraction_method VARCHAR(40)  NOT NULL DEFAULT 'cpc_title_list',
    schema_version    VARCHAR(8)   NOT NULL DEFAULT 'v2.2',
    raw               JSONB        NOT NULL DEFAULT '{}'::jsonb,
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_cpc_parent ON ip.cpc_scheme(parent_code) WHERE parent_code IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_cpc_level  ON ip.cpc_scheme(level);


-- 권한
GRANT USAGE ON SCHEMA ip TO autonexusgraph;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA ip TO autonexusgraph;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA ip TO autonexusgraph;

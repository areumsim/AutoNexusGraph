-- IPGraph — OpenAlex Work / Institution / Author 슬롯.
--
-- 사용자 의제: 특허×논문×재무 3중 cross 승격. Institution(company) →
-- bridge.corp_entity → 특허(assignee) → 재무(R&D비) 동시 추론.
--
-- 원천:
--   OpenAlex API — https://docs.openalex.org
--   주의: 2025-02 이후 무료 키 발급 필요 (하루 10만 크레딧). "무인증" 아님.
--
-- 라이선스: CC0.
--
-- PRD §3.5: OpenAlex (CC0 공식 통계) = A 등급 → confidence 0.950.
--
-- 그래프 흡수: (:Work)-[:AUTHORED_AT]->(:Institution),
--             (:Assignee)-[:AFFILIATED_WITH]->(:Institution).
--             Institution(type='company') → bridge.corp_entity (3중 cross 진입).
--
-- 멱등: PRIMARY KEY = openalex_id / ror_id.
--
-- 상태: 슬롯 (ingestion 코드 미구현, 예정). OpenAlex 키 발급 후 활성.

SET client_encoding = 'UTF8';

CREATE SCHEMA IF NOT EXISTS ip;

-- ── 1. Work (논문) ──────
CREATE TABLE IF NOT EXISTS ip.works (
    openalex_id          VARCHAR(40)  PRIMARY KEY,    -- 'W2741809807' 등 OpenAlex ID
    title                TEXT,
    publication_year     SMALLINT,
    cited_by_count       INTEGER,
    doi                  VARCHAR(120),
    type                 VARCHAR(40),                  -- article | book | dataset | …
    abstract             TEXT,
    -- 거버넌스
    source               VARCHAR(40)  NOT NULL DEFAULT 'openalex',
    confidence_score     NUMERIC(4,3) NOT NULL DEFAULT 0.950,
    validated_status     VARCHAR(20)  NOT NULL DEFAULT 'validated',
    extraction_method    VARCHAR(40)  NOT NULL DEFAULT 'api_direct_map',
    schema_version       VARCHAR(8)   NOT NULL DEFAULT '1',
    raw                  JSONB        NOT NULL DEFAULT '{}'::jsonb,
    created_at           TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_works_year ON ip.works(publication_year);
CREATE INDEX IF NOT EXISTS idx_works_doi  ON ip.works(doi) WHERE doi IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_works_type ON ip.works(type);


-- ── 2. Institution (연구기관 — 기업 R&D 브리지) ──────
CREATE TABLE IF NOT EXISTS ip.institution (
    ror_id               VARCHAR(40)  PRIMARY KEY,    -- ROR (Research Organization Registry) ID
    openalex_id          VARCHAR(40),                  -- OpenAlex Institution ID
    name                 VARCHAR(200),
    country              VARCHAR(2),                   -- ISO 3166-1 alpha-2
    type                 VARCHAR(20),                  -- company | education | government | healthcare | facility | nonprofit
    corp_code            VARCHAR(8),                   -- bridge.corp_entity 매칭 (type='company' 한정, 선택)
    -- 거버넌스
    source               VARCHAR(40)  NOT NULL DEFAULT 'openalex',
    confidence_score     NUMERIC(4,3) NOT NULL DEFAULT 0.950,
    validated_status     VARCHAR(20)  NOT NULL DEFAULT 'validated',
    extraction_method    VARCHAR(40)  NOT NULL DEFAULT 'api_direct_map',
    schema_version       VARCHAR(8)   NOT NULL DEFAULT '1',
    raw                  JSONB        NOT NULL DEFAULT '{}'::jsonb,
    created_at           TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_inst_type     ON ip.institution(type);
CREATE INDEX IF NOT EXISTS idx_inst_country  ON ip.institution(country);
CREATE INDEX IF NOT EXISTS idx_inst_openalex ON ip.institution(openalex_id) WHERE openalex_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_inst_corp     ON ip.institution(corp_code)   WHERE corp_code IS NOT NULL;


-- ── 3. Work ↔ Institution (authored_at) ──────
CREATE TABLE IF NOT EXISTS ip.work_institution (
    openalex_id          VARCHAR(40)  NOT NULL REFERENCES ip.works(openalex_id) ON DELETE CASCADE,
    ror_id               VARCHAR(40)  NOT NULL REFERENCES ip.institution(ror_id) ON DELETE CASCADE,
    author_position      VARCHAR(20),                  -- first | middle | last
    -- 거버넌스
    source               VARCHAR(40)  NOT NULL DEFAULT 'openalex',
    confidence_score     NUMERIC(4,3) NOT NULL DEFAULT 0.950,
    validated_status     VARCHAR(20)  NOT NULL DEFAULT 'validated',
    snapshot_year        SMALLINT,
    extraction_method    VARCHAR(40)  NOT NULL DEFAULT 'api_direct_map',
    schema_version       VARCHAR(8)   NOT NULL DEFAULT '1',
    created_at           TIMESTAMPTZ  NOT NULL DEFAULT now(),
    PRIMARY KEY (openalex_id, ror_id)
);
CREATE INDEX IF NOT EXISTS idx_wi_ror ON ip.work_institution(ror_id);


-- 권한
GRANT USAGE ON SCHEMA ip TO autonexusgraph;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA ip TO autonexusgraph;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA ip TO autonexusgraph;

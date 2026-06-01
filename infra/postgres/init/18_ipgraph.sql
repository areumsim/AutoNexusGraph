-- IPGraph (도메인3) PG 스키마 — PRD v2.2 §12.5 + docs/ipgraph.md SSOT.
--
-- Patent / Assignee / Inventor / CPCCode / Citation 정형 적재. USPTO ODP bulk
-- dataset (PatentsView 후속, 2026-03-20 이관) + KIPRIS Open API + CPC scheme.
--
-- 멱등 — CREATE TABLE IF NOT EXISTS / CREATE INDEX IF NOT EXISTS.

SET client_encoding = 'UTF8';

CREATE SCHEMA IF NOT EXISTS ip;

COMMENT ON SCHEMA ip IS
  'IPGraph 도메인 (도메인3) — 특허·기술혁신. docs/ipgraph.md SSOT';

-- ── Patents ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ip.patents (
    pub_no            VARCHAR PRIMARY KEY,            -- 'KR1020230012345' / 'US11234567B2'
    app_no            VARCHAR,                        -- 출원번호
    title             TEXT,
    abstract          TEXT,
    filing_date       DATE,
    grant_date        DATE,
    kind              VARCHAR(8),                     -- 'A' (출원공개) / 'B1' / 'B2' (등록) ...
    jurisdiction      VARCHAR(8) NOT NULL,            -- 'KR' / 'US' / 'JP' / 'EP' / 'WO'
    source            VARCHAR(32) NOT NULL,           -- 'kipris' / 'uspto_odp' / 'openalex'
    snapshot_year     INT,
    schema_version    VARCHAR,
    created_at        TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_patents_filing_date
    ON ip.patents(filing_date) WHERE filing_date IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_patents_jurisdiction
    ON ip.patents(jurisdiction);
CREATE INDEX IF NOT EXISTS idx_patents_source
    ON ip.patents(source);

-- ── Assignees ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ip.assignees (
    assignee_id       VARCHAR PRIMARY KEY,            -- USPTO assignee_id 또는 KIPRIS applicantNo
    name              TEXT NOT NULL,
    name_norm         TEXT,                           -- normalize (lowercase, 공백/기호 제거)
    country           VARCHAR(8),
    type              VARCHAR(16),                    -- 'company' / 'individual' / 'university' / 'gov'
    wikidata_qid      VARCHAR,
    snapshot_year     INT,
    schema_version    VARCHAR,
    created_at        TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_assignees_name_norm
    ON ip.assignees(name_norm) WHERE name_norm IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_assignees_country
    ON ip.assignees(country) WHERE country IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_assignees_qid
    ON ip.assignees(wikidata_qid) WHERE wikidata_qid IS NOT NULL;

-- ── Inventors ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ip.inventors (
    inventor_id       VARCHAR PRIMARY KEY,
    name              TEXT NOT NULL,
    name_norm         TEXT,
    country           VARCHAR(8),
    schema_version    VARCHAR,
    created_at        TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_inventors_name_norm
    ON ip.inventors(name_norm) WHERE name_norm IS NOT NULL;

-- ── Patent ↔ Assignee / Inventor (다대다) ───────────────────────
CREATE TABLE IF NOT EXISTS ip.patent_assignees (
    pub_no            VARCHAR NOT NULL REFERENCES ip.patents(pub_no) ON DELETE CASCADE,
    assignee_id       VARCHAR NOT NULL REFERENCES ip.assignees(assignee_id) ON DELETE CASCADE,
    sequence          INT,                            -- order in patent
    PRIMARY KEY (pub_no, assignee_id)
);
CREATE INDEX IF NOT EXISTS idx_patent_assignees_assignee
    ON ip.patent_assignees(assignee_id);

CREATE TABLE IF NOT EXISTS ip.patent_inventors (
    pub_no            VARCHAR NOT NULL REFERENCES ip.patents(pub_no) ON DELETE CASCADE,
    inventor_id       VARCHAR NOT NULL REFERENCES ip.inventors(inventor_id) ON DELETE CASCADE,
    sequence          INT,
    PRIMARY KEY (pub_no, inventor_id)
);
CREATE INDEX IF NOT EXISTS idx_patent_inventors_inventor
    ON ip.patent_inventors(inventor_id);

-- ── CPC 분류 체계 (depth ≥ 4: section/class/subclass/maingroup/subgroup) ──
CREATE TABLE IF NOT EXISTS ip.cpc_scheme (
    code              VARCHAR PRIMARY KEY,            -- 'H01M', 'H01M 10/052', etc.
    level             VARCHAR(16) NOT NULL,           -- 'section'|'class'|'subclass'|'maingroup'|'subgroup'
    title             TEXT,
    parent_code       VARCHAR REFERENCES ip.cpc_scheme(code) ON DELETE SET NULL,
    snapshot_year     INT,
    schema_version    VARCHAR,
    created_at        TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_cpc_scheme_parent
    ON ip.cpc_scheme(parent_code) WHERE parent_code IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_cpc_scheme_level
    ON ip.cpc_scheme(level);

CREATE TABLE IF NOT EXISTS ip.patent_cpc (
    pub_no            VARCHAR NOT NULL REFERENCES ip.patents(pub_no) ON DELETE CASCADE,
    cpc_code          VARCHAR NOT NULL REFERENCES ip.cpc_scheme(code) ON DELETE CASCADE,
    primary_flag      BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (pub_no, cpc_code)
);
CREATE INDEX IF NOT EXISTS idx_patent_cpc_code
    ON ip.patent_cpc(cpc_code);

-- ── Citations ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ip.citations (
    citing_pub_no     VARCHAR NOT NULL REFERENCES ip.patents(pub_no) ON DELETE CASCADE,
    cited_pub_no      VARCHAR NOT NULL,               -- cited patent may be outside our adapter scope — no FK
    citation_type     VARCHAR(8),                     -- 'A' (applicant) / 'X' (examiner) / 'P' (patent) ...
    snapshot_year     INT,
    schema_version    VARCHAR,
    PRIMARY KEY (citing_pub_no, cited_pub_no)
);
CREATE INDEX IF NOT EXISTS idx_citations_cited
    ON ip.citations(cited_pub_no);

COMMENT ON TABLE ip.patents IS 'IPGraph 도메인 Patent 마스터 — USPTO ODP / KIPRIS / OpenAlex 합집합';
COMMENT ON TABLE ip.assignees IS '특허 출원인 — corp_entity 브리지 진입점 (ip.assignee_corp_map join)';
COMMENT ON TABLE ip.cpc_scheme IS 'CPC 분류 계층 (depth ≥ 4). 무인증 bulk (USPTO/EPO)';
COMMENT ON TABLE ip.citations IS '특허 인용 네트워크. USPTO ODP citations bulk';

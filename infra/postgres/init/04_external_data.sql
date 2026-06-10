-- ESG / KOSIS / 특허 / 기업집단 / Wiki 보강 데이터 + 운영 메트릭

SET client_encoding = 'UTF8';

-- ── ESG (KCGS 등) ───────────────────────────────────────────────
CREATE SCHEMA IF NOT EXISTS anxg_esg;

CREATE TABLE IF NOT EXISTS anxg_esg.ratings (
    corp_code      CHAR(8)      NOT NULL REFERENCES anxg_master.companies(corp_code),
    year           SMALLINT     NOT NULL,
    source         VARCHAR(20)  NOT NULL,        -- kcgs | sustinvest | msci | ...
    e_grade        VARCHAR(5),                   -- E 등급 (A+ / A / B+ / ...)
    s_grade        VARCHAR(5),
    g_grade        VARCHAR(5),
    total_grade    VARCHAR(5),
    raw            JSONB,
    ingested_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
    PRIMARY KEY (corp_code, year, source)
);
CREATE INDEX IF NOT EXISTS idx_esg_year ON anxg_esg.ratings(year DESC, corp_code);


-- ── KOSIS 산업/거시 통계 (통계청) ────────────────────────────────
-- ECOS 와 별도 테이블 — KOSIS 는 산업/사회 통계 폭이 훨씬 넓다.
CREATE TABLE IF NOT EXISTS anxg_macro.kosis_series (
    stat_code      VARCHAR(40)  NOT NULL,
    item_code      VARCHAR(80)  NOT NULL,
    time           VARCHAR(20)  NOT NULL,        -- A=YYYY / M=YYYYMM / Q=YYYYQN
    cycle          CHAR(1)      NOT NULL,
    value          NUMERIC(28, 6),
    unit           VARCHAR(40),
    stat_name      VARCHAR(300),
    item_name      VARCHAR(300),
    raw            JSONB,
    PRIMARY KEY (stat_code, item_code, time)
);
CREATE INDEX IF NOT EXISTS idx_kosis_stat_time ON anxg_macro.kosis_series(stat_code, time);


-- ── 특허 (KIPRIS) ───────────────────────────────────────────────
CREATE SCHEMA IF NOT EXISTS anxg_ip;

CREATE TABLE IF NOT EXISTS anxg_ip.patents (
    application_no    VARCHAR(20)  PRIMARY KEY,  -- 출원번호
    registration_no   VARCHAR(20),               -- 등록번호 (등록 후)
    corp_code         CHAR(8)      REFERENCES anxg_master.companies(corp_code),
    applicant_name    VARCHAR(300),               -- 출원인 (정규화 전 원본)
    inventor_names    TEXT[],
    title             TEXT,
    abstract          TEXT,
    filing_date       DATE,
    publication_date  DATE,
    registration_date DATE,
    ipc_class         VARCHAR(200),               -- 국제특허분류
    status            VARCHAR(40),                -- 출원 / 공개 / 등록 / 거절 / ...
    raw               JSONB,
    ingested_at       TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_patents_corp_date ON anxg_ip.patents(corp_code, filing_date DESC);
CREATE INDEX IF NOT EXISTS idx_patents_applicant ON anxg_ip.patents(applicant_name);


-- ── 공정위 기업집단 ──────────────────────────────────────────────
-- 그룹은 Neo4j 노드의 SSOT 지만, PG 에도 시계열로 보관 (지정 연도 변화 추적).
CREATE SCHEMA IF NOT EXISTS anxg_ftc;

CREATE TABLE IF NOT EXISTS anxg_ftc.groups (
    group_code        VARCHAR(20),
    group_name        VARCHAR(100) NOT NULL,
    chairman          VARCHAR(100),
    designated_year   SMALLINT     NOT NULL,
    total_assets_krw  NUMERIC(20, 0),
    raw               JSONB,
    PRIMARY KEY (group_name, designated_year)
);

CREATE TABLE IF NOT EXISTS anxg_ftc.group_members (
    group_name        VARCHAR(100) NOT NULL,
    designated_year   SMALLINT     NOT NULL,
    company_name      VARCHAR(300) NOT NULL,    -- 정규화 전 원본
    corp_code         CHAR(8)      REFERENCES anxg_master.companies(corp_code),
    sector            VARCHAR(100),
    representative    VARCHAR(100),
    raw               JSONB,
    PRIMARY KEY (group_name, designated_year, company_name)
);
CREATE INDEX IF NOT EXISTS idx_ftc_members_corp ON anxg_ftc.group_members(corp_code);
CREATE INDEX IF NOT EXISTS idx_ftc_members_year ON anxg_ftc.group_members(designated_year DESC);


-- ── Wikipedia / Wikidata 보강 ───────────────────────────────────
CREATE SCHEMA IF NOT EXISTS anxg_wiki;

CREATE TABLE IF NOT EXISTS anxg_wiki.wikipedia_pages (
    corp_code        CHAR(8)      NOT NULL REFERENCES anxg_master.companies(corp_code),
    lang             VARCHAR(10)  NOT NULL,        -- ko / en
    title            VARCHAR(300) NOT NULL,
    page_id          BIGINT,
    revision_id      BIGINT,
    extract          TEXT,                         -- summary
    infobox          JSONB,
    last_modified    TIMESTAMPTZ,
    ingested_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    PRIMARY KEY (corp_code, lang)
);

CREATE TABLE IF NOT EXISTS anxg_wiki.wikidata_facts (
    corp_code        CHAR(8)      NOT NULL REFERENCES anxg_master.companies(corp_code),
    qid              VARCHAR(40)  NOT NULL,
    property         VARCHAR(40)  NOT NULL,        -- P31 / P127 (owned by) / P169 (CEO) / ...
    value            TEXT         NOT NULL,
    value_type       VARCHAR(40),                  -- item / string / time / quantity
    value_qid        VARCHAR(40),                  -- value 가 item 이면 QID
    valid_from       DATE,
    valid_until      DATE,
    raw              JSONB,
    PRIMARY KEY (corp_code, qid, property, value)
);
CREATE INDEX IF NOT EXISTS idx_wdfacts_prop ON anxg_wiki.wikidata_facts(property);


-- ── 법령 (LAW.go.kr) ────────────────────────────────────────────
CREATE SCHEMA IF NOT EXISTS anxg_law;

CREATE TABLE IF NOT EXISTS anxg_law.laws (
    law_id           VARCHAR(50)  PRIMARY KEY,    -- 법령일련번호 또는 MST
    law_name         VARCHAR(300) NOT NULL,
    law_name_short   VARCHAR(200),
    law_type         VARCHAR(50),                 -- 법률 / 시행령 / 시행규칙
    promulgation_no  VARCHAR(50),
    promulgation_date DATE,
    enforcement_date  DATE,
    ministry         VARCHAR(100),
    raw              JSONB,
    ingested_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_laws_ministry ON anxg_law.laws(ministry);


-- ── SEC EDGAR (한국 ADR) ────────────────────────────────────────
CREATE SCHEMA IF NOT EXISTS anxg_sec;

CREATE TABLE IF NOT EXISTS anxg_sec.filings (
    accession_no     VARCHAR(20)  PRIMARY KEY,    -- 0001193125-...
    cik              VARCHAR(10)  NOT NULL,
    corp_code        CHAR(8)      REFERENCES anxg_master.companies(corp_code),
    company_name     VARCHAR(300),
    form_type        VARCHAR(20),                 -- 20-F / 6-K / SC 13G / ...
    filed_at         DATE,
    period_of_report DATE,
    primary_doc_url  VARCHAR(1000),
    raw              JSONB
);
CREATE INDEX IF NOT EXISTS idx_sec_corp ON anxg_sec.filings(corp_code, filed_at DESC);
CREATE INDEX IF NOT EXISTS idx_sec_cik  ON anxg_sec.filings(cik);


-- ── GLEIF LEI ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS anxg_sec.lei (
    lei              CHAR(20)     PRIMARY KEY,    -- LEI 코드 20자리
    corp_code        CHAR(8)      REFERENCES anxg_master.companies(corp_code),
    legal_name       VARCHAR(300),
    legal_jurisdiction VARCHAR(10),               -- KR / US / ...
    entity_status    VARCHAR(20),                 -- ACTIVE / INACTIVE
    registration_status VARCHAR(20),
    issued_at        DATE,
    next_renewal_at  DATE,
    raw              JSONB
);


-- ── 운영 메트릭 ─────────────────────────────────────────────────
CREATE SCHEMA IF NOT EXISTS anxg_ops;

CREATE TABLE IF NOT EXISTS anxg_ops.ingest_stats (
    source         VARCHAR(40)  NOT NULL,
    entity_id      VARCHAR(200) NOT NULL,
    status         VARCHAR(20)  NOT NULL,         -- ok | failed | skipped
    attempts       INT          NOT NULL DEFAULT 1,
    last_error     TEXT,
    duration_sec   NUMERIC(10, 3),
    updated_at     TIMESTAMPTZ  NOT NULL DEFAULT now(),
    PRIMARY KEY (source, entity_id)
);
CREATE INDEX IF NOT EXISTS idx_ingest_stats_source ON anxg_ops.ingest_stats(source, updated_at DESC);

-- 일별 적재량 스냅샷 (대시보드)
CREATE TABLE IF NOT EXISTS anxg_ops.daily_inventory (
    snapshot_date  DATE         NOT NULL,
    source         VARCHAR(40)  NOT NULL,
    metric         VARCHAR(40)  NOT NULL,         -- raw_files / pg_rows / neo4j_nodes / ...
    value          BIGINT       NOT NULL,
    PRIMARY KEY (snapshot_date, source, metric)
);


-- 데이터 품질 검증 결과 (validate_cross_source.py)
CREATE TABLE IF NOT EXISTS anxg_ops.quality_checks (
    id             BIGSERIAL PRIMARY KEY,
    check_name     VARCHAR(80)  NOT NULL,         -- subsidiary_3way / ceo_2way / name_dedup / ...
    target_id      VARCHAR(200),                  -- corp_code / person internal_id 등
    severity       VARCHAR(10)  NOT NULL,         -- info | warn | error
    message        TEXT,
    details        JSONB,
    detected_at    TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_qchecks_name ON anxg_ops.quality_checks(check_name, detected_at DESC);

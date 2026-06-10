-- 뉴스 + 규제 보도자료 데이터
-- 라이선스 정책: anxg_news.articles 는 메타+요약만 (저작권). FSS·정부 RSS 는 본문 OK.

SET client_encoding = 'UTF8';

-- ── 뉴스 메타 ────────────────────────────────────────────────────
CREATE SCHEMA IF NOT EXISTS anxg_news;

CREATE TABLE IF NOT EXISTS anxg_news.articles (
    article_hash   CHAR(64)     PRIMARY KEY,    -- sha256(source||link)
    source         VARCHAR(40)  NOT NULL,        -- yonhap_economy / mois_press / ...
    guid           VARCHAR(500),
    title          VARCHAR(500) NOT NULL,
    summary        TEXT,                         -- RSS description (요약만 — 민간 RSS)
    body_text      TEXT,                         -- 본문 (정부 RSS 만 — KOGL)
    link           VARCHAR(1000) NOT NULL,
    published_at   TIMESTAMPTZ,
    categories     TEXT[],
    license_tier   VARCHAR(30),                  -- copyrighted | kogl_type1 | ...
    raw            JSONB,
    ingested_at    TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_articles_published ON anxg_news.articles(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_articles_source    ON anxg_news.articles(source, published_at DESC);


-- 기사 ↔ 회사 멘션
CREATE TABLE IF NOT EXISTS anxg_news.article_mentions (
    article_hash   CHAR(64)     NOT NULL REFERENCES anxg_news.articles(article_hash) ON DELETE CASCADE,
    corp_code      CHAR(8)      NOT NULL REFERENCES anxg_master.companies(corp_code),
    extracted_by   VARCHAR(20)  NOT NULL,        -- rule | llm
    confidence     NUMERIC(4,3),
    PRIMARY KEY (article_hash, corp_code)
);
CREATE INDEX IF NOT EXISTS idx_am_corp ON anxg_news.article_mentions(corp_code);


-- 일자별 회사 감성 스냅샷 (집계 — 본문 저장 못해도 가능)
CREATE TABLE IF NOT EXISTS anxg_news.sentiment_snapshots (
    corp_code      CHAR(8)      NOT NULL REFERENCES anxg_master.companies(corp_code),
    snapshot_date  DATE         NOT NULL,
    source         VARCHAR(40)  NOT NULL,
    mention_count  INT          NOT NULL DEFAULT 0,
    sentiment_avg  NUMERIC(5,3),                 -- -1.000 ~ +1.000
    PRIMARY KEY (corp_code, snapshot_date, source)
);
CREATE INDEX IF NOT EXISTS idx_sent_date ON anxg_news.sentiment_snapshots(snapshot_date DESC);


-- ── 금감원·공정위 보도자료/제재 (KOGL — 본문 저장 OK) ──────────
CREATE SCHEMA IF NOT EXISTS anxg_reg;

CREATE TABLE IF NOT EXISTS anxg_reg.fss_press (
    article_id       VARCHAR(50)  PRIMARY KEY,
    title            VARCHAR(500) NOT NULL,
    published_at     DATE         NOT NULL,
    category         VARCHAR(100),
    summary          TEXT,
    body_text        TEXT,                       -- KOGL 1유형 → 저장 OK
    attachment_urls  TEXT[],
    source_url       VARCHAR(1000),
    raw              JSONB,
    ingested_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_fss_press_date ON anxg_reg.fss_press(published_at DESC);

CREATE TABLE IF NOT EXISTS anxg_reg.fss_press_mentions (
    article_id     VARCHAR(50)  NOT NULL REFERENCES anxg_reg.fss_press(article_id) ON DELETE CASCADE,
    corp_code      CHAR(8)      NOT NULL REFERENCES anxg_master.companies(corp_code),
    extracted_by   VARCHAR(20)  NOT NULL,
    confidence     NUMERIC(4,3),
    PRIMARY KEY (article_id, corp_code)
);


-- 제재 이벤트 (rule-based 추출)
CREATE TABLE IF NOT EXISTS anxg_reg.sanctions (
    event_id       UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    corp_code      CHAR(8)      REFERENCES anxg_master.companies(corp_code),
    event_date     DATE         NOT NULL,
    event_type     VARCHAR(100) NOT NULL,         -- 과징금 / 시정명령 / 영업정지 / ...
    amount_krw     NUMERIC(20, 0),
    description    TEXT,
    source         VARCHAR(40)  NOT NULL,         -- fss_disclosure / ftc_actions / ...
    source_id      VARCHAR(100),                  -- 원본 article_id 등
    raw            JSONB
);
CREATE INDEX IF NOT EXISTS idx_sanctions_corp ON anxg_reg.sanctions(corp_code, event_date DESC);

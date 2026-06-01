-- AutoGraph — 제조사 IR / 뉴스룸 (오픈 공시 본문) 적재.
--
-- 사용자 의제 (Phase B1): "DART 사업보고서 본문 + IR/뉴스룸 크롤링 — KG
-- 프로젝트(MANUFACTURED_AT, 공급망 위험) 관점에서 오픈 채널 중 제일 값진
-- 채널". 공장 위치·CAPA·모델 배정 발표를 본문에서 추출.
--
-- 원천:
--   www.hyundai.com/worldwide/ko/company/ir/  (한국·영문 IR)
--   www.mobis.com/news/, mobis.co.kr/news/ + /ir/
--   (Kia 한국: robots.txt Disallow — 비활성)
--
-- 라이선스: ``src/autonexusgraph/ingestion/_license.py::OEM_NEWSROOM_POLICY`` 가
-- robots.txt + ToS 기반 정책 강제. 본문 저장 'public_partial' — 출처 표기 의무.
--
-- PRD §3.5: 공식 IR = B 등급 (0.80).
--
-- 멱등: UNIQUE (oem, url).

SET client_encoding = 'UTF8';

CREATE SCHEMA IF NOT EXISTS auto;

CREATE TABLE IF NOT EXISTS auto.events_oem_news (
    news_id           BIGSERIAL    PRIMARY KEY,
    oem               VARCHAR(20)  NOT NULL,        -- 'hyundai' | 'mobis' | 'kia'
    oem_corp_code     VARCHAR(8),                   -- DART corp_code (선택)
    url               TEXT         NOT NULL,
    title             TEXT,
    published_date    DATE,
    section           VARCHAR(80),                  -- 'ir/public_disclosure' | 'ir/quarterly_earnings' | 'news/press' 등
    body_text         TEXT,                         -- 추출된 본문 (HTML → text)
    body_text_len     INTEGER GENERATED ALWAYS AS (
        CASE WHEN body_text IS NULL THEN 0
             ELSE length(body_text) END
    ) STORED,
    body_html_path    TEXT,                         -- 디스크에 저장된 raw HTML 경로 (감사용)
    -- 거버넌스
    source            VARCHAR(40)  NOT NULL,        -- 'hyundai_ir' | 'mobis_ir' | 'mobis_news'
    fetched_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
    snapshot_year     SMALLINT,
    confidence_score  NUMERIC(4,3) NOT NULL DEFAULT 0.800,    -- B 등급
    validated_status  VARCHAR(20)  NOT NULL DEFAULT 'validated',
    extraction_method VARCHAR(40)  NOT NULL DEFAULT 'sitemap_crawler',
    license_tier      VARCHAR(20)  NOT NULL DEFAULT 'public_partial',
    raw               JSONB        NOT NULL DEFAULT '{}'::jsonb,
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
    UNIQUE (oem, url)
);
CREATE INDEX IF NOT EXISTS idx_oem_news_oem        ON auto.events_oem_news(oem);
CREATE INDEX IF NOT EXISTS idx_oem_news_date       ON auto.events_oem_news(published_date);
CREATE INDEX IF NOT EXISTS idx_oem_news_section    ON auto.events_oem_news(section);
CREATE INDEX IF NOT EXISTS idx_oem_news_corp       ON auto.events_oem_news(oem_corp_code)
    WHERE oem_corp_code IS NOT NULL;


-- 권한
GRANT USAGE ON SCHEMA auto TO autonexusgraph;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA auto TO autonexusgraph;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA auto TO autonexusgraph;

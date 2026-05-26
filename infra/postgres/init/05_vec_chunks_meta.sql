-- vec.chunks 메타 보강 — RAG filter 풍부화.
-- 추가:
--   source        — dart / wikipedia / fss_press / ...
--   fiscal_year   — 해당 청크의 회계연도 (필터/시점 검색)
--   report_type   — 사업/반기/분기 (DART 보고서) 또는 'wikipedia'
-- 멱등: IF NOT EXISTS.

SET client_encoding = 'UTF8';

ALTER TABLE vec.chunks
  ADD COLUMN IF NOT EXISTS source        VARCHAR(40),
  ADD COLUMN IF NOT EXISTS fiscal_year   SMALLINT,
  ADD COLUMN IF NOT EXISTS report_type   VARCHAR(40);

-- source 기본값 백필 — 기존 데이터는 section 으로 추정.
UPDATE vec.chunks
   SET source = CASE
                  WHEN section LIKE 'wikipedia%' THEN 'wikipedia'
                  ELSE 'dart'
                END
 WHERE source IS NULL;

-- DART chunk 의 fiscal_year / report_type 백필 — fin.filings 와 조인.
-- 보고서 코드 → report_type 매핑:
--   11011 = annual_business   (사업보고서)
--   11012 = half_year         (반기보고서)
--   11013 = quarterly_q1
--   11014 = quarterly_q3
UPDATE vec.chunks vc
   SET fiscal_year = EXTRACT(YEAR FROM f.rcept_dt)::SMALLINT,
       report_type = CASE
                       WHEN f.report_nm LIKE '사업보고서%'     THEN 'annual_business'
                       WHEN f.report_nm LIKE '반기보고서%'     THEN 'half_year'
                       WHEN f.report_nm LIKE '분기보고서%'     THEN 'quarterly'
                       WHEN f.report_nm LIKE '주요사항보고서%' THEN 'major_event'
                       ELSE 'other'
                     END
  FROM fin.filings f
 WHERE vc.rcept_no = f.rcept_no
   AND vc.fiscal_year IS NULL;

-- Wikipedia 청크의 report_type 표시.
UPDATE vec.chunks
   SET report_type = 'wikipedia'
 WHERE source = 'wikipedia'
   AND report_type IS NULL;

-- RAG 필터 인덱스. 부분 인덱스로 NULL 제외.
CREATE INDEX IF NOT EXISTS idx_chunks_year_corp
  ON vec.chunks(fiscal_year, corp_code)
  WHERE embedding IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_chunks_source_section
  ON vec.chunks(source, section);

-- 메타 컬럼 적재 통계
DO $$
DECLARE
  total       BIGINT;
  with_year   BIGINT;
  by_source   TEXT;
BEGIN
  SELECT count(*) INTO total FROM vec.chunks;
  SELECT count(*) INTO with_year FROM vec.chunks WHERE fiscal_year IS NOT NULL;
  RAISE NOTICE 'vec.chunks total=%, with fiscal_year=%', total, with_year;
END $$;

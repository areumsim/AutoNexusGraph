-- ════════════════════════════════════════════════════════════════════
-- 27_auto_kamp_catalog.sql — KAMP 제조AI 데이터셋 카탈로그 (data.go.kr 15089213)
-- ════════════════════════════════════════════════════════════════════
-- KAMP 포털(kamp-ai.kr) 본체 50종 데이터셋의 **메타·링크 인덱스**.
-- 본 테이블은 카탈로그(인덱스)이며, 실제 공정 센서 통계는 별도 `auto.process_metrics`
-- (source='kamp_15089213') 에 적재된다 (25_auto_process_metrics.sql, Layer B).
--
-- 본 테이블은 회사 비귀속(corp_code 없음). KAMP 전 데이터셋은 익명 B 등급(0.80).
-- PERFORMED_AT 금지 — load_performed_at.py allowlist 가 자동 차단.
--
-- 7키 메타 풀 적재 (source_type/source_id/confidence_score/validated_status/
-- snapshot_year/extraction_method/schema_version) — 기존 로더 갭(extraction_method,
-- confidence_score, validated_status 누락) 메우는 표준 사례.
--
-- hot-apply:  make migrate-schema-pg MIGRATE_FILE=27_auto_kamp_catalog.sql
-- ════════════════════════════════════════════════════════════════════

SET client_encoding = 'UTF8';

CREATE SCHEMA IF NOT EXISTS auto;

CREATE TABLE IF NOT EXISTS auto.kamp_catalog (
    catalog_id        BIGSERIAL    PRIMARY KEY,
    -- 카탈로그 원본 식별 (연번 + 기준년도)
    seq               SMALLINT     NOT NULL,                  -- 연번 1..50
    base_year         SMALLINT     NOT NULL,                  -- 기준년도 (2020/2021/2022)
    -- 분류
    industry          VARCHAR(40)  NOT NULL,                  -- 뿌리(주조)/정밀가공/사출성형/...
    purpose           VARCHAR(60),                            -- 예지보전/품질보증/공정최적화/공급망최적화
    process_name_raw  VARCHAR(120) NOT NULL,                  -- KAMP 원문 ("다이캐스팅 공정")
    process_name_norm VARCHAR(80),                            -- 정규화 ("die_casting") — 산단공 :Process 매핑
    process_category  VARCHAR(40),                            -- auto.process_metrics 와 동일 분류 (casting/forging/...)
    -- 데이터셋 메타
    dataset_name      VARCHAR(160) NOT NULL,
    dataset_desc      TEXT,
    data_type         VARCHAR(10),                            -- csv/jpg/bmp/txt/wav
    usage_terms       VARCHAR(60),                            -- "콘텐츠 변경허용" 등
    download_url      VARCHAR(200),                            -- 현재 단일 https://www.kamp-ai.kr/aidataList
    -- 7키 표준 메타 (governance) — 다른 로더의 갭 메우는 첫 표준
    source            VARCHAR(40)  NOT NULL DEFAULT 'datagokr_kamp_15089213',
    source_type       VARCHAR(40)  NOT NULL DEFAULT 'kamp_manufacturing',   -- 가이드 §2.1
    source_id         VARCHAR(60),                            -- 'kamp:15089213/<seq>'
    confidence_score  NUMERIC(4,3) NOT NULL DEFAULT 0.800,    -- B 등급 (익명)
    validated_status  VARCHAR(20)  NOT NULL DEFAULT 'candidate', -- 본체 적재 검증 후 'validated' 승격
    snapshot_year     SMALLINT     NOT NULL,
    extraction_method VARCHAR(20)  NOT NULL DEFAULT 'deterministic',
    schema_version    VARCHAR(20)  NOT NULL DEFAULT 'kamp_catalog_v1',
    raw               JSONB        NOT NULL DEFAULT '{}'::jsonb,
    ingested_at       TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
    UNIQUE (source, seq, base_year)
);

CREATE INDEX IF NOT EXISTS idx_auto_kamp_catalog_industry
    ON auto.kamp_catalog(industry);
CREATE INDEX IF NOT EXISTS idx_auto_kamp_catalog_process_norm
    ON auto.kamp_catalog(process_name_norm) WHERE process_name_norm IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_auto_kamp_catalog_purpose
    ON auto.kamp_catalog(purpose) WHERE purpose IS NOT NULL;

COMMENT ON TABLE auto.kamp_catalog IS
    'KAMP 제조AI 데이터셋 50종 카탈로그 (data.go.kr 15089213). 본체는 auto.process_metrics. corp_code 없음 = 회사 비귀속. grade B(0.80).';

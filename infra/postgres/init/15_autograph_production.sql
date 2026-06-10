-- AutoGraph — DART 사업보고서 "생산 및 설비" 섹션 추출 데이터.
--
-- 한국 상장 OEM 의 공장(법인)별 생산능력·생산실적·가동률을 PRD v2.1 의
-- MANUFACTURED_AT (Manufacturer ↔ Plant) 보강 데이터로 적재.
--
-- 원천: data/raw/dart_bulk/corp/<corp_code>/documents/<rcept_no>.zip 의 사업보고서 XML.
-- 추출기: src/autograph/extractors/dart_production_parser.py
-- 로더:   src/autograph/loaders/load_dart_production.py
--
-- PRD §3.5 신뢰도: DART = B 등급 (공식 공시) — confidence 0.80 기본.
-- MVP 의도적 제한: 차량부문 행만 적재 (상용·위탁생산 제외) — 이는 사업보고서
-- 자체의 "차량부문 / 금융부문" 구분과 일치.
--
-- 멱등: 모든 CREATE 은 IF NOT EXISTS. ON CONFLICT 키는 (corp_code, plant_name, snapshot_year).

SET client_encoding = 'UTF8';

CREATE SCHEMA IF NOT EXISTS anxg_auto;

-- ── 1. 공장별 생산능력 ───────────────────────────────────────────
-- DART 사업보고서 "(1) 생산능력" 표. 단위: 대 (vehicle 수).
CREATE TABLE IF NOT EXISTS anxg_auto.plant_capacity (
    capacity_id        BIGSERIAL       PRIMARY KEY,
    corp_code          VARCHAR(8)      NOT NULL,       -- 부모 사 (DART corp_code)
    business_division  VARCHAR(40),                    -- 차량부문 / 금융부문 ...
    plant_code         VARCHAR(40)     NOT NULL,       -- 법인 약어 (HMC/HMMA/HMI/...)
    plant_region       VARCHAR(40),                    -- 한국 / 북미 / 유럽 / 아시아 ...
    snapshot_year      SMALLINT        NOT NULL,
    capacity_units     BIGINT,                         -- 연간 생산능력 (대)
    unit               VARCHAR(20)     DEFAULT 'vehicles',
    -- 거버넌스
    source             VARCHAR(40)     NOT NULL DEFAULT 'dart_business_report',
    source_rcept_no    VARCHAR(20),                    -- DART 접수번호
    confidence_score   NUMERIC(4,3)    NOT NULL DEFAULT 0.800,    -- B 등급
    validated_status   VARCHAR(20)     NOT NULL DEFAULT 'validated',
    extraction_method  VARCHAR(40)     NOT NULL DEFAULT 'dart_xml_table_parser',
    raw                JSONB           NOT NULL DEFAULT '{}'::jsonb,
    created_at         TIMESTAMPTZ     NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ     NOT NULL DEFAULT now(),
    UNIQUE (corp_code, plant_code, snapshot_year)
);
CREATE INDEX IF NOT EXISTS idx_auto_capacity_corp ON anxg_auto.plant_capacity(corp_code);
CREATE INDEX IF NOT EXISTS idx_auto_capacity_year ON anxg_auto.plant_capacity(snapshot_year);


-- ── 2. 공장별 생산실적 ───────────────────────────────────────────
-- DART 사업보고서 "(2) 생산실적" 표. 보통 (단위: 대, 억원) — 본 표는 대 수만.
CREATE TABLE IF NOT EXISTS anxg_auto.plant_production (
    production_id      BIGSERIAL       PRIMARY KEY,
    corp_code          VARCHAR(8)      NOT NULL,
    business_division  VARCHAR(40),
    plant_code         VARCHAR(40)     NOT NULL,
    plant_region       VARCHAR(40),
    snapshot_year      SMALLINT        NOT NULL,
    actual_units       BIGINT,                         -- 실제 생산 (대)
    unit               VARCHAR(20)     DEFAULT 'vehicles',
    -- 거버넌스 (capacity 와 동일)
    source             VARCHAR(40)     NOT NULL DEFAULT 'dart_business_report',
    source_rcept_no    VARCHAR(20),
    confidence_score   NUMERIC(4,3)    NOT NULL DEFAULT 0.800,
    validated_status   VARCHAR(20)     NOT NULL DEFAULT 'validated',
    extraction_method  VARCHAR(40)     NOT NULL DEFAULT 'dart_xml_table_parser',
    raw                JSONB           NOT NULL DEFAULT '{}'::jsonb,
    created_at         TIMESTAMPTZ     NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ     NOT NULL DEFAULT now(),
    UNIQUE (corp_code, plant_code, snapshot_year)
);
CREATE INDEX IF NOT EXISTS idx_auto_production_corp ON anxg_auto.plant_production(corp_code);
CREATE INDEX IF NOT EXISTS idx_auto_production_year ON anxg_auto.plant_production(snapshot_year);


-- ── 3. 공장별 가동률 ────────────────────────────────────────────
-- DART 사업보고서 "(3) 가동률" 표. 단위: 시간 (실가동시간 / 가능가동시간 * 100).
CREATE TABLE IF NOT EXISTS anxg_auto.plant_utilization (
    utilization_id     BIGSERIAL       PRIMARY KEY,
    corp_code          VARCHAR(8)      NOT NULL,
    business_division  VARCHAR(40),
    plant_code         VARCHAR(40)     NOT NULL,
    snapshot_year      SMALLINT        NOT NULL,
    utilization_pct    NUMERIC(6,2),                   -- 가동률 % (0~999.99)
    actual_hours       NUMERIC(15,2),                  -- 실가동시간
    available_hours    NUMERIC(15,2),                  -- 가능가동시간
    -- 거버넌스
    source             VARCHAR(40)     NOT NULL DEFAULT 'dart_business_report',
    source_rcept_no    VARCHAR(20),
    confidence_score   NUMERIC(4,3)    NOT NULL DEFAULT 0.800,
    validated_status   VARCHAR(20)     NOT NULL DEFAULT 'validated',
    extraction_method  VARCHAR(40)     NOT NULL DEFAULT 'dart_xml_table_parser',
    raw                JSONB           NOT NULL DEFAULT '{}'::jsonb,
    created_at         TIMESTAMPTZ     NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ     NOT NULL DEFAULT now(),
    UNIQUE (corp_code, plant_code, snapshot_year)
);
CREATE INDEX IF NOT EXISTS idx_auto_util_corp ON anxg_auto.plant_utilization(corp_code);
CREATE INDEX IF NOT EXISTS idx_auto_util_year ON anxg_auto.plant_utilization(snapshot_year);


-- ── 4. 산단공 자동차 부품 제조업 공정 합성데이터 (15151075) ────────
-- 한국산업단지공단이 자동차 부품 제조 공정 (섀시·엔진·내장 등) 의 통계적 특성을
-- 모방한 합성 데이터. **실제 공장과 직접 연결 불가** — 본 테이블은 공정명
-- taxonomy + :Process 노드 사전으로만 사용. 라이선스: data.go.kr 무제한.
--
-- PRD §1.2 / §3.5: 합성 데이터 = C 등급 (0.50) — 단독 근거 금지.
--    실제 제조 공정 데이터는 영업비밀이라 오픈 거의 없음. 본 데이터는
--    어디까지나 "공정명 정규형 사전" 으로만 가치 있음 (사용자 명시).
CREATE TABLE IF NOT EXISTS anxg_auto.processes (
    process_id         BIGSERIAL       PRIMARY KEY,
    factory_manage_no  VARCHAR(40)     NOT NULL,       -- 공장관리번호 (합성)
    industry_code      VARCHAR(20),                    -- 업종코드 (KSIC)
    industry_level     SMALLINT,                       -- 업종차수
    process_map_name   VARCHAR(200),                   -- 공정도명 (예: '자동차 내장 부품 제조업 생산공정')
    process_map_desc   TEXT,                           -- 공정도설명
    process_order      SMALLINT,                       -- 공정순서
    process_name       VARCHAR(120)    NOT NULL,       -- 공정명 (예: '전처리', '스프레이도장')
    process_name_norm  VARCHAR(120)    NOT NULL,       -- 정규형 (lowercase + 공백 정리)
    process_desc       TEXT,                           -- 공정설명
    -- 거버넌스
    source             VARCHAR(40)     NOT NULL DEFAULT 'datagokr_15151075',
    confidence_score   NUMERIC(4,3)    NOT NULL DEFAULT 0.500,    -- C 등급 (합성 데이터)
    validated_status   VARCHAR(20)     NOT NULL DEFAULT 'candidate',
    extraction_method  VARCHAR(40)     NOT NULL DEFAULT 'csv_direct_map',
    snapshot_year      SMALLINT,
    raw                JSONB           NOT NULL DEFAULT '{}'::jsonb,
    created_at         TIMESTAMPTZ     NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ     NOT NULL DEFAULT now(),
    UNIQUE (factory_manage_no, process_order, process_name)
);
CREATE INDEX IF NOT EXISTS idx_auto_processes_name      ON anxg_auto.processes(process_name_norm);
CREATE INDEX IF NOT EXISTS idx_auto_processes_industry  ON anxg_auto.processes(industry_code);
CREATE INDEX IF NOT EXISTS idx_auto_processes_map_name  ON anxg_auto.processes(process_map_name);


-- 권한 (다른 init script 와 동일 패턴)
GRANT USAGE ON SCHEMA auto TO autonexusgraph;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA auto TO autonexusgraph;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA auto TO autonexusgraph;

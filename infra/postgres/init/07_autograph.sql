-- AutoGraph 자동차 도메인 스키마 (PRD v2.0 AutoGraph).
-- 원칙:
--   * 정량 수치·공식 데이터는 LLM이 생성하지 않고 본 테이블 조회 결과만 인용.
--   * 모든 정형 데이터는 source/confidence/validated_status/snapshot_year 동봉.
--   * candidate 관계는 validated_status='candidate', confidence<1.0 로만 적재.
--   * BOM 깊이 MVP: Manufacturer → VehicleModel → VehicleVariant(model_year+trim) → System → Component.
--   * raw JSONB 보존 → 재가공·감사 가능.
--
-- 멱등: 모든 CREATE 은 IF NOT EXISTS.
-- 외래키: anxg_master.companies 와 직접 연결하지 않음 — Cross-Domain 매핑은 anxg_bridge.corp_entity 경유.

SET client_encoding = 'UTF8';

CREATE SCHEMA IF NOT EXISTS anxg_auto;

-- ── 1. 제조사 마스터 ─────────────────────────────────────────────
-- NHTSA vPIC 의 MakeId, Wikidata QID, K-LEI 등 외부 식별자는 별도 컬럼/bridge 로 관리.
CREATE TABLE IF NOT EXISTS anxg_auto.master_manufacturers (
    manufacturer_id    BIGINT          PRIMARY KEY,        -- NHTSA MakeId 우선, 외부 없으면 자체 seq(>=10^9)
    name               VARCHAR(200)    NOT NULL,
    name_norm          VARCHAR(200)    NOT NULL,           -- normalize_corp_name() 결과 — 매칭 보조
    country            VARCHAR(40),
    wikidata_qid       VARCHAR(40),
    aliases            TEXT[]          NOT NULL DEFAULT '{}',
    source             VARCHAR(40)     NOT NULL,           -- 'nhtsa_vpic' | 'wikidata' | 'manual'
    source_ref         VARCHAR(200),                       -- 원천 식별자 (예: NHTSA MakeId)
    confidence         NUMERIC(4,3)    NOT NULL DEFAULT 1.000,
    validated_status   VARCHAR(20)     NOT NULL DEFAULT 'verified',   -- 'verified' | 'candidate' | 'rejected'
    snapshot_year      SMALLINT,
    valid_from         DATE,
    valid_to           DATE,
    raw                JSONB           NOT NULL DEFAULT '{}'::jsonb,
    created_at         TIMESTAMPTZ     NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ     NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_auto_mfr_norm  ON anxg_auto.master_manufacturers(name_norm);
CREATE INDEX IF NOT EXISTS idx_auto_mfr_qid   ON anxg_auto.master_manufacturers(wikidata_qid);
CREATE INDEX IF NOT EXISTS idx_auto_mfr_src   ON anxg_auto.master_manufacturers(source, source_ref);


-- ── 2. 차종(모델) 마스터 ────────────────────────────────────────
-- 한 모델은 (제조사 × 이름 × 마켓) 조합으로 유일. model_year 는 variant 에서 관리.
CREATE TABLE IF NOT EXISTS anxg_auto.master_vehicle_models (
    model_id           BIGSERIAL       PRIMARY KEY,
    manufacturer_id    BIGINT          NOT NULL REFERENCES anxg_auto.master_manufacturers(manufacturer_id),
    name               VARCHAR(200)    NOT NULL,
    name_norm          VARCHAR(200)    NOT NULL,
    market             VARCHAR(20),                        -- 'KR' | 'US' | 'EU' | 'GLOBAL' | NULL
    wikidata_qid       VARCHAR(40),
    aliases            TEXT[]          NOT NULL DEFAULT '{}',
    source             VARCHAR(40)     NOT NULL,
    source_ref         VARCHAR(200),
    confidence         NUMERIC(4,3)    NOT NULL DEFAULT 1.000,
    validated_status   VARCHAR(20)     NOT NULL DEFAULT 'verified',
    snapshot_year      SMALLINT,
    valid_from         DATE,
    valid_to           DATE,
    raw                JSONB           NOT NULL DEFAULT '{}'::jsonb,
    created_at         TIMESTAMPTZ     NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ     NOT NULL DEFAULT now(),
    UNIQUE (manufacturer_id, name_norm, market)
);
CREATE INDEX IF NOT EXISTS idx_auto_model_mfr   ON anxg_auto.master_vehicle_models(manufacturer_id);
CREATE INDEX IF NOT EXISTS idx_auto_model_norm  ON anxg_auto.master_vehicle_models(name_norm);
CREATE INDEX IF NOT EXISTS idx_auto_model_qid   ON anxg_auto.master_vehicle_models(wikidata_qid);


-- ── 3. 트림/연식 마스터 (variant) ───────────────────────────────
CREATE TABLE IF NOT EXISTS anxg_auto.master_vehicle_variants (
    variant_id         BIGSERIAL       PRIMARY KEY,
    model_id           BIGINT          NOT NULL REFERENCES anxg_auto.master_vehicle_models(model_id),
    model_year         SMALLINT        NOT NULL,
    trim               VARCHAR(120),
    body_class         VARCHAR(80),                        -- 'Sedan' | 'SUV' | 'Hatchback' | ...
    fuel_type          VARCHAR(40),                        -- 'Gasoline' | 'Diesel' | 'EV' | 'HEV' | ...
    drive_type         VARCHAR(40),                        -- 'FWD' | 'RWD' | 'AWD' | '4WD'
    transmission       VARCHAR(40),
    source             VARCHAR(40)     NOT NULL,
    source_ref         VARCHAR(200),
    confidence         NUMERIC(4,3)    NOT NULL DEFAULT 1.000,
    validated_status   VARCHAR(20)     NOT NULL DEFAULT 'verified',
    snapshot_year      SMALLINT,
    raw                JSONB           NOT NULL DEFAULT '{}'::jsonb,
    created_at         TIMESTAMPTZ     NOT NULL DEFAULT now()
);
-- UNIQUE 제약에 expression(COALESCE) 사용 불가 → 부분 unique index 로 (NULL 도 동일 키 취급).
CREATE UNIQUE INDEX IF NOT EXISTS uq_auto_var_key
  ON anxg_auto.master_vehicle_variants
  (model_id, model_year, COALESCE(trim, ''), COALESCE(fuel_type, ''));
CREATE INDEX IF NOT EXISTS idx_auto_var_model  ON anxg_auto.master_vehicle_variants(model_id, model_year);
CREATE INDEX IF NOT EXISTS idx_auto_var_year   ON anxg_auto.master_vehicle_variants(model_year);


-- ── 4. 제원 측정값 (long format) ────────────────────────────────
-- 차량 단위 정량 수치는 모두 본 테이블 (LLM 생성 금지).
-- measure_key 표준 (네임스페이스 권장):
--   spec.engine.displacement_cc / spec.engine.power_kw / spec.battery.capacity_kwh /
--   spec.dim.length_mm / spec.dim.wheelbase_mm / spec.weight.curb_kg /
--   spec.range.wltp_km / spec.efficiency.fuel_l_per_100km / safety.airbags_count ...
CREATE TABLE IF NOT EXISTS anxg_auto.spec_measurements (
    id                 BIGSERIAL       PRIMARY KEY,
    variant_id         BIGINT          NOT NULL REFERENCES anxg_auto.master_vehicle_variants(variant_id),
    measure_key        VARCHAR(120)    NOT NULL,
    value_num          NUMERIC(20, 4),
    value_text         VARCHAR(400),
    unit               VARCHAR(40),
    source             VARCHAR(40)     NOT NULL,           -- 'nhtsa_vpic' | 'oem_brochure' | 'wikidata' | ...
    source_ref         VARCHAR(300),
    confidence         NUMERIC(4,3)    NOT NULL DEFAULT 1.000,
    validated_status   VARCHAR(20)     NOT NULL DEFAULT 'verified',
    snapshot_year      SMALLINT,
    raw                JSONB           NOT NULL DEFAULT '{}'::jsonb,
    created_at         TIMESTAMPTZ     NOT NULL DEFAULT now(),
    UNIQUE (variant_id, measure_key, source)
);
CREATE INDEX IF NOT EXISTS idx_auto_spec_var_key ON anxg_auto.spec_measurements(variant_id, measure_key);
CREATE INDEX IF NOT EXISTS idx_auto_spec_key     ON anxg_auto.spec_measurements(measure_key);


-- ── 5. 부품 마스터 ─────────────────────────────────────────────
-- BOM 깊이 MVP 한정 — 시스템(System code) + 컴포넌트 명칭만.
-- system_code 예: ENGINE / TRANSMISSION / BRAKE / STEERING / SUSPENSION / ELECTRICAL /
--                  BATTERY / INFOTAINMENT / SAFETY / BODY / INTERIOR / EXTERIOR
CREATE TABLE IF NOT EXISTS anxg_auto.components (
    component_id       BIGSERIAL       PRIMARY KEY,
    canonical_name     VARCHAR(200)    NOT NULL,
    name_norm          VARCHAR(200)    NOT NULL,
    system_code        VARCHAR(40)     NOT NULL,
    aliases            TEXT[]          NOT NULL DEFAULT '{}',
    wikidata_qid       VARCHAR(40),
    source             VARCHAR(40)     NOT NULL DEFAULT 'manual',
    confidence         NUMERIC(4,3)    NOT NULL DEFAULT 1.000,
    validated_status   VARCHAR(20)     NOT NULL DEFAULT 'verified',
    notes              TEXT,
    created_at         TIMESTAMPTZ     NOT NULL DEFAULT now(),
    UNIQUE (canonical_name, system_code)
);
CREATE INDEX IF NOT EXISTS idx_auto_comp_sys  ON anxg_auto.components(system_code);
CREATE INDEX IF NOT EXISTS idx_auto_comp_norm ON anxg_auto.components(name_norm);


-- ── 6. 리콜 이벤트 ──────────────────────────────────────────────
-- NHTSA Recalls API / car.go.kr / KATRI 등. 원천 ID 가 다르므로 (source, source_recall_no) UNIQUE.
CREATE TABLE IF NOT EXISTS anxg_auto.events_recalls (
    recall_id          BIGSERIAL       PRIMARY KEY,
    source             VARCHAR(40)     NOT NULL,           -- 'nhtsa' | 'car_go_kr' | 'katri' | ...
    source_recall_no   VARCHAR(80)     NOT NULL,           -- NHTSA NHTSACampaignNumber 등
    manufacturer_id    BIGINT          REFERENCES anxg_auto.master_manufacturers(manufacturer_id),
    model_id           BIGINT          REFERENCES anxg_auto.master_vehicle_models(model_id),
    variant_id         BIGINT          REFERENCES anxg_auto.master_vehicle_variants(variant_id),
    component_text     VARCHAR(400),                       -- 원문 부품 표기 (정규화 전)
    component_id       BIGINT          REFERENCES anxg_auto.components(component_id),
    defect_summary     TEXT,
    consequence        TEXT,
    remedy_summary     TEXT,
    report_date        DATE,
    country            VARCHAR(8),                         -- ISO 3166-1 alpha-2 (US / KR ...)
    affected_units     BIGINT,
    confidence         NUMERIC(4,3)    NOT NULL DEFAULT 1.000,
    validated_status   VARCHAR(20)     NOT NULL DEFAULT 'verified',
    snapshot_year      SMALLINT,
    raw                JSONB           NOT NULL DEFAULT '{}'::jsonb,
    ingested_at        TIMESTAMPTZ     NOT NULL DEFAULT now(),
    UNIQUE (source, source_recall_no)
);
CREATE INDEX IF NOT EXISTS idx_auto_rec_var       ON anxg_auto.events_recalls(variant_id);
CREATE INDEX IF NOT EXISTS idx_auto_rec_model     ON anxg_auto.events_recalls(model_id);
CREATE INDEX IF NOT EXISTS idx_auto_rec_mfr_date  ON anxg_auto.events_recalls(manufacturer_id, report_date DESC);
CREATE INDEX IF NOT EXISTS idx_auto_rec_country   ON anxg_auto.events_recalls(country);


-- ── 7. 결함 신고 / 소비자 불만 ─────────────────────────────────
-- NHTSA Complaints API — 텍스트 본문은 anxg_vec.chunks 에 청크 단위로도 인덱싱.
CREATE TABLE IF NOT EXISTS anxg_auto.events_complaints (
    complaint_id       BIGSERIAL       PRIMARY KEY,
    source             VARCHAR(40)     NOT NULL,
    source_complaint_no VARCHAR(80)    NOT NULL,
    variant_id         BIGINT          REFERENCES anxg_auto.master_vehicle_variants(variant_id),
    model_id           BIGINT          REFERENCES anxg_auto.master_vehicle_models(model_id),
    manufacturer_id    BIGINT          REFERENCES anxg_auto.master_manufacturers(manufacturer_id),
    components         TEXT[]          NOT NULL DEFAULT '{}',
    summary            TEXT,
    filed_date         DATE,
    incident_date      DATE,
    country            VARCHAR(8),
    confidence         NUMERIC(4,3)    NOT NULL DEFAULT 1.000,
    validated_status   VARCHAR(20)     NOT NULL DEFAULT 'verified',
    snapshot_year      SMALLINT,
    raw                JSONB           NOT NULL DEFAULT '{}'::jsonb,
    ingested_at        TIMESTAMPTZ     NOT NULL DEFAULT now(),
    UNIQUE (source, source_complaint_no)
);
CREATE INDEX IF NOT EXISTS idx_auto_cmp_var    ON anxg_auto.events_complaints(variant_id);
CREATE INDEX IF NOT EXISTS idx_auto_cmp_filed  ON anxg_auto.events_complaints(filed_date DESC);


-- ── 8. 코멘트 ─────────────────────────────────────────────────
COMMENT ON SCHEMA auto IS 'AutoGraph 자동차 도메인 마스터·이벤트 (PRD v2.0).';
COMMENT ON TABLE  anxg_auto.master_manufacturers   IS '자동차 제조사 (OEM·부품사). source/confidence/validated_status 동봉.';
COMMENT ON TABLE  anxg_auto.master_vehicle_models  IS '차종(모델) — 제조사+이름+마켓 UNIQUE.';
COMMENT ON TABLE  anxg_auto.master_vehicle_variants IS '트림/연식 — model_year + trim + fuel_type 단위.';
COMMENT ON TABLE  anxg_auto.spec_measurements      IS '차량 제원 long format. LLM 은 본 테이블 결과만 인용.';
COMMENT ON TABLE  anxg_auto.components             IS '부품/시스템 마스터 (MVP 깊이).';
COMMENT ON TABLE  anxg_auto.events_recalls         IS '리콜 이벤트 — NHTSA·car.go.kr·KATRI 통합.';
COMMENT ON TABLE  anxg_auto.events_complaints      IS '결함 신고/컴플레인 이벤트.';

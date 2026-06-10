-- anxg_master.entities — 다형(polymorphic) Entity Resolution 마스터.
-- PRD §4.5 v2.1 신설. 법인·차량·부품·리콜·표준·플랜트 모두 하나의 행으로 식별.
--
-- v2.0 의 `anxg_master.companies` + `anxg_master.entity_map` 분리 구조는 그대로 유지
-- (도메인 코드가 의존). 이 테이블은 그 위에 폴리모픽 레이어로 얹는 형태이며,
-- 마이그레이션은 scripts/migrate/migrate_entity_map_to_entities.py 가 멱등 적재.
--
-- entities.corp_code 가 채워진 행 = anxg_bridge.corp_entity 의 대상.

SET client_encoding = 'UTF8';

CREATE TABLE IF NOT EXISTS anxg_master.entities (
    entity_id         VARCHAR(64)  PRIMARY KEY,        -- prefix + seq (예: 'mfr_000123')
    entity_type       VARCHAR(20)  NOT NULL,
    canonical_name    VARCHAR(300) NOT NULL,
    canonical_name_en VARCHAR(300),
    -- 외부 식별자 (entity_type 별로 일부만 채워짐)
    wikidata_qid      VARCHAR(40),
    lei               VARCHAR(20),                     -- 법인만 (20자 ISO 17442)
    corp_code         CHAR(8),                         -- 한국 상장사 / AutoNexusGraph 연동 키
    business_no       VARCHAR(20),                     -- 한국 사업자등록번호 (000-00-00000)
    cik               VARCHAR(10),                     -- SEC 등록 법인
    nhtsa_model_id    VARCHAR(40),                     -- 차량 모델
    nhtsa_campaign_id VARCHAR(40),                     -- NHTSA 리콜
    car_go_kr_id      VARCHAR(40),                     -- 한국 리콜
    -- 메타
    source_priority   INT          NOT NULL DEFAULT 1, -- 1=primary, 2=alias, 3=secondary
    confidence_score  NUMERIC(4,3) NOT NULL DEFAULT 1.000,
    valid_from        DATE,
    valid_to          DATE,
    schema_version    VARCHAR(10)  NOT NULL DEFAULT 'v2.1',
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT chk_entities_type CHECK (entity_type IN (
        'manufacturer', 'supplier', 'vehicle_model', 'vehicle_variant',
        'component', 'recall', 'standard', 'plant'
    )),
    CONSTRAINT chk_entities_validity CHECK (valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from),
    CONSTRAINT chk_entities_confidence CHECK (confidence_score BETWEEN 0.000 AND 1.000)
);

-- 인덱스 — PRD §4.5 + 운영 보강
CREATE INDEX IF NOT EXISTS idx_entities_type    ON anxg_master.entities(entity_type);
CREATE INDEX IF NOT EXISTS idx_entities_qid     ON anxg_master.entities(wikidata_qid)      WHERE wikidata_qid      IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_entities_corp    ON anxg_master.entities(corp_code)         WHERE corp_code         IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_entities_lei     ON anxg_master.entities(lei)               WHERE lei               IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_entities_bizno   ON anxg_master.entities(business_no)       WHERE business_no       IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_entities_cik     ON anxg_master.entities(cik)               WHERE cik               IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_entities_nhtsa_m ON anxg_master.entities(nhtsa_model_id)    WHERE nhtsa_model_id    IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_entities_nhtsa_c ON anxg_master.entities(nhtsa_campaign_id) WHERE nhtsa_campaign_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_entities_carkr   ON anxg_master.entities(car_go_kr_id)      WHERE car_go_kr_id      IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_entities_name    ON anxg_master.entities(canonical_name);

-- 자연키 유일성 — 같은 외부 ID 로 두 entity 가 생기는 것을 방지 (entity_type 별).
-- NULL 은 PostgreSQL UNIQUE 에서 서로 충돌하지 않으므로 그대로 사용.
CREATE UNIQUE INDEX IF NOT EXISTS uq_entities_type_qid
    ON anxg_master.entities(entity_type, wikidata_qid) WHERE wikidata_qid IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_entities_type_corp
    ON anxg_master.entities(entity_type, corp_code)    WHERE corp_code    IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_entities_type_lei
    ON anxg_master.entities(entity_type, lei)          WHERE lei          IS NOT NULL;

-- updated_at 자동 갱신 트리거 (PostgreSQL 표준 패턴)
CREATE OR REPLACE FUNCTION anxg_master.tg_entities_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS tg_entities_updated_at ON anxg_master.entities;
CREATE TRIGGER tg_entities_updated_at
    BEFORE UPDATE ON anxg_master.entities
    FOR EACH ROW
    EXECUTE FUNCTION anxg_master.tg_entities_set_updated_at();

-- 활성 entity 뷰 — valid_to 가 NULL 이거나 미래.
CREATE OR REPLACE VIEW anxg_master.entities_active AS
SELECT *
  FROM anxg_master.entities
 WHERE valid_to IS NULL OR valid_to > CURRENT_DATE;

-- entity_id 생성 시퀀스 (마이그레이션·로더 공용).
-- 사용 패턴 예: 'mfr_' || lpad(nextval('anxg_master.entities_seq')::text, 6, '0')
CREATE SEQUENCE IF NOT EXISTS anxg_master.entities_seq START 1;

COMMENT ON TABLE anxg_master.entities IS
  'AutoNexusGraph 다형 ER 마스터 (PRD §4.5 v2.1). 법인·차량·부품·리콜·표준·플랜트 통합.';
COMMENT ON COLUMN anxg_master.entities.entity_id IS
  'prefix+seq 형식 권장 (mfr_/sup_/veh_/var_/cmp_/rec_/std_/plt_)';
COMMENT ON COLUMN anxg_master.entities.corp_code IS
  'AutoNexusGraph anxg_master.companies.corp_code 와 동일. 채워진 행 = anxg_bridge.corp_entity 의 대상.';

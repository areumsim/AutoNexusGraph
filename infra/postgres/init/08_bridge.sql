-- Cross-Domain Bridge — FinGraph corp_code ↔ AutoGraph entity (PRD v2.0 §4.6).
-- entity_type 은 도메인 객체 유형 (manufacturer, supplier, vehicle_model, variant 등).
-- 자동 매칭 (Wikidata QID / LEI / 사업자번호 / 정규화 이름) 결과는 reviewed_status='candidate' 로
-- 적재. 사람이 검토하면 'reviewed' / 'rejected' 로 승급/거부.
--
-- 멱등: IF NOT EXISTS. corp_code 는 nullable — 자동차 entity 중 미상장(공급사 등) 도 등록 가능.
-- entity_id 는 string — AutoGraph 의 manufacturer_id / model_id / supplier_id 를 stringify 해서 저장.

SET client_encoding = 'UTF8';

CREATE SCHEMA IF NOT EXISTS bridge;

CREATE TABLE IF NOT EXISTS bridge.corp_entity (
    id                 BIGSERIAL       PRIMARY KEY,
    corp_code          CHAR(8)         REFERENCES master.companies(corp_code),
    entity_id          VARCHAR(64)     NOT NULL,
    entity_type        VARCHAR(30)     NOT NULL,
        -- 'manufacturer' | 'supplier' | 'vehicle_model' | 'variant' | 'recall'
    name               VARCHAR(300),
    wikidata_qid       VARCHAR(40),
    lei                CHAR(20),
    cik                VARCHAR(20),
    business_no        VARCHAR(40),                        -- 한국 사업자번호 (jurir_no / bizr_no)
    match_method       VARCHAR(20)     NOT NULL,
        -- 'wikidata_qid' | 'lei' | 'cik' | 'business_no' | 'name_exact' | 'name_fuzzy' | 'manual'
    confidence_score   NUMERIC(4,3)    NOT NULL DEFAULT 0.500,
    valid_from         DATE,
    valid_to           DATE,
    reviewed_status    VARCHAR(20)     NOT NULL DEFAULT 'candidate',
        -- 'candidate' | 'reviewed' | 'rejected'
    notes              TEXT,
    raw                JSONB           NOT NULL DEFAULT '{}'::jsonb,
    created_at         TIMESTAMPTZ     NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ     NOT NULL DEFAULT now()
);

-- 한 (corp_code, entity_type, entity_id) 조합당 1행. 미상장 entity 도 corp_code=NULL 로 유일하지 않을 수 있어
-- 부분 unique index 로 NULL 안전 처리.
CREATE UNIQUE INDEX IF NOT EXISTS uq_bridge_corp_entity
  ON bridge.corp_entity (COALESCE(corp_code, ''), entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_bridge_corp     ON bridge.corp_entity(corp_code, entity_type);
CREATE INDEX IF NOT EXISTS idx_bridge_entity   ON bridge.corp_entity(entity_id, entity_type);
CREATE INDEX IF NOT EXISTS idx_bridge_qid      ON bridge.corp_entity(wikidata_qid);
CREATE INDEX IF NOT EXISTS idx_bridge_reviewed ON bridge.corp_entity(reviewed_status);

COMMENT ON SCHEMA bridge IS 'Cross-Domain Bridge — FinGraph corp_code ↔ AutoGraph/기타 도메인 entity 매핑.';
COMMENT ON TABLE  bridge.corp_entity IS
  'corp_code ↔ entity_id 매핑. 자동 매칭은 candidate, 사람 검토 후 reviewed 로 승급.';

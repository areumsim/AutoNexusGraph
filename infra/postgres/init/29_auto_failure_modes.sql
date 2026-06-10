-- ════════════════════════════════════════════════════════════════════
-- 29_auto_failure_modes.sql — :FailureMode 노드 + MANIFESTS_AS Bridge
-- ════════════════════════════════════════════════════════════════════
-- Layer 1 (회사무관 설비 고장모드 taxonomy). 가이드 §1.x/§2.3 핵심.
--   (:Equipment)-[:SUBJECT_TO]->(:FailureMode)-[:MANIFESTS_AS]->(:DefectType)
--   (:ProcessStep)-[:CAN_CAUSE]->(:FailureMode)
--
-- 시드 추출 경로: NASA PCoE readme/문헌 텍스트 (회전기계 베어링, EV 배터리,
-- IGBT 전력반도체) → Claude Code Agent 추출 → ~15~20 :FailureMode 노드.
-- 시계열 raw 는 적재 안 함 (가이드 §2.3: 패턴만 노드 속성).
--
-- :Equipment 는 정규화 카테고리 컬럼으로 보유 (별도 테이블 보류 — bearing/battery/
-- igbt/turbofan 등 ~10개라 컬럼 충분). Neo4j 측에서 DISTINCT 로 :Equipment 노드 시드.
--
-- 등급:
--   NASA PCoE (공식) → A (0.80). 단 자동차 비귀속 (항공 엔진/일반 설비).
--   bridge MANIFESTS_AS 는 측정값 (cos_sim) 또는 LLM 라벨이라 conf 별도.
--
-- hot-apply:  make migrate-schema-pg MIGRATE_FILE=29_auto_failure_modes.sql
-- ════════════════════════════════════════════════════════════════════

SET client_encoding = 'UTF8';

CREATE SCHEMA IF NOT EXISTS anxg_auto;

-- ──────────────────────────────────────────────────────────────────────
-- :FailureMode — 회사무관 고장모드 (Layer 1)
-- ──────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS anxg_auto.failure_modes (
    fm_id             BIGSERIAL    PRIMARY KEY,
    name              VARCHAR(120) NOT NULL,                  -- snake_case (예: 'bearing_inner_race_spalling')
    name_en           VARCHAR(160),                            -- 자연 영문
    name_ko           VARCHAR(160),                            -- 한국어
    description       TEXT,                                    -- 메커니즘 1문장
    symptom           TEXT,                                    -- 가이드 §2.2 schema 호환 — 관측 가능 증상
    component_hint    VARCHAR(200),                            -- 어느 부품에서 주로 나타나는지
    equipment         VARCHAR(40),                             -- 'bearing' | 'battery' | 'igbt' | 'turbofan' | ...
    representative_text TEXT,                                  -- BGE-M3 임베딩 소스 (verbatim from readme)
    embedding         VECTOR(1024),                            -- BGE-M3 (TEI) 1024-dim, nullable backfill
    -- 7키 표준 메타
    source            VARCHAR(40)  NOT NULL DEFAULT 'nasa_pcoe',
    source_type       VARCHAR(40)  NOT NULL DEFAULT 'readme_text_extraction',
    source_id         VARCHAR(60),                             -- 'pcoe:bearing#inner_race_spalling'
    confidence_score  NUMERIC(4,3) NOT NULL DEFAULT 0.800,    -- A 등급 (NASA 공식)
    validated_status  VARCHAR(20)  NOT NULL DEFAULT 'candidate',
    snapshot_year     SMALLINT,
    extraction_method VARCHAR(20)  NOT NULL DEFAULT 'llm',
    schema_version    VARCHAR(20)  NOT NULL DEFAULT 'failure_mode_v1',
    raw               JSONB        NOT NULL DEFAULT '{}'::jsonb,
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
    UNIQUE (name)
);

CREATE INDEX IF NOT EXISTS idx_failure_modes_equipment
    ON anxg_auto.failure_modes(equipment) WHERE equipment IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_failure_modes_validated
    ON anxg_auto.failure_modes(validated_status);

COMMENT ON TABLE anxg_auto.failure_modes IS
    '회사무관 설비 고장모드 (Layer 1). NASA PCoE readme + KAMP 추출. corp_code 없음. grade A(0.80) 공식.';


-- ──────────────────────────────────────────────────────────────────────
-- MANIFESTS_AS — (:FailureMode) → (:DefectType) Bridge
-- ──────────────────────────────────────────────────────────────────────
-- 의미: "이 고장모드는 보통 이런 결함 유형으로 발현된다"
-- LLM 또는 BGE-M3 코사인. validated_status='candidate' → 사람 검토 후 'reviewed'.

CREATE TABLE IF NOT EXISTS anxg_auto.failure_mode_manifestations (
    manif_id          BIGSERIAL    PRIMARY KEY,
    fm_id             BIGINT       NOT NULL REFERENCES anxg_auto.failure_modes(fm_id),
    defect_type_id    BIGINT       NOT NULL REFERENCES anxg_auto.defect_types(defect_type_id),
    cos_sim           NUMERIC(5,4),                            -- NULL for llm_assign
    match_method      VARCHAR(20)  NOT NULL,                   -- 'llm_assign' | 'cosine_topk'
    rank              SMALLINT,
    -- 7키 표준 메타
    source            VARCHAR(40)  NOT NULL DEFAULT 'bridge_manifestations',
    source_type       VARCHAR(40)  NOT NULL,                   -- 'llm_label' | 'bge_m3_cosine'
    source_id         VARCHAR(60),
    confidence_score  NUMERIC(4,3) NOT NULL,
    validated_status  VARCHAR(20)  NOT NULL DEFAULT 'candidate',
    snapshot_year     SMALLINT,
    extraction_method VARCHAR(20)  NOT NULL,
    schema_version    VARCHAR(20)  NOT NULL DEFAULT 'manifestations_v1',
    raw               JSONB        NOT NULL DEFAULT '{}'::jsonb,
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
    UNIQUE (fm_id, defect_type_id, match_method)
);

CREATE INDEX IF NOT EXISTS idx_manifestations_fm
    ON anxg_auto.failure_mode_manifestations(fm_id);
CREATE INDEX IF NOT EXISTS idx_manifestations_dt
    ON anxg_auto.failure_mode_manifestations(defect_type_id);
CREATE INDEX IF NOT EXISTS idx_manifestations_topk
    ON anxg_auto.failure_mode_manifestations(fm_id, rank) WHERE rank IS NOT NULL;

COMMENT ON TABLE anxg_auto.failure_mode_manifestations IS
    'Bridge — :FailureMode(설비 고장모드) ↔ :DefectType(결함 유형). LLM 라벨 + BGE-M3 코사인 두 경로.';

-- ════════════════════════════════════════════════════════════════════
-- 28_auto_defect_matches.sql — :DefectType 노드 + DEFECT_MATCHES Bridge
-- ════════════════════════════════════════════════════════════════════
-- Layer 1 (회사무관 결함 유형 taxonomy) + Bridge (회사귀속 :Recall ↔
-- 회사무관 :DefectType 의미 매칭).
--
-- 가이드 §1.x:
--   (:Recall)-[:DEFECT_MATCHES {cos_sim, confidence}]->(:DefectType)
--   (:Recall)-[:SIMILAR_CASE_OF {cos_sim}]->(:Recall)
--
-- 시드 추출 경로: NHTSA(493) + KOTSA(941) defect_summary 텍스트 1,434건
--   → Claude API 자동 카테고리 라벨링(LLM, grade C, 0.70)
--   → :DefectType 노드 시드 (~30~50개)
--   → DEFECT_MATCHES = (a) LLM 직접 할당 (match_method='llm_assign')
--                    + (b) BGE-M3 코사인 top-k (match_method='cosine_topk')
--
-- 회사 귀속 가드: :DefectType 은 회사 비귀속 (corp_code 없음). 회사귀속은
-- :Recall 쪽이 담당. DEFECT_MATCHES 자체도 의미 측정값(cos_sim)이지 회사 주장 아님.
--
-- hot-apply:  make migrate-schema-pg MIGRATE_FILE=28_auto_defect_matches.sql
-- ════════════════════════════════════════════════════════════════════

SET client_encoding = 'UTF8';

CREATE SCHEMA IF NOT EXISTS anxg_auto;

-- ──────────────────────────────────────────────────────────────────────
-- :DefectType — 회사무관 결함 유형 노드 (Layer 1)
-- ──────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS anxg_auto.defect_types (
    defect_type_id    BIGSERIAL    PRIMARY KEY,
    name              VARCHAR(120) NOT NULL,         -- snake_case 영문 표준 (예: 'fuel_pump_impeller_interference')
    name_en           VARCHAR(160),                  -- 자연어 영문 (예: 'Fuel pump impeller interference')
    name_ko           VARCHAR(160),                  -- 한국어 별칭 (예: '연료펌프 임펠러 간섭')
    description       TEXT,                          -- LLM 산출 카테고리 정의
    category          VARCHAR(40),
        -- 'mechanical' | 'electrical' | 'software' | 'material' | 'assembly' | 'design' | 'process' | 'safety_system'
    representative_text TEXT,                        -- 카테고리 대표 텍스트 (BGE-M3 임베딩 소스)
    embedding         VECTOR(1024),                  -- BGE-M3 (TEI) 1024-dim, nullable (백필)
    -- 7키 표준 메타
    source            VARCHAR(40)  NOT NULL DEFAULT 'recall_text_llm',
    source_type       VARCHAR(40)  NOT NULL DEFAULT 'recall_text_label_extraction',
    source_id         VARCHAR(60),                  -- 'defect_type:<name>'
    confidence_score  NUMERIC(4,3) NOT NULL DEFAULT 0.700,   -- LLM = C 등급
    validated_status  VARCHAR(20)  NOT NULL DEFAULT 'candidate',
    snapshot_year     SMALLINT,
    extraction_method VARCHAR(20)  NOT NULL DEFAULT 'llm',
    schema_version    VARCHAR(20)  NOT NULL DEFAULT 'defect_type_v1',
    raw               JSONB        NOT NULL DEFAULT '{}'::jsonb,
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
    UNIQUE (name)
);

CREATE INDEX IF NOT EXISTS idx_defect_types_category
    ON anxg_auto.defect_types(category) WHERE category IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_defect_types_validated
    ON anxg_auto.defect_types(validated_status);
-- pgvector IVFFlat 인덱스는 데이터 적재 후 별도 CREATE — 빈 테이블에선 의미 없음.

COMMENT ON TABLE anxg_auto.defect_types IS
    '회사무관 결함 유형 taxonomy (Layer 1). NHTSA+KOTSA 리콜 텍스트에서 LLM 라벨링으로 시드 추출. corp_code 없음 — 회사 귀속 금지.';


-- ──────────────────────────────────────────────────────────────────────
-- DEFECT_MATCHES — :Recall ↔ :DefectType 의미 매칭 (Bridge)
-- ──────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS anxg_auto.defect_matches (
    match_id          BIGSERIAL    PRIMARY KEY,
    recall_id         BIGINT       NOT NULL REFERENCES anxg_auto.events_recalls(recall_id),
    defect_type_id    BIGINT       NOT NULL REFERENCES anxg_auto.defect_types(defect_type_id),
    cos_sim           NUMERIC(5,4),                 -- 0..1, NULL for llm_assign
    match_method      VARCHAR(20)  NOT NULL,
        -- 'llm_assign'   — LLM이 카테고리 추출하며 동시에 이 리콜에 할당 (1차)
        -- 'cosine_topk'  — :Recall 청크 임베딩 ↔ :DefectType 임베딩 top-K (확장)
    rank              SMALLINT,                      -- top-k 내 순위 (1=best)
    -- 7키 표준 메타
    source            VARCHAR(40)  NOT NULL DEFAULT 'bridge_defect_matches',
    source_type       VARCHAR(40)  NOT NULL,         -- 'llm_label' | 'bge_m3_cosine'
    source_id         VARCHAR(60),
    confidence_score  NUMERIC(4,3) NOT NULL,
    validated_status  VARCHAR(20)  NOT NULL DEFAULT 'candidate',
    snapshot_year     SMALLINT,
    extraction_method VARCHAR(20)  NOT NULL,         -- 'llm' | 'cosine_topk'
    schema_version    VARCHAR(20)  NOT NULL DEFAULT 'defect_matches_v1',
    raw               JSONB        NOT NULL DEFAULT '{}'::jsonb,
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
    UNIQUE (recall_id, defect_type_id, match_method)
);

CREATE INDEX IF NOT EXISTS idx_defect_matches_recall
    ON anxg_auto.defect_matches(recall_id);
CREATE INDEX IF NOT EXISTS idx_defect_matches_type
    ON anxg_auto.defect_matches(defect_type_id);
CREATE INDEX IF NOT EXISTS idx_defect_matches_method
    ON anxg_auto.defect_matches(match_method, validated_status);
CREATE INDEX IF NOT EXISTS idx_defect_matches_topk
    ON anxg_auto.defect_matches(recall_id, rank) WHERE rank IS NOT NULL;

COMMENT ON TABLE anxg_auto.defect_matches IS
    'Bridge — :Recall(회사귀속,A등급) ↔ :DefectType(회사무관,C등급) 의미 매칭. cos_sim/llm_label 두 경로. 회사 주장이 아니라 측정값.';

-- ════════════════════════════════════════════════════════════════════
-- 25_auto_process_metrics.sql — ProcessGraph 4단계 (패턴·품질, 익명)
-- ════════════════════════════════════════════════════════════════════
-- KAMP 제조AI 데이터셋(data.go.kr 15089213) + AI Hub 품질 통계의 익명/합성
-- 공정 파라미터 분포(cycle_time / yield / defect_rate). **회사 귀속 금지** —
-- 본 테이블에는 corp_code 컬럼이 **의도적으로 없다**(PRD §8). 공정 유형
-- (process_name_norm / category) 단위 통계만 보관. :ProcessStep 통계 속성으로
-- 사용하되 답변 시 "패턴(합성/익명)" 표시. grade B (익명, 0.80).
--
-- hot-apply:  make migrate-schema-pg MIGRATE_FILE=25_auto_process_metrics.sql
-- ════════════════════════════════════════════════════════════════════

CREATE SCHEMA IF NOT EXISTS auto;

CREATE TABLE IF NOT EXISTS auto.process_metrics (
    metric_id          BIGSERIAL       PRIMARY KEY,
    -- 공정 유형 단위 (회사 아님). process_name_norm 은 :Process taxonomy 키와 정렬.
    process_name_norm  VARCHAR(120),
    process_category   VARCHAR(40),    -- casting|forging|stamping|welding|coating|machining|assembly|inspection
    metric_type        VARCHAR(30)     NOT NULL,   -- 'cycle_time' | 'yield' | 'defect_rate'
    unit               VARCHAR(20),                -- 'sec' | 'pct' | 'ppm' …
    -- 분포 통계 (개별 레코드 아님 — 익명화)
    value_mean         NUMERIC(12,4),
    value_p50          NUMERIC(12,4),
    value_p95          NUMERIC(12,4),
    value_std          NUMERIC(12,4),
    sample_count       INTEGER,
    -- governance (auto.processes 패턴 — 단, corp_code 없음 = 회사 비귀속)
    source             VARCHAR(40)     NOT NULL DEFAULT 'kamp_15089213',
    confidence_score   NUMERIC(4,3)    NOT NULL DEFAULT 0.800,    -- B 등급 (익명·합성)
    validated_status   VARCHAR(20)     NOT NULL DEFAULT 'validated',
    snapshot_year      SMALLINT,
    raw                JSONB           NOT NULL DEFAULT '{}'::jsonb,
    created_at         TIMESTAMPTZ     NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ     NOT NULL DEFAULT now(),
    UNIQUE (process_name_norm, process_category, metric_type, source, snapshot_year)
);

CREATE INDEX IF NOT EXISTS idx_auto_process_metrics_norm
    ON auto.process_metrics(process_name_norm);
CREATE INDEX IF NOT EXISTS idx_auto_process_metrics_cat
    ON auto.process_metrics(process_category);

COMMENT ON TABLE auto.process_metrics IS
    'KAMP/AI Hub 익명 공정 파라미터 분포 (cycle_time/yield/defect). 회사 귀속 금지 — corp_code 컬럼 없음 (PRD_process_graph §8). grade B(0.80) 익명.';

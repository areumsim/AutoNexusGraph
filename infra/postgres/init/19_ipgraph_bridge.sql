-- IPGraph Bridge — anxg_ip.assignee_corp_map (PRD v2.2 §12.5 + docs/ipgraph.md §4).
--
-- 신규 join 테이블. **anxg_bridge.corp_entity 직접 변경 0** — core/bridge 스키마 변경 0
-- → §10.12 "코어 변경 < 5%" 보존. supplier candidate 4,792 row 운영 SOP (auto/manual/
-- reviewed 흐름) 와 동일 패턴 재사용.
--
-- 멱등.

SET client_encoding = 'UTF8';

CREATE TABLE IF NOT EXISTS anxg_ip.assignee_corp_map (
    assignee_id       VARCHAR NOT NULL REFERENCES anxg_ip.assignees(assignee_id) ON DELETE CASCADE,
    corp_code         CHAR(8) NOT NULL REFERENCES anxg_master.companies(corp_code) ON DELETE CASCADE,  -- finance anxg_bridge.corp_entity 와 동일 패턴
    match_type        VARCHAR(16) NOT NULL,              -- 'qid' | 'business_no' | 'lei' | 'name' | 'manual'
    confidence_score  NUMERIC NOT NULL CHECK (confidence_score >= 0 AND confidence_score <= 1),
    reviewed_status   VARCHAR(16) DEFAULT 'auto',        -- 'auto' | 'reviewed' | 'rejected'
    reviewed_by       VARCHAR,
    reviewed_at       TIMESTAMPTZ,
    schema_version    VARCHAR,
    created_at        TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (assignee_id, corp_code)
);

CREATE INDEX IF NOT EXISTS idx_assignee_corp_map_corp
    ON anxg_ip.assignee_corp_map(corp_code);
CREATE INDEX IF NOT EXISTS idx_assignee_corp_map_status
    ON anxg_ip.assignee_corp_map(reviewed_status, confidence_score DESC);

COMMENT ON TABLE anxg_ip.assignee_corp_map IS
  'IPGraph assignee → finance corp_code 브리지 (PRD v2.2 §12.5). anxg_bridge.corp_entity 직접 변경 0 — core 스키마 보존.';

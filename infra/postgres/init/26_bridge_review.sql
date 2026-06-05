-- Bridge candidate 검토 운영 (Q-1) — anxg_bridge.corp_entity 검토 감사 컬럼 + 인덱스.
--
-- 08_bridge.sql 의 reviewed_status (candidate/reviewed/rejected) 운영을 위한 보강:
-- 누가/언제 검토했는지 추적 + 미검토 stale 스캔·진행률 KPI 인덱스.
-- 멱등 (ADD COLUMN/INDEX IF NOT EXISTS) — hot-apply 안전.

SET client_encoding = 'UTF8';

ALTER TABLE anxg_bridge.corp_entity
  ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMPTZ;          -- 검토(승급/거부) 시각
ALTER TABLE anxg_bridge.corp_entity
  ADD COLUMN IF NOT EXISTS reviewed_by VARCHAR(100);          -- 검토자 (사람 id / 'auto-expire')

-- stale 스캔 (미검토 candidate 를 created_at 순) + 진행률 KPI 집계용.
CREATE INDEX IF NOT EXISTS idx_bridge_status_created
  ON anxg_bridge.corp_entity(reviewed_status, created_at);

COMMENT ON COLUMN anxg_bridge.corp_entity.reviewed_at IS '검토(reviewed/rejected) 확정 시각. NULL = 미검토 candidate.';
COMMENT ON COLUMN anxg_bridge.corp_entity.reviewed_by IS '검토 주체 — 사람 reviewer id 또는 auto-expire (Q-1 자동 거부).';

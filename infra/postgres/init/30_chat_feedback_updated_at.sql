-- 30_chat_feedback_updated_at.sql
-- anxg_chat.feedback.updated_at 컬럼 신규 — 첫 작성 시각(created_at) 과
-- 마지막 갱신(rating 변경, 코멘트 보강) 시각 분리.
--
-- 배경: 기존 UI `record_feedback` 의 ON CONFLICT 가 `SET created_at = now()` 로
-- 첫 작성 시각을 덮어쓰는 의미적 오류 (E-4 분석 routine 의 "최근 N일" 집계가
-- 갱신 사건과 신규 사건을 구분 못 함).
--
-- 마이그: 멱등 (IF NOT EXISTS). 기존 row 의 updated_at 은 created_at 으로 초기화.
-- 후속: UI record_feedback 의 ON CONFLICT 가 created_at 보존 + updated_at = now()
-- 로 정정 (별도 PR).

ALTER TABLE anxg_chat.feedback
  ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();

-- 기존 row backfill — updated_at 가 default(now) 로 채워졌으면 created_at 으로 보정.
-- 신규 row 는 default 가 자연스럽게 동일.
UPDATE anxg_chat.feedback
   SET updated_at = created_at
 WHERE updated_at IS NULL OR updated_at > created_at;

CREATE INDEX IF NOT EXISTS idx_feedback_updated ON anxg_chat.feedback(updated_at DESC);

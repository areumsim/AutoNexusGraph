-- anxg_vec.chunks 에 AutoGraph 메타 컬럼 추가 — RAG 필터 풍부화.
-- 기존 finance 청크는 NULL → 영향 없음. 도메인 무관 retrieve 도 함께 통과.
-- 멱등: IF NOT EXISTS.

SET client_encoding = 'UTF8';

ALTER TABLE anxg_vec.chunks
  ADD COLUMN IF NOT EXISTS manufacturer_id BIGINT,
  ADD COLUMN IF NOT EXISTS model_id        BIGINT,
  ADD COLUMN IF NOT EXISTS variant_id      BIGINT;

-- corp_code 는 자동차 청크에서 매핑되지 않은 OEM 도 있을 수 있어 NULL 허용으로 완화.
-- 기존 finance 청크에는 영향 없음 (이미 NOT NULL 로 채워져 있음).
ALTER TABLE anxg_vec.chunks ALTER COLUMN corp_code DROP NOT NULL;

-- 자동차 청크 필터 인덱스 (manufacturer_id 가 있는 행만 대상).
CREATE INDEX IF NOT EXISTS idx_chunks_auto_mfr
  ON anxg_vec.chunks(manufacturer_id, model_id, variant_id)
  WHERE manufacturer_id IS NOT NULL;

-- source 값 컨벤션 (auto 도메인):
--   'nhtsa_recall'    — 리콜 텍스트 청크
--   'nhtsa_complaint' — 컴플레인 텍스트 청크
--   'wikipedia_auto'  — 차종/제조사 위키 본문
COMMENT ON COLUMN anxg_vec.chunks.manufacturer_id IS 'AutoGraph 제조사 — anxg_auto.master_manufacturers.manufacturer_id';
COMMENT ON COLUMN anxg_vec.chunks.model_id        IS 'AutoGraph 차종 — anxg_auto.master_vehicle_models.model_id';
COMMENT ON COLUMN anxg_vec.chunks.variant_id      IS 'AutoGraph 변형 — anxg_auto.master_vehicle_variants.variant_id';

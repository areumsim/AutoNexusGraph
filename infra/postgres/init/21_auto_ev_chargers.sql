-- AutoGraph — EV 충전 인프라 (data.go.kr B552584/B553530).
--
-- 사용자 의제: auto 도메인의 EV 확장. Operator(운영기관) → anxg_bridge.corp_entity 로
-- "충전 인프라 운영사 ↔ 재무" cross-domain. 이미 보유한 DATA_GO_KR_API_KEY 재사용.
--
-- 원천:
--   B552584 (한국환경공단) — 전국 충전소 위치·운영정보 (운영기관·충전기타입·용량·설치년도)
--   B553530 (한국에너지공단) — 지역별 급속충전기 설치현황·실제 이용량
--
-- 라이선스: 공공.
--
-- PRD §3.5: 공공 (data.go.kr) = A 등급 → confidence 0.950.
--
-- 그래프 흡수:
--   (:ChargingStation {station_id, operator, charger_type, capacity_kw, install_year, sido, gungu})
--   (:Operator)-[:OPERATES {snapshot_year}]->(:ChargingStation)
--   (:Operator)-[:IS_ENTITY]->(anxg_bridge.corp_entity)
--
-- 멱등: PRIMARY KEY (station_id) / (snapshot_year, sido, gungu).
--
-- 상태: 슬롯 (ingestion 코드 미구현, 예정).

SET client_encoding = 'UTF8';

CREATE SCHEMA IF NOT EXISTS anxg_auto;

-- ── 1. 전국 충전소 위치·운영정보 (B552584, 환경공단) ──────
CREATE TABLE IF NOT EXISTS anxg_auto.ev_chargers (
    station_id           VARCHAR(40)  PRIMARY KEY,    -- 충전소 ID (statId)
    charger_seq          VARCHAR(10),                 -- 충전기 일련번호 (chgerId)
    operator             VARCHAR(120),                -- 운영기관 (busiNm)
    operator_corp_code   VARCHAR(8),                  -- anxg_bridge.corp_entity 매칭 (선택)
    station_name         VARCHAR(200),                -- 충전소명 (statNm)
    charger_type         VARCHAR(20),                 -- AC완속 | DC차데모 | DC콤보 | AC3상 …
    capacity_kw          NUMERIC(6,2),                -- 충전용량 (kW)
    install_year         SMALLINT,                    -- 설치년도
    sido                 VARCHAR(20),                 -- 시·도
    gungu                VARCHAR(40),                 -- 시·군·구
    address              TEXT,
    latitude             NUMERIC(10,7),
    longitude            NUMERIC(10,7),
    -- 거버넌스
    source               VARCHAR(40)  NOT NULL DEFAULT 'datagokr_b552584',
    confidence_score     NUMERIC(4,3) NOT NULL DEFAULT 0.950,
    validated_status     VARCHAR(20)  NOT NULL DEFAULT 'validated',
    extraction_method    VARCHAR(40)  NOT NULL DEFAULT 'api_direct_map',
    raw                  JSONB        NOT NULL DEFAULT '{}'::jsonb,
    created_at           TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_evc_operator     ON anxg_auto.ev_chargers(operator);
CREATE INDEX IF NOT EXISTS idx_evc_corp_code    ON anxg_auto.ev_chargers(operator_corp_code)
    WHERE operator_corp_code IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_evc_install_year ON anxg_auto.ev_chargers(install_year);
CREATE INDEX IF NOT EXISTS idx_evc_sido         ON anxg_auto.ev_chargers(sido);
CREATE INDEX IF NOT EXISTS idx_evc_type         ON anxg_auto.ev_chargers(charger_type);


-- ── 2. 지역별 급속충전기 설치현황·실제 이용량 (B553530, 에너지공단) ──────
CREATE TABLE IF NOT EXISTS anxg_auto.ev_charger_usage (
    snapshot_year        SMALLINT     NOT NULL,
    snapshot_month       SMALLINT     NOT NULL DEFAULT 0,   -- 0 = 연 단위, 1~12 = 월 단위
    sido                 VARCHAR(20)  NOT NULL,
    gungu                VARCHAR(40)  NOT NULL DEFAULT '',  -- '' = 시·도 집계
    fast_charger_count   INTEGER,                            -- 급속충전기 설치 수
    slow_charger_count   INTEGER,                            -- 완속충전기 설치 수
    usage_kwh            BIGINT,                             -- 누적 사용량 (kWh)
    sessions_count       BIGINT,                             -- 충전 세션 수
    -- 거버넌스
    source               VARCHAR(40)  NOT NULL DEFAULT 'datagokr_b553530',
    confidence_score     NUMERIC(4,3) NOT NULL DEFAULT 0.950,
    validated_status     VARCHAR(20)  NOT NULL DEFAULT 'validated',
    extraction_method    VARCHAR(40)  NOT NULL DEFAULT 'api_direct_map',
    raw                  JSONB        NOT NULL DEFAULT '{}'::jsonb,
    created_at           TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ  NOT NULL DEFAULT now(),
    PRIMARY KEY (snapshot_year, snapshot_month, sido, gungu)
);
CREATE INDEX IF NOT EXISTS idx_evu_year ON anxg_auto.ev_charger_usage(snapshot_year);
CREATE INDEX IF NOT EXISTS idx_evu_sido ON anxg_auto.ev_charger_usage(sido);


-- 권한
GRANT USAGE ON SCHEMA auto TO autonexusgraph;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA auto TO autonexusgraph;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA auto TO autonexusgraph;

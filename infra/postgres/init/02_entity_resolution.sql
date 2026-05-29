-- Entity Resolution 마스터 ID 매핑 (AutoNexusGraph 통합 키 체계)
-- 모든 외부 소스(Wikidata/Wikipedia/KRX/SEC/GLEIF/KIPRIS …) 는
-- corp_code 를 마스터 키로 묶는다. mapping 은 별도 테이블로 분리.

SET client_encoding = 'UTF8';

-- 외부 ID 매핑
-- 한 회사가 여러 외부 ID 를 가질 수 있고, 한 외부 ID 가 여러 회사를 가리킬 수도 있다(드물지만 분쟁시).
-- → (corp_code, id_type, id_value) PK + 인덱스로 양방향 빠른 조회.
CREATE TABLE IF NOT EXISTS master.entity_map (
    corp_code      CHAR(8)      NOT NULL REFERENCES master.companies(corp_code),
    id_type        VARCHAR(40)  NOT NULL,
        -- 표준 키:
        -- ticker / wikidata_qid / wikipedia_title / business_no / jurir_no /
        -- lei / cik / ftc_group_code / kipris_applicant_id / sec_ticker / isin
    id_value       VARCHAR(200) NOT NULL,
    source         VARCHAR(40)  NOT NULL,    -- wikidata | wikipedia | krx | sec | gleif | kipris | manual ...
    confidence     NUMERIC(4,3) NOT NULL DEFAULT 1.000,
    resolved_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
    resolved_by    VARCHAR(20)  NOT NULL DEFAULT 'rule',   -- rule | llm | manual
    notes          TEXT,
    PRIMARY KEY (corp_code, id_type, id_value)
);
CREATE INDEX IF NOT EXISTS idx_em_id      ON master.entity_map(id_type, id_value);
CREATE INDEX IF NOT EXISTS idx_em_source  ON master.entity_map(source);

COMMENT ON TABLE master.entity_map IS
  'AutoNexusGraph 마스터 키(corp_code) 와 외부 ID 의 매핑. 한 회사가 여러 외부 ID 보유 가능.';


-- 회사명 별칭 사전 (정규화·fuzzy 매칭 보조)
-- 예: 삼성전자 ↔ Samsung Electronics ↔ (주)삼성전자 ↔ ㈜삼성전자
CREATE TABLE IF NOT EXISTS master.company_aliases (
    alias          VARCHAR(300) NOT NULL,
    alias_norm     VARCHAR(300) NOT NULL,    -- normalize_corp_name() 결과
    corp_code      CHAR(8)      NOT NULL REFERENCES master.companies(corp_code),
    source         VARCHAR(40)  NOT NULL,    -- dart | wikipedia | wikidata | news | manual
    confidence     NUMERIC(4,3) NOT NULL DEFAULT 1.000,
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT now(),
    PRIMARY KEY (alias_norm, corp_code, source)
);
CREATE INDEX IF NOT EXISTS idx_aliases_corp ON master.company_aliases(corp_code);
CREATE INDEX IF NOT EXISTS idx_aliases_norm ON master.company_aliases(alias_norm);


-- 인물 마스터 (동명이인 분리, Neo4j Person 노드와 1:1)
-- DART 임원공시·Wikidata·뉴스에서 모두 같은 internal_id 로 묶는다.
CREATE TABLE IF NOT EXISTS master.persons (
    internal_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    canonical_name VARCHAR(100) NOT NULL,
    birth_year     SMALLINT,
    wikidata_qid   VARCHAR(40),
    aliases        TEXT[]        NOT NULL DEFAULT '{}',
    notes          TEXT,
    created_at     TIMESTAMPTZ   NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ   NOT NULL DEFAULT now(),
    UNIQUE (canonical_name, birth_year)
);
CREATE INDEX IF NOT EXISTS idx_persons_qid  ON master.persons(wikidata_qid);
CREATE INDEX IF NOT EXISTS idx_persons_name ON master.persons(canonical_name);


-- 인물-회사 임원 이력 (시점 포함)
-- Neo4j EXECUTIVE_OF 와 동기화되는 SQL SSOT. Neo4j 가 그래프 탐색용이라면 PG 는 시계열 분석용.
CREATE TABLE IF NOT EXISTS master.person_executive_history (
    id             BIGSERIAL    PRIMARY KEY,
    internal_id    UUID         NOT NULL REFERENCES master.persons(internal_id),
    corp_code      CHAR(8)      NOT NULL REFERENCES master.companies(corp_code),
    role           VARCHAR(50)  NOT NULL,             -- 대표이사 / 사외이사 / 감사위원 / ...
    registered     BOOLEAN,
    since_date     DATE,
    until_date     DATE,
    rcept_no       CHAR(14),                          -- 출처 보고서
    raw            JSONB,
    UNIQUE (internal_id, corp_code, role, since_date, rcept_no)
);
CREATE INDEX IF NOT EXISTS idx_peh_corp   ON master.person_executive_history(corp_code, since_date DESC);
CREATE INDEX IF NOT EXISTS idx_peh_person ON master.person_executive_history(internal_id);

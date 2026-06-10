-- PG 스키마 namespace 마이그레이션 — 기존 스키마에 프로젝트 프리픽스(anxg_) 부여.
--
-- 공유 PostgreSQL 서버에서 AutoNexusGraph 데이터를 타 프로젝트와 분리하기 위해, database
-- 명(autonexusgraph) 격리 위에 스키마 프리픽스를 추가한다. 코드(.py SQL 문자열 / .sql)는 이미
-- anxg_<schema> 를 참조하므로, 기존 적재된 DB 도 본 스크립트로 한 번 rename 해야 일치한다.
--
-- 특징:
--   - 멱등: 원본 스키마가 없으면(이미 rename 됐으면) 각 블록이 조용히 skip.
--   - search_path / 권한은 rename 후에도 보존 (ALTER SCHEMA RENAME 은 객체를 그대로 이동).
--   - LangGraph 체크포인트 스키마 chat → anxg_chat 포함.
--
-- 실행:
--   psql "$POSTGRES_DSN" -f scripts/migrate/rename_pg_schemas_namespace.sql
--   (또는 make 타깃에 연결)
--
-- 주의: 코드 배포 전 DB 백업(docs/operations/backup_dr.md) 권장. 앱 중단 창에서 실행.

DO $$
DECLARE
    s text;
    schemas text[] := ARRAY[
        'auto','bridge','chat','esg','eval','fin','ftc','ip','law','macro',
        'master','news','ops','reg','sec','vec','wiki'
    ];
BEGIN
    FOREACH s IN ARRAY schemas LOOP
        -- 원본 스키마가 존재하고, 타깃(anxg_<s>) 이 아직 없을 때만 rename (멱등).
        IF EXISTS (SELECT 1 FROM information_schema.schemata WHERE schema_name = s)
           AND NOT EXISTS (SELECT 1 FROM information_schema.schemata WHERE schema_name = 'anxg_' || s)
        THEN
            EXECUTE format('ALTER SCHEMA %I RENAME TO %I', s, 'anxg_' || s);
            RAISE NOTICE 'renamed schema % -> anxg_%', s, s;
        ELSE
            RAISE NOTICE 'skip schema % (원본 없음 또는 anxg_% 이미 존재)', s, s;
        END IF;
    END LOOP;
END $$;

-- 검증: 프리픽스 스키마 목록 확인.
--   SELECT schema_name FROM information_schema.schemata WHERE schema_name LIKE 'anxg\_%' ORDER BY 1;

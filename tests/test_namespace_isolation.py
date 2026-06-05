"""공유 DB 멀티테넌시 namespace 격리 헬퍼 회귀 가드.

docs/architecture.md §4.4 의 핵심 규약:
- 단일 토큰 `app_namespace` 에서 모든 스토어 namespace 파생
- PG: `anxg_<schema>` / Neo4j: `Anxg_<Label>` / Qdrant: `<app_namespace>_<base>`
- 관계 타입은 프리픽스 없음 (라벨만 대상)
- 모든 Neo4j 세션은 `get_session()` 으로

본 테스트는 DB 미연결 환경에서도 동작 — 헬퍼·SSOT·마이그 스크립트 구조만 검증.
실제 PG/Neo4j round-trip 은 별도 integration 테스트가 담당.
"""

from __future__ import annotations

import re
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]


# ── 1) config 헬퍼 ───────────────────────────────────────────────────────

def test_pg_schema_uses_app_namespace_prefix():
    from autonexusgraph.config import get_settings
    s = get_settings()
    # 기본 namespace = anxg.
    assert s.app_namespace == "anxg"
    assert s.pg_schema("master") == "anxg_master"
    assert s.pg_schema("auto") == "anxg_auto"
    assert s.pg_schema("ip") == "anxg_ip"
    assert s.pg_schema("vec") == "anxg_vec"


def test_neo4j_label_uses_capitalized_namespace_prefix():
    from autonexusgraph.config import get_settings
    s = get_settings()
    assert s.neo4j_label("Company") == "Anxg_Company"
    assert s.neo4j_label("VehicleModel") == "Anxg_VehicleModel"
    assert s.neo4j_label("Part") == "Anxg_Part"


def test_qdrant_collection_default_and_derived():
    from autonexusgraph.config import get_settings
    from autonexusgraph.db.qdrant import collection_name
    s = get_settings()
    # base="chunks" 는 config qdrant_collection 직접 반환 (env override 가능).
    assert collection_name("chunks") == s.qdrant_collection
    # 다른 base 는 <namespace>_<base>.
    assert collection_name("entities") == f"{s.app_namespace}_entities"
    assert collection_name("specs") == f"{s.app_namespace}_specs"


def test_langgraph_checkpoint_schema_namespaced_by_default():
    from autonexusgraph.config import get_settings
    s = get_settings()
    # PG checkpoint 스키마 기본값도 namespace 프리픽스.
    assert s.langgraph_checkpoint_schema == "anxg_chat"


# ── 2) Neo4j get_session 가드 ────────────────────────────────────────────

def test_get_session_injects_database_when_configured(monkeypatch):
    """neo4j_database 설정 시 driver.session 에 database 주입."""
    from autonexusgraph.db import neo4j as N

    captured = {}

    class _FakeDriver:
        def session(self, **kwargs):
            captured.update(kwargs)
            class _Sess:
                def __enter__(self_): return self_
                def __exit__(self_, *a): pass
            return _Sess()

    monkeypatch.setattr(N, "get_driver", lambda: _FakeDriver())

    # neo4j_database 가 비어있으면 database 키 자체가 들어가지 않아 driver 기본 db 사용.
    from autonexusgraph.config import get_settings
    get_settings.cache_clear()
    monkeypatch.setattr(get_settings(), "neo4j_database", "")
    captured.clear()
    with N.get_session() as _: pass
    assert "database" not in captured

    # neo4j_database 설정 시 주입.
    monkeypatch.setattr(get_settings(), "neo4j_database", "autonexusgraph")
    captured.clear()
    with N.get_session() as _: pass
    assert captured.get("database") == "autonexusgraph"


def test_get_session_respects_explicit_database_kwarg(monkeypatch):
    """호출자가 database= 명시하면 그대로 사용 (테스트 override 보장).

    회귀 가드: namespace 격리 commit fb1c925 의 초기 버전은
    `session(database=db, **kwargs)` 로 명시 kwarg 와 충돌 → TypeError.
    """
    from autonexusgraph.db import neo4j as N

    captured = {}

    class _FakeDriver:
        def session(self, **kwargs):
            captured.update(kwargs)
            class _Sess:
                def __enter__(self_): return self_
                def __exit__(self_, *a): pass
            return _Sess()

    monkeypatch.setattr(N, "get_driver", lambda: _FakeDriver())
    from autonexusgraph.config import get_settings
    monkeypatch.setattr(get_settings(), "neo4j_database", "autonexusgraph")

    captured.clear()
    with N.get_session(database="test_override") as _: pass
    assert captured.get("database") == "test_override", \
        "명시 database kwarg 가 config 보다 우선해야 한다 (multi-kwarg TypeError 회귀 가드)"


# ── 3) Neo4j 마이그 스크립트 NODE_LABELS SSOT 정합 ──────────────────────

def test_relabel_node_labels_derived_from_domain_registry():
    """relabel 스크립트의 NODE_LABELS 가 ontology.domain SSOT 에서 파생되어야 한다.

    회귀 가드: 과거 hardcoded NODE_LABELS 가 _DOMAIN_MAP 과 drift 하면서
    Component/FailureMode/Product 등 누락 사고 발생. 본 테스트가 동기 보장.
    """
    from autonexusgraph.ontology.domain import _DOMAIN_MAP
    from scripts.migrate.relabel_neo4j_namespace import _TEMPLATE_ONLY_LABELS, NODE_LABELS

    expected = (set(_DOMAIN_MAP) | _TEMPLATE_ONLY_LABELS) - {"Sector"}
    assert set(NODE_LABELS) == expected, \
        f"NODE_LABELS drift: expected={expected - set(NODE_LABELS)}, " \
        f"extra={set(NODE_LABELS) - expected}"


def test_relabel_excludes_sector():
    """Sector 는 migrate_neo4j_schema.py 가 → Anxg_Industry 로 폐기 — 중복 방지."""
    from scripts.migrate.relabel_neo4j_namespace import NODE_LABELS
    assert "Sector" not in NODE_LABELS


def test_relabel_includes_template_only_labels():
    """Cell/Product 같이 _DOMAIN_MAP 에 없지만 cypher 템플릿에서 쓰이는 라벨도 포함."""
    from scripts.migrate.relabel_neo4j_namespace import NODE_LABELS
    assert "Cell" in NODE_LABELS
    assert "Product" in NODE_LABELS


# ── 4) PG 마이그 스크립트 스키마 SSOT 정합 ───────────────────────────────

def test_pg_rename_script_covers_all_create_schemas():
    """rename_pg_schemas_namespace.sql 의 스키마 리스트가 init/*.sql 의
    실제 CREATE SCHEMA 와 정합해야 한다 (drift 가드)."""
    rename_sql = (REPO / "scripts" / "migrate"
                  / "rename_pg_schemas_namespace.sql").read_text(encoding="utf-8")
    # ARRAY[...] 안의 schema 이름 추출.
    m = re.search(r"schemas\s+text\[\]\s*:=\s*ARRAY\[([^\]]+)\]",
                  rename_sql, re.DOTALL)
    assert m, "rename SQL 에 schemas ARRAY 선언 없음"
    rename_schemas = set(re.findall(r"'([a-z_]+)'", m.group(1)))

    # init/*.sql 의 CREATE SCHEMA anxg_<x> 추출.
    init_dir = REPO / "infra" / "postgres" / "init"
    created = set()
    for sql in init_dir.glob("*.sql"):
        for m in re.finditer(r"CREATE SCHEMA IF NOT EXISTS\s+anxg_([a-z_]+)",
                              sql.read_text(encoding="utf-8")):
            created.add(m.group(1))

    missing = created - rename_schemas
    rename_schemas - created
    assert not missing, f"rename SQL 에서 누락된 스키마 (init 에는 있음): {missing}"
    # rename 에만 있는 건 OK — 과거 스키마 호환용일 수 있음. 경고만.


# ── 5) Cypher 템플릿 bare 라벨 회귀 가드 ────────────────────────────────

def test_no_bare_labels_in_cypher_templates():
    """src/scripts 의 Cypher 문자열에 bare 라벨이 없어야 한다.

    회귀 가드: namespace 마이그레이션 commit fb1c925 가 6개 파일에서
    `c:Part` / `c:Module` 등 bare 라벨을 놓쳐 (`Anxg_Module OR c:Part`),
    마이그레이션 후 사일런트하게 0건 반환하는 버그 발생.
    """
    import sys
    sys.path.insert(0, str(REPO / "src"))
    from autonexusgraph.ontology.domain import _DOMAIN_MAP

    # 마이그 대상 라벨 = _DOMAIN_MAP + template-only - {Sector}
    template_only = {"Cell", "Product"}
    namespaced_labels = (set(_DOMAIN_MAP) | template_only) - {"Sector"}

    # 엄격: 라벨이 `(`/`[`/`OR ` 직후 또는 변수 뒤 `:` 형태로 와야 cypher 패턴.
    # docstring 자연어의 ` :Module` 같은 표기는 제외.
    pat = re.compile(r'(?:\(|\[)([a-z][a-z0-9_]*)?:([A-Z][A-Za-z_]+)(?=[\s,)}|\]{])')
    pat_or = re.compile(r'\b(?:OR|AND)\s+([a-z][a-z0-9_]*):([A-Z][A-Za-z_]+)(?=[\s,)}|\]{])')
    cypher_kws = ('MATCH (', 'MERGE (', 'OPTIONAL MATCH', 'WHERE (')

    violations = []
    for root in ('src', 'scripts'):
        for p in (REPO / root).rglob('*.py'):
            try:
                text = p.read_text(encoding="utf-8")
            except Exception:   # noqa: BLE001 — 파일 읽기 실패 (binary/encoding) 흡수 → 다음 파일 진행 (가드 정합 가드)
                continue
            # migrate_neo4j_schema.py 는 의도적으로 bare Sector 매칭 (마이그 source).
            if p.name == "migrate_neo4j_schema.py":
                continue
            for i, line in enumerate(text.splitlines(), 1):
                ls = line.strip()
                if ls.startswith('#') or ls.startswith('"""') or ls.startswith("'''"):
                    continue
                if not any(kw in line for kw in cypher_kws):
                    # WHERE c:X OR c:Y 같은 라인도 검사 (cypher_kws 외 패턴).
                    if not pat_or.search(line):
                        continue
                for m in pat.finditer(line):
                    label = m.group(2)
                    if label.startswith('Anxg_'):
                        continue
                    if label in namespaced_labels:
                        violations.append(f"{p.relative_to(REPO)}:{i}: {label}")
                for m in pat_or.finditer(line):
                    label = m.group(2)
                    if label.startswith('Anxg_'):
                        continue
                    if label in namespaced_labels:
                        violations.append(f"{p.relative_to(REPO)}:{i}: {label}")

    assert not violations, \
        "Cypher 문자열에 bare 라벨 발견 (Anxg_ 프리픽스 누락):\n" + \
        "\n".join(violations[:20])


def test_no_close_on_singleton_get_connection():
    """`get_connection()` 은 @lru_cache 싱글톤 — `conn.close()` 호출 금지.

    회귀 가드: 본 세션 검토 중 kamp_catalog.upsert_pg 에 try/finally close 를
    추가했다가 발견. 싱글톤 conn 을 닫으면 다음 호출자가 closed conn 을 받아
    깨진다 (psycopg `the connection is closed`). 정리는 db.postgres.close() 가
    cache_clear 와 함께 일괄 처리.

    허용: db/postgres.py 의 close() 함수 자체 (cache_clear 와 같이 호출).
    """
    import ast

    violations = []
    for root in ('src',):
        for p in (REPO / root).rglob('*.py'):
            # db/postgres.py 자체는 close() 정의·구현이라 예외.
            if p.name == 'postgres.py' and p.parent.name == 'db':
                continue
            try:
                text = p.read_text(encoding="utf-8")
            except Exception:   # noqa: BLE001 — 파일 읽기 실패 흡수 → 다음 파일 진행
                continue
            if 'get_connection' not in text:
                continue
            try:
                tree = ast.parse(text)
            except Exception:   # noqa: BLE001 — syntax error 파일 흡수 → 다음 파일 진행 (AST 가드 회복성)
                continue
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                src = ast.unparse(node)
                if 'get_connection()' not in src:
                    continue
                # `conn = get_connection()` 형태에서 변수명 추출 후 close() 호출 검사.
                lines = src.split('\n')
                for i, ln in enumerate(lines):
                    s = ln.strip()
                    if not s.endswith('= get_connection()'):
                        continue
                    var = s.split('=')[0].strip()
                    remaining = '\n'.join(lines[i:])
                    if f'{var}.close()' in remaining:
                        violations.append(
                            f"{p.relative_to(REPO)}:{node.name}: "
                            f"`{var}.close()` 호출 — 싱글톤 conn 닫으면 후속 호출 깨짐"
                        )
                        break
                # `get_connection().close()` 직접 호출도 금지.
                if 'get_connection().close()' in src:
                    violations.append(
                        f"{p.relative_to(REPO)}:{node.name}: "
                        f"`get_connection().close()` 직접 호출 — db.postgres.close() 사용 권장"
                    )

    assert not violations, \
        "싱글톤 get_connection() 에 close() 호출 발견 (다음 호출자 깨짐):\n" + \
        "\n".join(violations[:10])


def test_get_connection_auto_invalidates_closed_cache_entry():
    """싱글톤 conn 이 손상되면 자동 폐기·재생성 — 후속 호출자 보호.

    회귀 가드: fail-soft 경로에서 rollback 실패로 conn 손상되거나 서버
    disconnect 시, cache 가 손상된 conn 을 들고 있어 다음 호출자가
    `the connection is closed` 로 깨지는 함정을 방지한다.
    """
    from autonexusgraph.db import postgres as pg

    # 기존 cache 비우기.
    pg._open_connection.cache_clear()

    # 가짜 conn 클래스 — 첫 생성은 closed=True, 두 번째는 정상.
    counter = {"n": 0}

    class _FakeConn:
        def __init__(self, *, closed: bool):
            self.closed = closed
            self.broken = False

    def _fake_psycopg_connect(_dsn):
        counter["n"] += 1
        # 첫 호출 → closed conn (이전 호출자가 fail-soft 후 손상 시뮬).
        # 두 번째 호출 → 정상 conn.
        return _FakeConn(closed=(counter["n"] == 1))

    import psycopg as _real
    orig_connect = _real.connect
    _real.connect = _fake_psycopg_connect
    try:
        conn1 = pg.get_connection()
        # health check 가 closed=True 를 감지 → cache_clear + 재생성 → 두 번째 호출.
        assert counter["n"] == 2, \
            f"health check 가 손상된 conn 감지·재생성 실패 (호출 횟수={counter['n']})"
        assert conn1.closed is False, "재생성된 conn 은 정상이어야 한다"
    finally:
        _real.connect = orig_connect
        pg._open_connection.cache_clear()


def test_get_pool_auto_invalidates_closed_cache_entry(monkeypatch):
    """get_pool() 도 get_connection() 과 대칭 — 손상된 pool 자동 폐기·재생성.

    회귀 가드: 외부에서 pool.close() 호출 (현재 db.postgres.close() 한 곳만)
    이후 cache 가 stale 한 채 다음 호출자가 `pool.connection()` 시 PoolClosed.
    health check 가 자동 복구.
    """
    from autonexusgraph.db import postgres as pg

    pg._open_pool.cache_clear()
    counter = {"n": 0}

    class _FakePool:
        def __init__(self, *, closed: bool):
            self.closed = closed

    def _fake_pool_ctor(*_a, **_kw):
        counter["n"] += 1
        return _FakePool(closed=(counter["n"] == 1))

    import psycopg_pool as _real
    orig = _real.ConnectionPool
    _real.ConnectionPool = _fake_pool_ctor
    try:
        pool = pg.get_pool()
        assert counter["n"] == 2, \
            f"health check 가 closed pool 감지·재생성 실패 (호출={counter['n']})"
        assert pool.closed is False, "재생성된 pool 은 열려있어야 함"
    finally:
        _real.ConnectionPool = orig
        pg._open_pool.cache_clear()


def test_transaction_invalidates_cache_on_rollback_failure(monkeypatch):
    """`transaction()` 컨텍스트에서 rollback 실패 시 cache 무효화.

    회귀 가드: yield 후 예외 발생 → rollback() 도 실패 (conn 손상) 시
    cache 가 손상된 conn 보존하면 다음 호출 깨짐. cache_clear() 호출 검증.
    """
    from autonexusgraph.db import postgres as pg

    pg._open_connection.cache_clear()

    class _FakeConn:
        def __init__(self):
            self.closed = False
            self.broken = False
            self.committed = False
        def cursor(self):
            raise RuntimeError("simulated query failure")
        def commit(self):
            self.committed = True
        def rollback(self):
            # rollback 자체도 실패 — conn 손상 상황 시뮬.
            raise RuntimeError("simulated rollback failure")

    fake = _FakeConn()
    monkeypatch.setattr(pg, "_open_connection", lambda: fake)
    # cache_clear 호출 검증용 카운터.
    cleared = {"n": 0}
    type(pg._open_connection).cache_clear if hasattr(pg._open_connection, "cache_clear") else None
    # monkeypatch 후 _open_connection 은 plain 함수라 cache_clear 속성 없음 — 대체 mock.
    pg._open_connection.cache_clear = lambda: cleared.__setitem__("n", cleared["n"] + 1)  # type: ignore[attr-defined]

    try:
        with pg.transaction() as conn:
            with conn.cursor() as _:
                pass
    except RuntimeError:
        pass

    assert cleared["n"] >= 1, "rollback 실패 시 _open_connection.cache_clear() 호출되어야 함"


def test_no_bare_pg_schemas_in_sql_strings():
    """src/scripts 의 SQL 문자열에 bare schema 가 없어야 한다 (anxg_ 프리픽스 강제)."""
    bare_schemas = ('master', 'auto', 'bridge', 'sec', 'wiki', 'ip', 'vec',
                    'esg', 'fin', 'ftc', 'law', 'macro', 'news', 'ops', 'chat')
    # 거짓 양성 예외: 모듈명·attr 접근 등 (예: 'master.' 가 SQL 컨텍스트 밖)
    sql_kws = ('INSERT INTO', 'FROM ', 'JOIN ', 'UPDATE ', 'REFERENCES ',
               'TRUNCATE ', 'DELETE FROM ', 'COPY ', 'EXISTS ', 'CREATE TABLE')

    violations = []
    for root in ('src', 'scripts'):
        for p in (REPO / root).rglob('*.py'):
            try:
                text = p.read_text(encoding="utf-8")
            except Exception:   # noqa: BLE001 — 파일 읽기 실패 (binary/encoding) 흡수 → 다음 파일 진행
                continue
            for i, line in enumerate(text.splitlines(), 1):
                ls = line.strip()
                if ls.startswith('#'):
                    continue
                if not any(kw in line for kw in sql_kws):
                    continue
                for sch in bare_schemas:
                    # SQL 컨텍스트에서 'sch.table' 직접 발견 — anxg_sch 가 아닌 경우만.
                    if re.search(rf'\b(?<!anxg_){sch}\.[a-z_]+', line):
                        # 추가 거짓양성 필터: 'kw <space> sch.table'
                        for kw in sql_kws:
                            if re.search(rf'{re.escape(kw)}\s*(?<!anxg_){sch}\.[a-z_]+', line):
                                violations.append(f"{p.relative_to(REPO)}:{i}: {sch}.* | {line.strip()[:100]}")
                                break

    assert not violations, \
        "SQL 문자열에 bare PG 스키마 발견 (anxg_ 프리픽스 누락):\n" + \
        "\n".join(violations[:20])

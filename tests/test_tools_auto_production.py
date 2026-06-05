"""AutoGraph 생산 & 공정 tool 6 종 단위 테스트.

DB 없이 mock cursor 로 SQL 파라미터 / 빈 인자 short-circuit / 화이트리스트
등록 검증. 실제 데이터 조회는 integration 영역.
"""

from __future__ import annotations

import importlib
from unittest import mock

import pytest


@pytest.fixture
def mock_db():
    """query_dicts 호출 인터셉트 — SQL + params 검사용.

    test_domain_plugin_discovery.py 의 sys.modules pop 후 stale ref 회피를 위해
    매 테스트마다 autograph.tools.spec 을 재 import.
    """
    # 매 테스트에서 fresh import — 모듈 재로드 시 stale ref 방지
    import autograph.tools.spec as spec
    importlib.reload(spec)
    with mock.patch.object(spec, "query_dicts") as qd:
        qd.return_value = []
        yield qd, spec


def _funcs(spec):
    """spec 모듈에서 신규 함수 6 종 추출."""
    return (
        spec.get_plant_capacity,
        spec.get_oem_production,
        spec.list_plants_by_oem,
        spec.search_processes,
        spec.get_macro_industry,
        spec.get_macro_production,
    )


# ── get_plant_capacity ───────────────────────────────────────────
def test_get_plant_capacity_empty_corp_code_returns_empty(mock_db):
    qd, spec = mock_db
    assert spec.get_plant_capacity("") == []
    assert qd.call_count == 0


def test_get_plant_capacity_none_corp_code_returns_empty(mock_db):
    qd, spec = mock_db
    assert spec.get_plant_capacity(None) == []   # type: ignore[arg-type]
    assert qd.call_count == 0


def test_get_plant_capacity_sql_uses_corp_code_filter(mock_db):
    qd, spec = mock_db
    spec.get_plant_capacity("00164742", year=2024)
    assert qd.call_count == 1
    sql, params = qd.call_args[0]
    assert "anxg_auto.plant_capacity" in sql
    assert params["cc"] == "00164742"
    assert params["year"] == 2024
    assert params["plant"] is None


def test_get_plant_capacity_with_plant_filter(mock_db):
    qd, spec = mock_db
    spec.get_plant_capacity("00164742", plant_code="HMC", year=2024)
    _, params = qd.call_args[0]
    assert params["plant"] == "HMC"


# ── get_oem_production ───────────────────────────────────────────
def test_get_oem_production_empty_returns_empty(mock_db):
    qd, spec = mock_db
    assert spec.get_oem_production("") == []
    assert qd.call_count == 0


def test_get_oem_production_year_optional(mock_db):
    qd, spec = mock_db
    spec.get_oem_production("00164742")
    _, params = qd.call_args[0]
    assert params["year"] is None


def test_get_oem_production_with_year(mock_db):
    qd, spec = mock_db
    spec.get_oem_production("00164742", year=2023)
    _, params = qd.call_args[0]
    assert params["year"] == 2023


# ── list_plants_by_oem ───────────────────────────────────────────
def test_list_plants_by_oem_empty_returns_empty(mock_db):
    qd, spec = mock_db
    assert spec.list_plants_by_oem("") == []
    assert qd.call_count == 0


def test_list_plants_by_oem_uses_full_outer_join(mock_db):
    qd, spec = mock_db
    spec.list_plants_by_oem("00164742")
    sql, params = qd.call_args[0]
    assert "FULL OUTER JOIN" in sql
    assert "plant_capacity" in sql
    assert "plant_production" in sql
    assert params["cc"] == "00164742"


# ── search_processes ────────────────────────────────────────────
def test_search_processes_empty_query_short_circuits(mock_db):
    qd, spec = mock_db
    assert spec.search_processes("") == []
    assert spec.search_processes("   ") == []
    assert qd.call_count == 0


def test_search_processes_lowercase_query(mock_db):
    """ILIKE 대상이 process_name_norm (lowercase) 라 query 도 lowercase 변환."""
    qd, spec = mock_db
    spec.search_processes("도장")
    _, params = qd.call_args[0]
    assert params["q"] == "도장"


def test_search_processes_caps_limit(mock_db):
    qd, spec = mock_db
    spec.search_processes("도장", limit=9999)
    _, params = qd.call_args[0]
    assert params["lim"] <= 200   # HARD_LIMIT


def test_search_processes_uses_process_name_norm_index(mock_db):
    qd, spec = mock_db
    spec.search_processes("도장")
    sql, _ = qd.call_args[0]
    assert "process_name_norm" in sql


# ── get_macro_industry ───────────────────────────────────────────
def test_get_macro_industry_no_args_returns_recent(mock_db):
    qd, spec = mock_db
    spec.get_macro_industry()
    args = qd.call_args[0]
    assert len(args) >= 1
    sql = args[0]
    assert "LIMIT 24" in sql
    assert "macro_industry_monthly" in sql


def test_get_macro_industry_with_year(mock_db):
    qd, spec = mock_db
    spec.get_macro_industry(year=2024)
    sql, params = qd.call_args[0]
    assert params["year"] == 2024
    assert params["month"] is None


def test_get_macro_industry_with_year_month(mock_db):
    qd, spec = mock_db
    spec.get_macro_industry(year=2024, month=12)
    _, params = qd.call_args[0]
    assert params["year"] == 2024
    assert params["month"] == 12


# ── get_macro_production ─────────────────────────────────────────
def test_get_macro_production_no_args_returns_all(mock_db):
    qd, spec = mock_db
    spec.get_macro_production()
    args = qd.call_args[0]
    assert len(args) >= 1
    sql = args[0]
    assert "macro_production_yearly" in sql


def test_get_macro_production_with_year(mock_db):
    qd, spec = mock_db
    spec.get_macro_production(year=2024)
    _, params = qd.call_args[0]
    assert params["year"] == 2024


# ── 화이트리스트 / 등록 ─────────────────────────────────────────
def test_auto_sql_allowed_contains_all_new_tools():
    """AUTO_SQL_ALLOWED 화이트리스트 등록 — 6 신규 함수 모두."""
    from autograph.agent_handler import AUTO_SQL_ALLOWED
    for name in ("get_plant_capacity", "get_oem_production",
                 "list_plants_by_oem", "search_processes",
                 "get_macro_industry", "get_macro_production"):
        assert name in AUTO_SQL_ALLOWED, f"{name} 화이트리스트 누락"


def test_tools_pkg_exports_new_names():
    """tools 패키지 __all__ + import 양쪽에서 새 함수 노출."""
    from autograph import tools
    for name in ("get_plant_capacity", "get_oem_production",
                 "list_plants_by_oem", "search_processes",
                 "get_macro_industry", "get_macro_production"):
        assert hasattr(tools, name), f"{name} 모듈 attribute 누락"
        assert name in tools.__all__, f"{name} __all__ 누락"


def test_tools_callable_from_package_level():
    """``from autograph.tools import get_plant_capacity`` 가 통과."""
    # 매번 재import — sys.modules pop 후 stale ref 회피
    import autograph.tools
    importlib.reload(autograph.tools)
    from autograph.tools import (
        get_plant_capacity,
        get_oem_production,
        list_plants_by_oem,
        search_processes,
    )
    # 빈 인자 short-circuit 으로 DB 불요 검증
    assert get_plant_capacity("") == []
    assert get_oem_production("") == []
    assert list_plants_by_oem("") == []
    assert search_processes("") == []

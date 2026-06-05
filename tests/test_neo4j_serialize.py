"""BACKLOG A-7 회귀 가드 — `neo4j.time.*` / `Duration` 등 msgpack 비호환 객체를
`serialize_value` 가 ISO string 으로 변환해 LangGraph checkpointer 의 'Type is not
msgpack serializable' 폴백을 차단.

eval matrix 2026-06-05 에서 `[run_agent] LangGraph 실행 실패 — 함수 체인 폴백:
Type is not msgpack serializable: Date` 가 다수 발생 → 본 helper 도입.
"""

from __future__ import annotations

import datetime as dt

import pytest

from autonexusgraph.db.neo4j import serialize_record, serialize_value


def test_primitive_passthrough() -> None:
    assert serialize_value(None) is None
    assert serialize_value(1) == 1
    assert serialize_value(1.5) == 1.5
    assert serialize_value(True) is True
    assert serialize_value("abc") == "abc"


def test_isoformat_object() -> None:
    """isoformat() 이 있는 객체는 ISO string 으로 변환."""
    d = dt.date(2026, 6, 5)
    assert serialize_value(d) == "2026-06-05"
    ts = dt.datetime(2026, 6, 5, 12, 30, 45)
    assert serialize_value(ts) == "2026-06-05T12:30:45"


def test_neo4j_time_date_like() -> None:
    """`neo4j.time.Date` 같은 외부 타입 모사 — isoformat() 만 있으면 OK."""

    class FakeNeo4jDate:
        def __init__(self, y: int, m: int, day: int) -> None:
            self._y, self._m, self._d = y, m, day

        def isoformat(self) -> str:
            return f"{self._y:04d}-{self._m:02d}-{self._d:02d}"

    assert serialize_value(FakeNeo4jDate(2026, 6, 5)) == "2026-06-05"


def test_nested_collections() -> None:
    """list/dict 재귀 — Date 가 들어 있어도 모두 변환."""
    d = dt.date(2026, 6, 5)
    out = serialize_value({"a": [d, 1, "x"], "b": {"c": d}})
    assert out == {"a": ["2026-06-05", 1, "x"], "b": {"c": "2026-06-05"}}


def test_unknown_type_str_fallback() -> None:
    """isoformat() 도 없는 unknown 객체는 str() 으로 fallback."""

    class Opaque:
        def __str__(self) -> str:
            return "opaque-value"

    assert serialize_value(Opaque()) == "opaque-value"


def test_serialize_record_dict_compat() -> None:
    """`Record` 처럼 dict 변환 가능한 객체 → dict[str, sanitized]."""
    rec = {"company": "현대차", "founded": dt.date(1967, 12, 29)}
    out = serialize_record(rec)
    assert out == {"company": "현대차", "founded": "1967-12-29"}


def test_msgpack_roundtrip_after_serialize() -> None:
    """A-7 회귀 가드 본문 — serialize 후엔 msgpack 으로 직렬화 가능해야 한다.

    LangGraph checkpointer 가 내부적으로 msgpack 을 쓰므로, 본 테스트가 PASS 면
    `[run_agent] LangGraph 실행 실패 — Type is not msgpack serializable: Date`
    가 더 이상 발생하지 않는다.
    """
    msgpack = pytest.importorskip("msgpack")
    d = dt.date(2026, 6, 5)
    raw = {"date_col": d, "name": "현대모비스", "rev": 1234.5}
    with pytest.raises(TypeError):
        msgpack.packb(raw, use_bin_type=True)
    sanitized = serialize_value(raw)
    packed = msgpack.packb(sanitized, use_bin_type=True)
    assert msgpack.unpackb(packed, raw=False) == {
        "date_col": "2026-06-05",
        "name": "현대모비스",
        "rev": 1234.5,
    }

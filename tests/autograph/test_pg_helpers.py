"""savepoint_guard 단위 테스트 — 실제 DB 없이 FakeCursor 로 execute() 호출 시퀀스 검증.

로더 적용이 동작-동등(SAVEPOINT→work→RELEASE / 오류 시 SAVEPOINT→ROLLBACK→재raise)임을
순수 단위 수준에서 보장한다 (autograph 로더는 라이브 PG 필요 → CI 미커버 영역 보완).
"""

from __future__ import annotations

import pytest

from autograph.loaders._pg_helpers import savepoint_guard


class FakeCursor:
    def __init__(self):
        self.calls: list[str] = []

    def execute(self, sql, params=None):
        self.calls.append(sql)


def test_success_emits_savepoint_then_release():
    cur = FakeCursor()
    with savepoint_guard(cur, "sp_x"):
        cur.execute("INSERT ...")
    assert cur.calls == ["SAVEPOINT sp_x", "INSERT ...", "RELEASE SAVEPOINT sp_x"]


def test_failure_rolls_back_and_reraises():
    cur = FakeCursor()
    with pytest.raises(ValueError):
        with savepoint_guard(cur, "sp_x", errors=ValueError):
            cur.execute("INSERT ...")
            raise ValueError("row bad")
    # SAVEPOINT → work → (예외) → ROLLBACK. RELEASE 는 없어야 함.
    assert cur.calls == ["SAVEPOINT sp_x", "INSERT ...", "ROLLBACK TO SAVEPOINT sp_x"]


def test_error_outside_errors_set_propagates_without_rollback():
    """errors 집합 밖 예외는 ROLLBACK/RELEASE 없이 그대로 전파 (기존 except 범위와 동일)."""
    cur = FakeCursor()
    with pytest.raises(KeyError):
        with savepoint_guard(cur, "sp_x", errors=ValueError):
            raise KeyError("not in errors set")
    assert cur.calls == ["SAVEPOINT sp_x"]   # SAVEPOINT 만, ROLLBACK/RELEASE 없음


def test_caller_except_still_handles_after_reraise():
    """ROLLBACK 후 재-raise 되므로 호출부 except 가 카운트/continue 를 수행 (제어흐름 보존)."""
    cur = FakeCursor()
    inserted = errors = 0
    for i in range(3):
        try:
            with savepoint_guard(cur, "sp_x", errors=ValueError):
                if i == 1:
                    raise ValueError("bad row")
            inserted += 1
        except ValueError:
            errors += 1
    assert (inserted, errors) == (2, 1)


def test_invalid_savepoint_name_rejected():
    cur = FakeCursor()
    with pytest.raises(ValueError):
        with savepoint_guard(cur, "sp x; DROP TABLE"):
            pass
    assert cur.calls == []   # 보간 전에 거부 — execute 미호출

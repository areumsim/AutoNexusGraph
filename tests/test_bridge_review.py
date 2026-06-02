"""Q-1 Bridge candidate 검토 운영 테스트 — DB 없이 (순수 helper + _run monkeypatch)."""

from __future__ import annotations

import pytest

from autonexusgraph import bridge_review as br


# ── 순수 helper ──────────────────────────────────────────────────────
def test_validate_status():
    for s in ("candidate", "reviewed", "rejected"):
        assert br._validate_status(s) == s
    with pytest.raises(ValueError):
        br._validate_status("approved")


def test_kpi_summarize_pct():
    k = br._kpi_summarize({"candidate": 80, "reviewed": 15, "rejected": 5}, 200)
    assert k["total"] == 100
    assert k["pending"] == 80
    assert k["reviewed_pct"] == 20.0       # (15+5)/100
    assert k["oldest_pending_age_days"] == 200


def test_kpi_summarize_empty():
    k = br._kpi_summarize({}, None)
    assert k["total"] == 0 and k["reviewed_pct"] == 0.0


# ── _run monkeypatch 로 SQL 호출 검증 ────────────────────────────────
@pytest.fixture()
def captured(monkeypatch):
    calls = []

    def fake_run(sql, params=None, *, fetch="none"):
        calls.append({"sql": " ".join(sql.split()), "params": tuple(params or ()), "fetch": fetch})
        if fetch == "scalar":
            return 7
        if fetch == "rows":
            return []
        return 3   # rowcount
    monkeypatch.setattr(br, "_run", fake_run)
    return calls


def test_set_review_status_records_reviewer(captured):
    n = br.set_review_status(42, "reviewed", reviewer="alice", note="ok")
    assert n == 3
    call = captured[-1]
    assert "now()" in call["sql"] and "reviewed_at" in call["sql"]
    assert call["params"] == ("reviewed", "alice", "ok", 42)


def test_set_status_candidate_nulls_reviewed_at(captured):
    br.set_review_status(1, "candidate")
    assert "reviewed_at = NULL" in captured[-1]["sql"]


def test_set_review_status_rejects_bad_status(captured):
    with pytest.raises(ValueError):
        br.set_review_status(1, "approved")
    assert captured == []   # DB 호출 전에 차단


def test_bulk_set_status_empty_noop(captured):
    assert br.bulk_set_status([], "rejected") == 0
    assert captured == []


def test_bulk_set_status(captured):
    n = br.bulk_set_status([1, 2, 3], "rejected", reviewer="bob")
    assert n == 3
    assert captured[-1]["params"] == ("rejected", "bob", None, [1, 2, 3])
    assert "ANY(%s)" in captured[-1]["sql"]


def test_auto_expire_dry_run(captured):
    out = br.auto_expire_stale(days=180, apply=False)
    assert out == {"dry_run": True, "days": 180, "would_reject": 7}
    assert captured[-1]["fetch"] == "scalar"
    assert "SELECT count(*)" in captured[-1]["sql"]


def test_auto_expire_apply(captured):
    out = br.auto_expire_stale(days=90, apply=True)
    assert out == {"dry_run": False, "days": 90, "rejected": 3}
    assert "UPDATE" in captured[-1]["sql"] and "'rejected'" in captured[-1]["sql"]
    assert "auto-rejected" in captured[-1]["params"][0]


def test_auto_expire_bad_days(captured):
    with pytest.raises(ValueError):
        br.auto_expire_stale(days=0, apply=True)
    assert captured == []


def test_list_candidates_clamps_limit(captured):
    br.list_candidates(limit=99999, status="candidate")
    # limit 은 500 으로 clamp, 마지막 두 param = (limit, offset)
    assert captured[-1]["params"][-2] == 500
    assert captured[-1]["fetch"] == "rows"


def test_list_candidates_bad_status(captured):
    with pytest.raises(ValueError):
        br.list_candidates(status="nope")

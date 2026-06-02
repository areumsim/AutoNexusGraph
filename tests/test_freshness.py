"""Q-5 데이터 freshness 테스트 — DB 없이 (_age_days/_classify + _run monkeypatch)."""

from __future__ import annotations

from datetime import date, datetime, timezone

from autonexusgraph import freshness as fr

NOW = datetime(2026, 6, 2, 12, 0, 0, tzinfo=timezone.utc)


# ── _age_days ────────────────────────────────────────────────────────
def test_age_days_datetime_aware():
    ts = datetime(2026, 5, 3, 12, 0, 0, tzinfo=timezone.utc)
    assert fr._age_days(ts, NOW) == 30


def test_age_days_naive_treated_utc():
    assert fr._age_days(datetime(2026, 6, 1, 12, 0, 0), NOW) == 1


def test_age_days_date():
    assert fr._age_days(date(2026, 5, 23), NOW) == 10


def test_age_days_none():
    assert fr._age_days(None, NOW) is None


# ── _classify ────────────────────────────────────────────────────────
def test_classify():
    assert fr._classify(0, None, 90) == "empty"
    assert fr._classify(5, None, 90) == "unknown"
    assert fr._classify(5, 30, 90) == "ok"
    assert fr._classify(5, 120, 90) == "stale"


# ── check_freshness (graceful + 집계) ───────────────────────────────
def test_check_freshness_mixed(monkeypatch):
    srcs = [
        {"label": "fresh", "table": "a.t1", "ingest": "ingested_at", "content": "d"},
        {"label": "old",   "table": "a.t2", "ingest": "ingested_at", "content": "d"},
        {"label": "empty", "table": "a.t3", "ingest": "ingested_at", "content": "d"},
        {"label": "broken","table": "a.t4", "ingest": "ingested_at", "content": "d"},
    ]

    def fake_run(sql, params=None):
        if "a.t1" in sql:
            return [{"n": 10, "last_ingested": datetime(2026, 5, 30, tzinfo=timezone.utc), "last_content": date(2026, 5, 1)}]
        if "a.t2" in sql:
            return [{"n": 7, "last_ingested": datetime(2026, 1, 1, tzinfo=timezone.utc), "last_content": date(2025, 12, 1)}]
        if "a.t3" in sql:
            return [{"n": 0, "last_ingested": None, "last_content": None}]
        raise RuntimeError("relation a.t4 does not exist")

    monkeypatch.setattr(fr, "_run", fake_run)
    rep = fr.check_freshness(stale_days=90, now=NOW, sources=srcs)
    by = {s["label"]: s for s in rep["sources"]}
    assert by["fresh"]["status"] == "ok"
    assert by["old"]["status"] == "stale"        # 2026-01-01 → >90일
    assert by["empty"]["status"] == "empty"
    assert by["broken"]["status"] == "error" and "a.t4" in by["broken"]["error"]
    assert rep["n_stale"] == 1 and rep["n_sources"] == 4


def test_format_table(monkeypatch):
    rep = {"stale_days": 90, "n_sources": 1, "n_stale": 1,
           "sources": [{"label": "X", "table": "a.t", "n": 3, "status": "stale",
                        "ingest_age_days": 120, "last_content": "2025-12-01"}]}
    out = fr._format_table(rep)
    assert "freshness" in out and "STALE" in out and "X" in out


def test_real_sources_have_required_keys():
    for s in fr.FRESHNESS_SOURCES:
        assert {"label", "table", "ingest", "content"} <= set(s)

"""Q-4 embed-status 테스트 — DB 없이 (순수 _summarize + _run monkeypatch)."""

from __future__ import annotations

from autonexusgraph import embed_status as es


def test_summarize_pct_and_pending():
    st = es._summarize(
        {"total": 100, "embedded": 40},
        [
            {"source": "dart", "total": 80, "embedded": 20},
            {"source": "nhtsa_recall", "total": 20, "embedded": 20},
            {"source": None, "total": 0, "embedded": 0},
        ],
    )
    assert st["total"] == 100 and st["embedded"] == 40 and st["pending"] == 60
    assert st["pct"] == 40.0
    by = {s["source"]: s for s in st["by_source"]}
    assert by["dart"]["pending"] == 60 and by["dart"]["pct"] == 25.0
    assert by["nhtsa_recall"]["pct"] == 100.0
    assert by["(null)"]["pct"] == 0.0          # NULL source → '(null)', 0 total 안전


def test_summarize_empty():
    st = es._summarize({"total": 0, "embedded": 0}, [])
    assert st["pct"] == 0.0 and st["by_source"] == []


def test_embed_status_uses_count_queries(monkeypatch):
    calls = []

    def fake_run(sql, params=None, *, fetch="rows"):
        calls.append(" ".join(sql.split()))
        if "GROUP BY source" in sql:
            return [{"source": "dart", "total": 5, "embedded": 3}]
        return [{"total": 5, "embedded": 3}]    # overall

    monkeypatch.setattr(es, "_run", fake_run)
    st = es.embed_status()
    assert st == {
        "total": 5, "embedded": 3, "pending": 2, "pct": 60.0,
        "by_source": [{"source": "dart", "total": 5, "embedded": 3,
                       "pending": 2, "pct": 60.0}],
    }
    # count(embedding) 로 NULL 제외, GROUP BY source 사용
    assert any("count(embedding)" in c for c in calls)
    assert any("GROUP BY source" in c for c in calls)


def test_format_table_renders(monkeypatch):
    st = es._summarize({"total": 10, "embedded": 7},
                       [{"source": "dart", "total": 10, "embedded": 7}])
    out = es._format_table(st)
    assert "anxg_vec.chunks" in out and "70.0%" in out and "dart" in out

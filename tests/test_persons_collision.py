"""Q-3 anxg_master.persons 충돌 측정 테스트 — DB 없이 (_summarize + _run monkeypatch)."""

from __future__ import annotations

from autonexusgraph import persons_collision as pc


def test_summarize_pct_and_fields():
    r = pc._summarize(
        {"total": 9948, "with_year": 6000, "with_qid": 3000},
        {"dup_names": 120, "dup_rows": 260},
        ambiguous=15,
        suspected=[{"canonical_name": "김철수", "birth_year": None, "n_corp": 9}],
    )
    assert r["total"] == 9948
    assert r["null_birth_year"] == 3948
    assert r["null_birth_year_pct"] == 39.7         # 3948/9948
    assert r["qid_pct"] == 30.2
    assert r["reused_names"] == 120 and r["reused_name_rows"] == 260
    assert r["ambiguous_overlap_names"] == 15
    assert r["suspected_merge_candidates"][0]["n_corp"] == 9


def test_summarize_empty():
    r = pc._summarize({"total": 0, "with_year": 0, "with_qid": 0}, {}, 0, [])
    assert r["null_birth_year_pct"] == 0.0 and r["null_birth_year"] == 0
    assert r["suspected_merge_candidates"] == []


def test_collision_report_queries(monkeypatch):
    calls = []

    def fake_run(sql, params=None, *, fetch="rows"):
        s = " ".join(sql.split())
        calls.append(s)
        if "count(birth_year)" in s:
            return [{"total": 10, "with_year": 7, "with_qid": 4}]
        if "dup_names" in s:
            return [{"dup_names": 2, "dup_rows": 5}]
        if "bool_or" in s:        # ambiguous (scalar)
            return 3
        if "person_executive_history" in s:
            assert params == (8,)          # min_corp 전달 확인
            return [{"canonical_name": "이영희", "birth_year": 1970, "n_corp": 11}]
        raise AssertionError(f"unexpected sql: {s}")

    monkeypatch.setattr(pc, "_run", fake_run)
    r = pc.collision_report(min_corp=8)
    assert r["total"] == 10 and r["null_birth_year"] == 3
    assert r["reused_names"] == 2 and r["ambiguous_overlap_names"] == 3
    assert r["suspected_merge_candidates"][0]["n_corp"] == 11
    # FILTER / distinct corp 쿼리 사용 확인
    assert any("FILTER (WHERE wikidata_qid IS NOT NULL)" in c for c in calls)
    assert any("count(DISTINCT h.corp_code)" in c for c in calls)


def test_format_table_renders():
    r = pc._summarize({"total": 5, "with_year": 3, "with_qid": 1},
                      {"dup_names": 1, "dup_rows": 2}, 0,
                      [{"canonical_name": "박민수", "birth_year": None, "n_corp": 6}])
    out = pc._format_table(r)
    assert "anxg_master.persons 충돌" in out and "박민수" in out and "6 corps" in out

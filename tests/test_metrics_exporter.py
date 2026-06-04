"""O-5 Prometheus exporter 테스트 — DB 없이 (render 순수 + collect graceful)."""

from __future__ import annotations

from autonexusgraph import metrics_exporter as mx


# ── render (pure) ────────────────────────────────────────────────────
def test_render_help_type_once_and_labels():
    metrics = [
        mx._m("up", 1, help="db up", labels={"component": "postgres"}),
        mx._m("up", 0, help="db up", labels={"component": "neo4j"}),
        mx._m("llm_cost_usd_total", 1.5, mtype="counter", help="cost"),
    ]
    out = mx.render_prometheus(metrics)
    # HELP/TYPE 는 name 당 1회
    assert out.count("# HELP anxg_up ") == 1
    assert out.count("# TYPE anxg_up gauge") == 1
    assert 'anxg_up{component="postgres"} 1' in out
    assert 'anxg_up{component="neo4j"} 0' in out
    assert "# TYPE anxg_llm_cost_usd_total counter" in out
    assert "anxg_llm_cost_usd_total 1.5" in out


def test_render_int_vs_float_format():
    out = mx.render_prometheus([mx._m("x", 5.0), mx._m("y", 2.5)])
    assert "anxg_x 5\n" in out          # 정수는 5 (5.0 아님)
    assert "anxg_y 2.5\n" in out


def test_render_escapes_label_quotes():
    out = mx.render_prometheus([mx._m("e", 1, labels={"k": 'a"b'})])
    assert 'k="a\\"b"' in out


# ── collect (graceful) ───────────────────────────────────────────────
def test_collect_graceful_counts_failures(monkeypatch):
    def good():
        return [mx._m("ok_metric", 1)]

    def bad():
        raise RuntimeError("db down")

    monkeypatch.setattr(mx, "COLLECTORS", [good, bad, good])
    out = mx.collect_metrics()
    names = [m["name"] for m in out]
    assert names.count("anxg_ok_metric") == 2          # 정상 collector 결과 보존
    scrape = next(m for m in out if m["name"] == "anxg_scrape_errors")
    assert scrape["value"] == 1.0                       # bad 1건 카운트, crash 없음


def test_collect_all_fail_still_returns_scrape_errors(monkeypatch):
    monkeypatch.setattr(mx, "COLLECTORS", [lambda: (_ for _ in ()).throw(ValueError())])
    out = mx.collect_metrics()
    assert out[-1]["name"] == "anxg_scrape_errors" and out[-1]["value"] == 1.0

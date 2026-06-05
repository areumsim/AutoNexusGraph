"""Prometheus exporter (O-5) — read-only 운영 메트릭 노출.

node count / chunk count / cost / error rate / stale source / DB up 을 Prometheus
text exposition format 으로 노출. **prometheus_client 의존 없음** (텍스트 직접 렌더)
+ stdlib http.server. 기존 read-only audit 모듈(embed_status / bridge_review /
freshness / cost_log)을 조합 — 각 collector graceful(실패 → scrape_errors 증가).

CLI:
    python -m autonexusgraph.metrics_exporter --once       # 1회 텍스트 출력
    python -m autonexusgraph.metrics_exporter --port 9105  # /metrics HTTP 서버
Makefile: ``make metrics`` (once) / ``make serve-metrics``.
알람 규칙·대시보드: infra/monitoring/ · docs/operations/monitoring.md.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

log = logging.getLogger(__name__)

NS = "anxg"   # metric prefix


def _m(name: str, value: float, *, mtype: str = "gauge",
       help: str = "", labels: dict[str, str] | None = None) -> dict[str, Any]:
    return {"name": f"{NS}_{name}", "value": float(value), "type": mtype,
            "help": help, "labels": labels or {}}


# ── collectors (각자 list[metric] 반환, 실패는 collect_metrics 가 graceful 처리) ──
def _collect_db_up() -> list[dict]:
    from autonexusgraph.db import neo4j, postgres
    out = []
    for comp, mod in (("postgres", postgres), ("neo4j", neo4j)):
        try:
            up = 1.0 if mod.ping() else 0.0
        except Exception:   # noqa: BLE001 — fail-soft 흡수 → 기본값 반환
            up = 0.0
        out.append(_m("up", up, help="DB component reachable (1/0)", labels={"component": comp}))
    return out


def _collect_chunks() -> list[dict]:
    from autonexusgraph.embed_status import embed_status
    st = embed_status()
    return [
        _m("vec_chunks_total", st["total"], help="anxg_vec.chunks 행 수"),
        _m("vec_chunks_embedded", st["embedded"], help="임베딩 채워진 chunk 수"),
    ]


def _collect_bridge() -> list[dict]:
    from autonexusgraph.bridge_review import review_progress_kpi
    k = review_progress_kpi()
    return [
        _m("bridge_entries", k["total"], help="anxg_bridge.corp_entity 총 행", labels={"status": "total"}),
        _m("bridge_entries", k["candidate"], help="anxg_bridge.corp_entity 총 행", labels={"status": "candidate"}),
        _m("bridge_entries", k["reviewed"], help="anxg_bridge.corp_entity 총 행", labels={"status": "reviewed"}),
        _m("bridge_entries", k["rejected"], help="anxg_bridge.corp_entity 총 행", labels={"status": "rejected"}),
    ]


def _collect_neo4j_nodes() -> list[dict]:
    from autonexusgraph.db.neo4j import get_session
    with get_session() as s:
        n = s.run("MATCH (n) RETURN count(n) AS n").single()["n"]
    return [_m("neo4j_nodes_total", n, help="Neo4j 전체 노드 수")]


def _collect_cost() -> list[dict]:
    from autonexusgraph.llm.cost_log import total_cost
    return [_m("llm_cost_usd_total", total_cost(), mtype="counter",
               help="cost_log.jsonl 누적 LLM 비용(USD)")]


def _collect_stale() -> list[dict]:
    from autonexusgraph.freshness import check_freshness
    r = check_freshness()
    return [_m("data_sources_stale", r["n_stale"], help="stale 임계 초과 소스 수"),
            _m("data_sources_total", r["n_sources"], help="모니터 대상 소스 수")]


def _collect_llm_status() -> list[dict]:
    """anxg_ops.llm_usage status 분포 → error rate 산출 근거."""
    from autonexusgraph.db.postgres import get_connection
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT status, count(*) FROM anxg_ops.llm_usage GROUP BY status")
        rows = cur.fetchall()
    conn.commit()
    return [_m("llm_turns_total", int(c), mtype="counter",
               help="anxg_ops.llm_usage turn 수 (status별)", labels={"status": str(st or "unknown")})
            for st, c in rows]


COLLECTORS: list[Callable[[], list[dict]]] = [
    _collect_db_up, _collect_chunks, _collect_bridge, _collect_neo4j_nodes,
    _collect_cost, _collect_stale, _collect_llm_status,
]


def collect_metrics() -> list[dict]:
    """모든 collector 실행 — 실패는 graceful 카운트(scrape 자체는 안 깨짐)."""
    out: list[dict] = []
    errors = 0
    for c in COLLECTORS:
        try:
            out.extend(c())
        except Exception as e:   # noqa: BLE001 — fail-soft 흡수 → 기본값 반환 (log 동반)
            errors += 1
            log.warning("[metrics] collector %s 실패: %s", getattr(c, "__name__", c), e)
    out.append(_m("scrape_errors", errors, help="이번 scrape 에서 실패한 collector 수"))
    return out


def _esc(v: str) -> str:
    return v.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def _fmt(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else repr(float(value))


def render_prometheus(metrics: list[dict]) -> str:
    """metric dict 리스트 → Prometheus text exposition. HELP/TYPE 는 name 당 1회."""
    lines: list[str] = []
    seen: set[str] = set()
    for m in metrics:
        name = m["name"]
        if name not in seen:
            seen.add(name)
            if m.get("help"):
                lines.append(f"# HELP {name} {_esc(m['help'])}")
            lines.append(f"# TYPE {name} {m.get('type', 'gauge')}")
        labels = m.get("labels") or {}
        lbl = ("{" + ",".join(f'{k}="{_esc(str(v))}"' for k, v in sorted(labels.items())) + "}") if labels else ""
        lines.append(f"{name}{lbl} {_fmt(m['value'])}")
    return "\n".join(lines) + "\n"


# ── HTTP 서버 (stdlib) ───────────────────────────────────────────────
def _serve(port: int) -> None:
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class H(BaseHTTPRequestHandler):
        def do_GET(self):   # noqa: N802
            if self.path.rstrip("/") in ("", "/healthz"):
                body = b"ok\n"
                self.send_response(200)
            elif self.path == "/metrics":
                body = render_prometheus(collect_metrics()).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; version=0.0.4")
            else:
                body = b"not found\n"
                self.send_response(404)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):   # noqa: N802 — 기본 stderr access log 억제
            pass

    log.info("[metrics] serving on :%d/metrics", port)
    ThreadingHTTPServer(("0.0.0.0", port), H).serve_forever()


def _main(argv: list[str] | None = None) -> int:
    import argparse

    p = argparse.ArgumentParser(prog="autonexusgraph.metrics_exporter",
                                description="Prometheus exporter (O-5)")
    p.add_argument("--once", action="store_true", help="1회 텍스트 출력 후 종료")
    p.add_argument("--port", type=int, default=9105, help="HTTP /metrics 포트")
    args = p.parse_args(argv)
    if args.once:
        print(render_prometheus(collect_metrics()), end="")
        return 0
    logging.basicConfig(level="INFO")
    _serve(args.port)
    return 0


__all__ = ["collect_metrics", "render_prometheus", "COLLECTORS"]


if __name__ == "__main__":
    raise SystemExit(_main())

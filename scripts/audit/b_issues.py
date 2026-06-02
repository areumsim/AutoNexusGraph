#!/usr/bin/env python3
"""data_inventory.md §3 B-issue 측정 routine — 미해결 4 건 (B6/B7/B10/B11) 의 현재 상태.

P2-(10) "이슈 추적" 단순 리스트 → 측정 가능 audit (사용자 cold review 2026-06-02):
    B-issue 별 진단 SOP (data_inventory §3) 를 runnable Python 으로 응축. 각 measure
    → metric 출력 → 해결 임계 (0 또는 정의된 threshold) 와 비교 → 종합 표.

사용:
    python scripts/audit/b_issues.py                    # 4 건 모두
    python scripts/audit/b_issues.py --issue B10        # 한 건
    python scripts/audit/b_issues.py --strict           # 한 건이라도 active 면 exit 1

출력:
    data/reports/b_issues.json  — 4 measure + status
    stdout — 한 줄 요약 + 표

판정:
    B6  : aihub_578/aihub_71347 component 매칭률 — 현재 모니터링만
    B7  : auto.staging_relations (Wikidata P176) row > 0 = 해결
    B10 : Neo4j :Supplier 중복 count (name_norm group_by, cnt > 1) = 0 = 해결
    B11 : auto.events_complaints 의 missing component_text 비율 < 0.30 = 해결
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

log = logging.getLogger(__name__)


def _load_env_once() -> None:
    """`.env` → process env (idempotent, setdefault). dotenv 미설치 시 manual parse."""
    import os
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    try:
        from dotenv import load_dotenv
        load_dotenv(env_path, override=False)
    except ImportError:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def _pg_conn():
    """psycopg2 connection — .env 또는 env override."""
    import os
    import psycopg2
    _load_env_once()
    dsn = os.environ.get("POSTGRES_DSN")
    if not dsn:
        raise RuntimeError("POSTGRES_DSN 미설정")
    return psycopg2.connect(dsn)


def _neo4j_driver():
    import os
    from neo4j import GraphDatabase
    _load_env_once()
    return GraphDatabase.driver(
        os.environ["NEO4J_URI"],
        auth=(os.environ.get("NEO4J_USER", "neo4j"),
              os.environ["NEO4J_PASSWORD"]),
    )


# ── B6 — AI-Hub model name mismatch ─────────────────────────
def check_b6() -> dict[str, Any]:
    """auto.components AI-Hub source 분포. 모니터링만 — threshold 없음.

    현재 상태: 양호 (24 CONTAINS_COMPONENT edge OK). model 변경 시 routine 재실행.
    """
    try:
        with _pg_conn() as c, c.cursor() as cur:
            cur.execute("""
                SELECT source, count(*) AS n,
                       count(DISTINCT system_code) AS n_systems
                  FROM auto.components
                 WHERE source IN ('aihub_578', 'aihub_71347')
                 GROUP BY source ORDER BY source
            """)
            rows = cur.fetchall()
    except Exception as exc:   # noqa: BLE001
        return {"id": "B6", "status": "ERROR",
                "reason": f"PG 조회 실패: {exc}"}
    return {
        "id":     "B6",
        "status": "MONITORING",
        "metric": "aihub_component_rows",
        "value":  sum(r[1] for r in rows),
        "detail": [{"source": r[0], "n_rows": r[1], "n_systems": r[2]} for r in rows],
        "note":   "현재 정합 양호 — model 명 변경 시 routine 재실행",
    }


# ── B7 — Wikidata P176 rate-limit / staging_relations 0 ────
def check_b7() -> dict[str, Any]:
    """auto.staging_relations 의 P176 (HAS_PART) row 수. > 0 = 해결.

    staging_relations 스키마: source 컬럼 없음 — extractor_name 으로 wikidata 식별.
    """
    try:
        with _pg_conn() as c, c.cursor() as cur:
            cur.execute("""
                SELECT count(*) FROM auto.staging_relations
                 WHERE extractor_name ILIKE '%wikidata%'
                    OR (relation_type = 'SUPPLIED_BY' AND extractor_name ILIKE '%p176%')
            """)
            n = cur.fetchone()[0] or 0
    except Exception as exc:   # noqa: BLE001
        return {"id": "B7", "status": "ERROR",
                "reason": f"PG 조회 실패: {exc}"}
    status = "RESOLVED" if n > 0 else "ACTIVE"
    return {
        "id":     "B7",
        "status": status,
        "metric": "staging_wikidata_p176_rows",
        "value":  n,
        "threshold": "> 0",
        "note":   ("Wikidata SPARQL P176 rate-limit (1 req/min) 우회 routine "
                    "(수동 batch / OpenAlex inference / manual seed 확장) 적용 후 row > 0"
                    if n == 0 else "해결됨"),
    }


# ── B10 — :Supplier Neo4j 중복 ─────────────────────────────
def check_b10() -> dict[str, Any]:
    """Neo4j :Supplier 의 name_norm 중복 패턴. 0 = 해결."""
    try:
        drv = _neo4j_driver()
        with drv.session() as s:
            r = s.run("""
                MATCH (s:Supplier)
                WITH s.name_norm AS norm, count(*) AS cnt
                WHERE norm IS NOT NULL AND cnt > 1
                RETURN count(norm) AS dup_groups,
                       sum(cnt - 1) AS extra_nodes
            """).single()
            dup_groups = (r or {}).get("dup_groups", 0)
            extra_nodes = (r or {}).get("extra_nodes", 0)
            total = s.run(
                "MATCH (s:Supplier) RETURN count(s) AS n"
            ).single()["n"]
        drv.close()
    except Exception as exc:   # noqa: BLE001
        return {"id": "B10", "status": "ERROR",
                "reason": f"Neo4j 조회 실패: {exc}"}
    extra_nodes = extra_nodes or 0
    dup_groups = dup_groups or 0
    status = "RESOLVED" if extra_nodes == 0 else "ACTIVE"
    return {
        "id":     "B10",
        "status": status,
        "metric": "supplier_duplicate_extra_nodes",
        "value":  int(extra_nodes),
        "detail": {
            "total_supplier_nodes": int(total),
            "duplicate_groups":     int(dup_groups),
            "extra_nodes":          int(extra_nodes),
        },
        "threshold": "= 0",
        "note":   ("`dedupe_suppliers_by_name_norm()` 추가 + load-auto-all 후 1회 실행 권장"
                    if extra_nodes else "해결됨"),
    }


# ── B11 — NHTSA complaint 짧은 카테고리 매칭 누락 ─────────────
def check_b11() -> dict[str, Any]:
    """events_complaints.components (ARRAY) 의 매칭 실패 비율. < 0.30 = 해결.

    실측 스키마: complaints.components = text[] (NHTSA categories) — unnest 후
    components.canonical_name 와 비교.
    """
    try:
        with _pg_conn() as c, c.cursor() as cur:
            cur.execute("""
                WITH expanded AS (
                  SELECT complaint_id, unnest(components) AS comp_text
                    FROM auto.events_complaints
                   WHERE components IS NOT NULL AND array_length(components, 1) > 0
                )
                SELECT
                    count(*) AS total,
                    count(*) FILTER (
                        WHERE comp_text NOT IN
                              (SELECT canonical_name FROM auto.components)
                    ) AS unmatched
                  FROM expanded
            """)
            row = cur.fetchone()
            total = row[0] or 0
            unmatched = row[1] or 0
    except Exception as exc:   # noqa: BLE001
        return {"id": "B11", "status": "ERROR",
                "reason": f"PG 조회 실패: {exc}"}
    ratio = (unmatched / total) if total else 0.0
    status = "RESOLVED" if ratio < 0.30 else "ACTIVE"
    return {
        "id":     "B11",
        "status": status,
        "metric": "complaint_unmatched_ratio",
        "value":  round(ratio, 3),
        "detail": {
            "total_complaints":    int(total),
            "unmatched_component": int(unmatched),
        },
        "threshold": "< 0.30",
        "note":   ("L3 system 매칭 추가 (ontology/auto/relations.yaml COMPLAINT_OF "
                    "target 확장) 또는 짧은 카테고리 components 등록 후 측정"
                    if ratio >= 0.30 else "해결됨"),
    }


_CHECKS = {
    "B6":  check_b6,
    "B7":  check_b7,
    "B10": check_b10,
    "B11": check_b11,
}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="audit-b-issues",
                                  description=__doc__.split("\n")[0])
    ap.add_argument("--issue", choices=tuple(_CHECKS.keys()),
                    default=None,
                    help="단일 B-issue 만 (생략 시 4 개 모두)")
    ap.add_argument("--strict", action="store_true",
                    help="ACTIVE 항목 (or ERROR) 있으면 exit 1 (CI 게이트)")
    ap.add_argument("--out", type=Path,
                    default=ROOT / "data" / "reports" / "b_issues.json")
    ap.add_argument("--log-level", default="WARNING")
    args = ap.parse_args(argv)
    logging.basicConfig(level=args.log_level,
                         format="%(asctime)s %(levelname)s %(name)s %(message)s")

    if args.issue:
        targets = {args.issue: _CHECKS[args.issue]}
    else:
        targets = _CHECKS

    results: list[dict[str, Any]] = []
    for k, fn in targets.items():
        log.info("[b-issues] checking %s", k)
        results.append(fn())

    payload = {
        "measured_at":   datetime.now(timezone.utc).isoformat(),
        "n_total":       len(results),
        "n_resolved":    sum(1 for r in results if r.get("status") == "RESOLVED"),
        "n_active":      sum(1 for r in results if r.get("status") == "ACTIVE"),
        "n_monitoring":  sum(1 for r in results if r.get("status") == "MONITORING"),
        "n_error":       sum(1 for r in results if r.get("status") == "ERROR"),
        "results":       results,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                        encoding="utf-8")

    status_marks = {"RESOLVED": "✅", "ACTIVE": "🟡",
                     "MONITORING": "⚠️", "ERROR": "❌"}
    summary = (f"[b-issues] resolved {payload['n_resolved']}/{payload['n_total']} | "
               f"active {payload['n_active']} | monitoring {payload['n_monitoring']} | "
               f"error {payload['n_error']}")
    print(summary)
    for r in results:
        m = status_marks.get(r.get("status", ""), "?")
        metric = r.get("metric") or "-"
        val = r.get("value")
        val_str = f"{val}" if val is not None else "?"
        print(f"  {m} {r['id']:4s} {metric:36s} = {val_str:>10}   {r.get('note', '')[:60]}")
    print(f"  → {args.out}")

    if args.strict and (payload["n_active"] or payload["n_error"]):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

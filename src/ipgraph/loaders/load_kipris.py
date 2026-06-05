"""KIPRIS XML → ip.{patents,assignees,inventors,patent_assignees,patent_inventors,
patent_cpc} PG + Neo4j ``:Patent`` / ``:Assignee`` / ``:Inventor`` +
``:ASSIGNED_TO`` / ``:INVENTED`` / ``:CLASSIFIED_AS`` 적재.

source_type='kipris', jurisdiction='KR', confidence=0.95 (A 등급 — KIPRIS 공공).
USPTO ODP 와 동일 스키마 + 멱등 — `load_uspto_odp.upsert_pg / load_neo4j` 헬퍼 재사용
(source_prefix override).

CLI:
    python -m ipgraph.loaders.load_kipris                 # raw/ip/kipris/*.xml 적재
    python -m ipgraph.loaders.load_kipris --skip-neo4j
    python -m ipgraph.loaders.load_kipris --dry-run

전제:
    - ``KIPRIS_API_KEY`` 가 있으면 ingestion 단이 fetch → raw 저장 → 본 loader 가 parse.
    - 키 없으면 raw 가 미리 ``data/raw/ip/kipris/*.xml`` 에 있어야 (offline 적재).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

log = logging.getLogger(__name__)

_SCHEMA_VERSION = "v2.2"
_CONF_A = 0.95
_SOURCE = "kipris"

# KIPRIS 공공 — A 등급, deterministic.
_EDGE_META = {
    "source_type":       _SOURCE,
    "confidence_score":  _CONF_A,
    "validated_status":  "validated",
    "extraction_method": "deterministic",
    "schema_version":    _SCHEMA_VERSION,
    # snapshot_year 는 호출 시점 — load_uspto_odp 가 _SNAPSHOT_YEAR 를 갖고 있으나
    # load_neo4j 가 edge_meta 그대로 cypher param 으로 spread하므로 여기서 명시.
}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="ipgraph.loaders.load_kipris",
                                  description=__doc__.split("\n")[0])
    ap.add_argument("--applicants", default=None,
                    help="csv — 미지정 시 priority 5사")
    ap.add_argument("--year", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true",
                    help="parse 만 — PG/Neo4j 적재 안 함")
    ap.add_argument("--skip-pg", action="store_true")
    ap.add_argument("--skip-neo4j", action="store_true")
    ap.add_argument("--log-level", default="INFO")
    args = ap.parse_args(argv)
    logging.basicConfig(level=args.log_level,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")

    from ipgraph.ingestion import kipris as ing
    from ipgraph.loaders.load_uspto_odp import load_neo4j, upsert_pg

    apps: list[str] | None = None
    if args.applicants:
        apps = [a.strip() for a in args.applicants.split(",") if a.strip()]
    result = ing.collect(applicants=apps, year=args.year, dry_run=args.dry_run)

    data = result.pop("_data", {})
    counts = {k: result.get(f"n_{k}") for k in
              ("patents", "assignees", "inventors",
               "patent_assignees", "patent_inventors", "patent_cpc")}
    log.info("[kipris] parsed: %s", counts)

    if not any(counts.values()):
        log.warning("[kipris] no parsed rows — KIPRIS_API_KEY 발급 또는 raw XML 배치 필요")
        print(json.dumps({"parsed": counts, "status": "no_data"},
                         ensure_ascii=False, indent=2))
        return 0

    out: dict[str, Any] = {"parsed": counts}
    if args.dry_run:
        out["status"] = "dry_run"
        print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
        return 0

    # KIPRIS 는 citations bulk 없음 (KIPRIS API 는 cited_by 미지원 — Q2 추가 후속).
    common: dict[str, list[dict]] = {
        "patents":           data.get("patents") or [],
        "assignees":         data.get("assignees") or [],
        "inventors":         data.get("inventors") or [],
        "patent_assignees":  data.get("patent_assignees") or [],
        "patent_inventors":  data.get("patent_inventors") or [],
        "patent_cpc":        data.get("patent_cpc") or [],
        "citations":         [],
    }

    # snapshot_year fallback — result.snapshot_year 가 None 이면 7-key invariant 위배 위험
    # (Neo4j 엣지에 null 적재 → audit-edge-meta FAIL). 항상 정수 보장.
    snapshot_year = result.get("snapshot_year") or datetime.now(timezone.utc).year
    edge_meta = {**_EDGE_META, "snapshot_year": int(snapshot_year)}

    if not args.skip_pg:
        out["pg"] = upsert_pg(**common)
        log.info("[kipris:pg] %s", out["pg"])

    if not args.skip_neo4j:
        out["neo4j"] = load_neo4j(edge_meta=edge_meta, **common)
        log.info("[kipris:neo4j] %s", out["neo4j"])

    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())

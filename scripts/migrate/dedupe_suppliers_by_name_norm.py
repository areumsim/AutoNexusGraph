#!/usr/bin/env python3
"""B10 — Neo4j :Anxg_Supplier 의 name_norm 중복 병합 (load-auto-all 후 1회 실행).

supplier 로더는 ``{entity_id}`` 키로 MERGE 하므로, master_suppliers 에 같은 회사가
다른 supplier_id 로 중복되면(예: 'Dana'(680) vs 'Dana Corporation'(3718)) Neo4j 에
name_norm 동일 노드가 2개 생긴다(B10). load-auto-all 이 재적재할 때마다 재발하므로,
본 routine 을 **load-auto-all 마지막 단계**로 두어 매번 정규화한다.

병합 정책: name_norm 그룹에서 **degree(관계 수) 최다 → 동률 시 entity_id 작은 것**을
canonical 로, 나머지를 apoc.refactor.mergeNodes 로 병합(관계 합치고, 흡수된 이름은
``name_aliases`` 로 보존). 멱등 — 중복 없으면 no-op.

사용:
    python scripts/migrate/dedupe_suppliers_by_name_norm.py [--dry-run]
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from autonexusgraph.db.neo4j import get_session  # noqa: E402

log = logging.getLogger("dedupe_suppliers")


def dedupe(*, dry_run: bool = False) -> dict:
    merged = groups = 0
    with get_session() as s:
        try:
            s.run("RETURN apoc.version()").single()
        except Exception as e:  # noqa: BLE001 — apoc.version() 호출 실패 흡수 → apoc 미설치 안내 + 중단 (mergeNodes 의존, 진행 불가)
            log.error("apoc 필요(apoc.refactor.mergeNodes). 중단: %s", e)
            return {"groups": 0, "merged": 0, "error": "apoc_missing"}

        dups = list(s.run("""
            MATCH (x:Anxg_Supplier) WHERE x.name_norm IS NOT NULL
            WITH x.name_norm AS nn, count(*) AS c
            WHERE c > 1
            RETURN nn AS name_norm, c AS cnt ORDER BY c DESC
        """))
        for rec in dups:
            groups += 1
            nn = rec["name_norm"]
            # canonical = degree 최다 → entity_id 작은 것. 나머지를 canonical 로 merge.
            log.info("dedupe name_norm=%r (%d nodes)%s", nn, rec["cnt"],
                     " [dry-run]" if dry_run else "")
            if dry_run:
                continue
            res = s.run("""
                MATCH (x:Anxg_Supplier {name_norm: $nn})
                WITH x ORDER BY apoc.node.degree(x) DESC,
                              coalesce(toInteger(x.entity_id), 2147483647) ASC
                WITH collect(x) AS nodes
                WITH head(nodes) AS keep, tail(nodes) AS dups
                // 흡수 노드 이름을 alias 로 보존
                SET keep.name_aliases =
                    apoc.coll.toSet(coalesce(keep.name_aliases, []) +
                                    [d IN dups | d.name])
                WITH keep, dups
                CALL apoc.refactor.mergeNodes(
                    [keep] + dups,
                    {properties: 'discard', mergeRels: true}) YIELD node
                RETURN size(dups) AS merged
            """, nn=nn).single()
            merged += int(res["merged"]) if res else 0

    log.info("done — groups=%d merged_nodes=%d%s", groups, merged,
             " (dry-run)" if dry_run else "")
    return {"groups": groups, "merged": merged}


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    dedupe(dry_run=a.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Neo4j 기존 노드에 `domain` 속성 일괄 backfill.

ontology.domain.DOMAIN_MAP SSOT 기준. 라벨별로 한 쿼리씩 실행 (transactional).
멱등 — 이미 domain 박힌 노드는 OVERWRITE (SSOT 진실 동기화).

CLI:
    python scripts/migrate/backfill_neo4j_domain.py
    python scripts/migrate/backfill_neo4j_domain.py --dry-run
    python scripts/migrate/backfill_neo4j_domain.py --only Manufacturer Company
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "src"))

from autonexusgraph.db.neo4j import get_session  # noqa: E402
from autonexusgraph.ontology.domain import (         # noqa: E402
    all_labels, domain_for, KNOWN_DOMAINS,
)


SET_DOMAIN = """
MATCH (n:`{label}`)
WITH n, $domain AS dom
SET  n.domain = dom
RETURN count(n) AS n
"""

COUNT_LABEL = "MATCH (n:`{label}`) RETURN count(n) AS n"

COUNT_NULL_DOMAIN = """
CALL db.labels() YIELD label
CALL { WITH label
  MATCH (n) WHERE label IN labels(n) AND n.domain IS NULL
  RETURN count(n) AS missing
}
RETURN label, missing ORDER BY missing DESC
"""


def main() -> int:
    ap = argparse.ArgumentParser(prog="backfill_neo4j_domain")
    ap.add_argument("--only", nargs="*", default=None,
                    help="특정 라벨만 (예: --only Manufacturer Company)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    targets = args.only or all_labels()
    print(f"[backfill] {len(targets)} labels: {targets}\n")


    total = 0
    with get_session() as sess:
        # 사전 NULL 상태 점검
        r = list(sess.run(COUNT_NULL_DOMAIN))
        if r:
            print("=== pre: domain NULL by label (DB의 실제 라벨 인벤토리) ===")
            for row in r:
                if row["missing"] > 0:
                    print(f"  {row['label']:<22} {row['missing']:>10}")
            print()

        # 라벨별 backfill
        for label in targets:
            dom = domain_for(label)
            if dom is None:
                print(f"  [skip] {label:<22} (domain.py에 매핑 없음)")
                continue
            # 사전 카운트
            pre = sess.run(COUNT_LABEL.format(label=label)).single()
            pre_n = pre["n"] if pre else 0
            if pre_n == 0:
                print(f"  [empty] {label:<22} 0 노드 — skip")
                continue
            if args.dry_run:
                print(f"  [dry] {label:<22} domain={dom} would set on {pre_n} nodes")
                continue
            res = sess.run(SET_DOMAIN.format(label=label), domain=dom).single()
            n = res["n"] if res else 0
            print(f"  [OK] {label:<22} domain={str(dom):<28} set on {n:>10} nodes")
            total += n

        # 사후 점검
        if not args.dry_run:
            print()
            print("=== post: domain NULL by label (0 이어야 정상) ===")
            r = list(sess.run(COUNT_NULL_DOMAIN))
            still_null = [(row["label"], row["missing"]) for row in r if row["missing"] > 0]
            if still_null:
                for lab, n in still_null:
                    print(f"  ⚠ {lab:<22} {n:>10} (domain.py 매핑 추가 필요)")
            else:
                print("  ✓ all clean — 모든 라벨의 domain 속성 적재 완료")
            print(f"\n[total] {total} nodes updated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

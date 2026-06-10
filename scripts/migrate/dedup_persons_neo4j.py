"""Anxg_Person 중복 노드 dedup + (name, birth_year) UNIQUE 제약 — 멱등.

문제 (2026-06-10 진단):
  `Anxg_Person` 에 ``(name, birth_year)`` UNIQUE 제약이 없고 INDEX 만 있어
  (graph.py:80-81), 배치 MERGE 가 **동일 (name, birth_year) 노드를 중복 생성**.
  실측 14,536 노드 vs distinct(name, birth_year) 12,897 → **중복 1,639개**
  (1,161 그룹, 최대 8중). + ``graph.py`` CEO 로더가 name-only MERGE(birth_year 미부여)라
  graph_structural 의 (name, birth_year) 노드와도 분리됨.

수정:
  1. birth_year 미상(CEO name-only 등) → -1 정규화 (동명이인 안전 분리 규약과 동일).
  2. ``apoc.refactor.mergeNodes`` 로 동일 (name, birth_year) 노드 병합 (관계 결합·dedup).
  3. ``(name, birth_year)`` UNIQUE 제약 추가 → 향후 중복 차단.

⚠️ **공유 Neo4j 를 변경한다 (노드 삭제 포함)**. 실행 전 백업 필수
  (docs/operations/backup_dr.md / `make backup`). 멱등 — 재실행 안전.

사용:
  # 1) 백업
  make backup
  # 2) dry-run (변경 없이 영향만 출력)
  python3 scripts/migrate/dedup_persons_neo4j.py --dry-run
  # 3) 실행
  python3 scripts/migrate/dedup_persons_neo4j.py --apply
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from autonexusgraph.db.neo4j import get_session  # noqa: E402


def _counts(s) -> tuple[int, int, int]:
    total = s.run("MATCH (p:Anxg_Person) RETURN count(p) AS n").single()["n"]
    distinct = s.run(
        "MATCH (p:Anxg_Person) "
        "RETURN count(DISTINCT [p.name, coalesce(p.birth_year, -1)]) AS d"
    ).single()["d"]
    null_by = s.run(
        "MATCH (p:Anxg_Person) WHERE p.birth_year IS NULL RETURN count(p) AS n"
    ).single()["n"]
    return total, distinct, null_by


def main() -> None:
    ap = argparse.ArgumentParser(description="Anxg_Person dedup + UNIQUE 제약")
    ap.add_argument("--apply", action="store_true", help="실제 변경 (없으면 dry-run)")
    ap.add_argument("--dry-run", action="store_true", help="명시적 dry-run")
    args = ap.parse_args()
    apply = args.apply and not args.dry_run

    with get_session() as s:
        total, distinct, null_by = _counts(s)
        removable = total - distinct
        print(f"[dedup-persons] 현재 Person {total} / distinct(name,birth_year) {distinct} "
              f"→ 중복 {removable} (병합 대상), birth_year NULL {null_by}")
        if not apply:
            print("[dedup-persons] dry-run — 변경 없음. 실행하려면 --apply (백업 후).")
            return

        # 1. NULL birth_year → -1 정규화.
        s.run("MATCH (p:Anxg_Person) WHERE p.birth_year IS NULL SET p.birth_year = -1")

        # 2. (name, birth_year) 동일 노드 병합 — 관계 결합 + dedup.
        merged = s.run(
            """
            MATCH (p:Anxg_Person)
            WITH p.name AS n, p.birth_year AS by, collect(p) AS ps
            WHERE size(ps) > 1
            CALL apoc.refactor.mergeNodes(ps, {properties: 'discard', mergeRels: true})
                 YIELD node
            RETURN count(node) AS merged
            """
        ).single()["merged"]

        # 3. UNIQUE 제약 (dedup 후라야 생성 성공).
        s.run(
            "CREATE CONSTRAINT person_name_birth_unique IF NOT EXISTS "
            "FOR (p:Anxg_Person) REQUIRE (p.name, p.birth_year) IS UNIQUE"
        )

        after, after_d, _ = _counts(s)
        dups = s.run(
            "MATCH (p:Anxg_Person) WITH p.name AS n, p.birth_year AS by, count(*) AS c "
            "WHERE c > 1 RETURN count(*) AS d"
        ).single()["d"]
        print(f"[dedup-persons] 완료 — Person {total} → {after} (병합 그룹 {merged}, "
              f"제거 {total - after}, 잔여 중복 {dups}) + UNIQUE 제약 person_name_birth_unique")


if __name__ == "__main__":
    main()

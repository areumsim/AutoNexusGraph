"""master.persons 동명·동년생 충돌 측정 (Q-3) — read-only audit.

배경: `master.persons` 의 dedup 키는 `UNIQUE(canonical_name, birth_year)`
(02_entity_resolution.sql). 이 키는 두 가지 충돌 위험을 갖는다 (README §12.4):
1. **birth_year NULL** — 디스앰비규에이터 부재 → 동명이인 false-merge 또는 분절 위험.
2. **동일 (name, birth_year)** — 진짜 다른 두 사람이 한 row 로 병합될 수 있음
   (테이블만으로는 직접 탐지 불가 → exec_history 의 distinct corp 수가 비정상적으로
   많은 person 을 "병합 의심 검토 후보" 로 surface).

본 모듈은 사전 정의 함수만 (자유 SQL 금지). 충돌 빈도를 측정해 (name, birth_year,
회사) 보조 키 도입 여부를 판단할 근거를 만든다.

CLI:
    python -m autonexusgraph.persons_collision           # 표
    python -m autonexusgraph.persons_collision --json
    python -m autonexusgraph.persons_collision --min-corp 8   # 병합 의심 임계
Makefile: ``make persons-collision``.
"""

from __future__ import annotations

import json
from typing import Any, Sequence

DEFAULT_MIN_CORP = 5      # exec_history distinct corp ≥ 이 값이면 병합 의심 검토 후보


def _run(sql: str, params: Sequence | None = None, *, fetch: str = "rows") -> Any:
    from autonexusgraph.db.postgres import get_connection

    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(sql, tuple(params or ()))
        if fetch == "rows":
            cols = [d.name for d in cur.description]
            out: Any = [dict(zip(cols, r)) for r in cur.fetchall()]
        else:  # scalar
            row = cur.fetchone()
            out = row[0] if row else None
    conn.commit()
    return out


def _pct(n: int, total: int) -> float:
    return round(100.0 * n / total, 1) if total else 0.0


def _summarize(overall: dict, reused: dict, ambiguous: int,
               suspected: list[dict]) -> dict[str, Any]:
    """순수 집계 (DB 없이 테스트 가능)."""
    total = int(overall.get("total", 0))
    with_year = int(overall.get("with_year", 0))
    with_qid = int(overall.get("with_qid", 0))
    null_year = total - with_year
    return {
        "total": total,
        "with_birth_year": with_year,
        "null_birth_year": null_year,
        "null_birth_year_pct": _pct(null_year, total),     # 핵심 위험 지표
        "with_wikidata_qid": with_qid,
        "qid_pct": _pct(with_qid, total),
        "reused_names": int(reused.get("dup_names", 0)),    # 같은 이름 다중 row
        "reused_name_rows": int(reused.get("dup_rows", 0)),
        "ambiguous_overlap_names": int(ambiguous),          # 이름이 NULL+비NULL 혼재
        "suspected_merge_candidates": suspected,            # distinct corp 과다 person
    }


def collision_report(*, min_corp: int = DEFAULT_MIN_CORP) -> dict[str, Any]:
    """master.persons 충돌 빈도 측정."""
    overall = _run(
        """
        SELECT count(*) AS total,
               count(birth_year) AS with_year,
               count(*) FILTER (WHERE wikidata_qid IS NOT NULL) AS with_qid
          FROM master.persons
        """, fetch="rows")[0]
    reused = _run(
        """
        SELECT count(*) AS dup_names, coalesce(sum(c), 0) AS dup_rows
          FROM (SELECT canonical_name, count(*) AS c
                  FROM master.persons GROUP BY canonical_name HAVING count(*) > 1) t
        """, fetch="rows")[0]
    ambiguous = _run(
        """
        SELECT count(*) FROM (
          SELECT canonical_name FROM master.persons
           GROUP BY canonical_name
          HAVING bool_or(birth_year IS NULL) AND bool_or(birth_year IS NOT NULL)
        ) t
        """, fetch="scalar")
    suspected = _run(
        """
        SELECT p.canonical_name, p.birth_year,
               count(DISTINCT h.corp_code) AS n_corp
          FROM master.persons p
          JOIN master.person_executive_history h ON h.internal_id = p.internal_id
         GROUP BY p.internal_id, p.canonical_name, p.birth_year
        HAVING count(DISTINCT h.corp_code) >= %s
         ORDER BY n_corp DESC
         LIMIT 20
        """, (int(min_corp),), fetch="rows")
    return _summarize(overall, reused, int(ambiguous or 0), suspected)


def _format_table(r: dict[str, Any]) -> str:
    lines = [
        f"master.persons 충돌 측정 — total {r['total']:,}",
        f"  birth_year NULL : {r['null_birth_year']:,} ({r['null_birth_year_pct']}%)  ← 디스앰비규에이터 부재 위험",
        f"  wikidata_qid    : {r['with_wikidata_qid']:,} ({r['qid_pct']}%)",
        f"  동명 다중 row   : {r['reused_names']:,} 이름 / {r['reused_name_rows']:,} row",
        f"  NULL+비NULL 혼재: {r['ambiguous_overlap_names']:,} 이름",
        "",
        f"  병합 의심 검토 후보 (distinct corp 과다, {len(r['suspected_merge_candidates'])}건):",
    ]
    for s in r["suspected_merge_candidates"]:
        by = s.get("birth_year")
        lines.append(f"    - {s['canonical_name']} (b.{by if by is not None else '?'}) → {s['n_corp']} corps")
    if not r["suspected_merge_candidates"]:
        lines.append("    (없음)")
    return "\n".join(lines)


def _main(argv: Sequence[str] | None = None) -> int:
    import argparse

    p = argparse.ArgumentParser(prog="autonexusgraph.persons_collision",
                                description="master.persons 동명·동년생 충돌 측정 (Q-3)")
    p.add_argument("--json", action="store_true")
    p.add_argument("--min-corp", type=int, default=DEFAULT_MIN_CORP,
                   help="병합 의심 검토 후보 distinct corp 임계 (기본 5)")
    args = p.parse_args(argv)
    rep = collision_report(min_corp=args.min_corp)
    print(json.dumps(rep, ensure_ascii=False, indent=2, default=str) if args.json
          else _format_table(rep))
    return 0


__all__ = ["collision_report", "_summarize", "DEFAULT_MIN_CORP"]


if __name__ == "__main__":
    raise SystemExit(_main())

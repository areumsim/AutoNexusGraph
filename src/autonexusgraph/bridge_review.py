"""Bridge candidate 검토 운영 (Q-1) — `bridge.corp_entity` SOP 데이터 계층.

배경: 자동 매칭 (Wikidata QID / LEI / 사업자번호 / 이름) 결과는
``reviewed_status='candidate'`` 로 적재된다 (08_bridge.sql). 검토 없이 누적되면
4,792+ candidate 가 영속 쌓여 cross-domain 답변 신뢰도를 흐린다 (README §12.4).

본 모듈은 **사전 정의 함수만** 제공 (자유 SQL 금지, 프로젝트 원칙):
- ``list_candidates(...)``      — 검토 대기/특정 상태 목록 (UI·CLI 공용)
- ``set_review_status(...)``    — ✓ reviewed / ✗ rejected 라벨 (감사 컬럼 기록)
- ``bulk_set_status(...)``      — 다건 일괄 라벨
- ``auto_expire_stale(...)``    — N일 미검토 candidate 자동 rejected (cron)
- ``review_progress_kpi()``     — 검토 진행률 + 상태/유형 분포 KPI

CLI:
    python -m autonexusgraph.bridge_review kpi
    python -m autonexusgraph.bridge_review expire --days 180 [--apply]
    python -m autonexusgraph.bridge_review list --entity-type supplier --limit 20

Streamlit 검토 UI 는 ``autonexusgraph.ui.bridge_review`` (본 모듈을 호출).
"""

from __future__ import annotations

import argparse
import json
import logging
from typing import Any, Sequence

log = logging.getLogger(__name__)

VALID_STATUSES = ("candidate", "reviewed", "rejected")
DEFAULT_STALE_DAYS = 180          # 6개월 — README §12.4 / BACKLOG Q-1


# ── 내부 실행기 (테스트에서 monkeypatch 지점) ────────────────────────
def _run(sql: str, params: Sequence | None = None, *, fetch: str = "none") -> Any:
    """단일 진입 DB 실행기. fetch: 'none' | 'rows' | 'scalar'. write 는 commit.

    프로젝트의 ``tools/_db.py`` 와 같은 get_connection + commit 패턴.
    """
    from autonexusgraph.db.postgres import get_connection

    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(sql, tuple(params or ()))
        if fetch == "rows":
            cols = [d.name for d in cur.description]
            out: Any = [dict(zip(cols, r)) for r in cur.fetchall()]
        elif fetch == "scalar":
            row = cur.fetchone()
            out = row[0] if row else None
        else:
            out = cur.rowcount
    conn.commit()
    return out


def _validate_status(status: str) -> str:
    if status not in VALID_STATUSES:
        raise ValueError(f"reviewed_status 허용값: {VALID_STATUSES} (받음: {status!r})")
    return status


# ── 조회 ─────────────────────────────────────────────────────────────
def list_candidates(*, status: str = "candidate",
                    entity_type: str | None = None,
                    match_method: str | None = None,
                    min_confidence: float = 0.0,
                    max_confidence: float = 1.0,
                    limit: int = 50,
                    offset: int = 0) -> list[dict]:
    """검토 대상 목록. 기본은 candidate, confidence 낮은 것/오래된 것 우선 정렬.

    name match (name_exact/name_fuzzy) 처럼 의심스러운 후보를 먼저 보도록
    confidence 오름차순 → created_at 오름차순(오래된 것 먼저).
    """
    _validate_status(status)
    limit = max(1, min(int(limit), 500))
    offset = max(0, int(offset))
    return _run(
        """
        SELECT id, corp_code, entity_id, entity_type, name,
               wikidata_qid, lei, cik, business_no,
               match_method, confidence_score, reviewed_status, notes,
               created_at, reviewed_at, reviewed_by,
               EXTRACT(DAY FROM now() - created_at)::int AS age_days
          FROM bridge.corp_entity
         WHERE reviewed_status = %s
           AND (%s::text IS NULL OR entity_type = %s)
           AND (%s::text IS NULL OR match_method = %s)
           AND confidence_score >= %s
           AND confidence_score <= %s
         ORDER BY confidence_score ASC, created_at ASC
         LIMIT %s OFFSET %s
        """,
        (status, entity_type, entity_type, match_method, match_method,
         min_confidence, max_confidence, limit, offset),
        fetch="rows",
    )


# ── 라벨링 (✓ / ✗) ──────────────────────────────────────────────────
def set_review_status(row_id: int, status: str, *,
                      reviewer: str = "ui",
                      note: str | None = None) -> int:
    """단건 검토 라벨. reviewed_at/reviewed_by 기록. 변경 행 수 반환 (0/1).

    candidate → reviewed(✓) / rejected(✗) 가 일반 흐름이지만, 정정(reviewed↔
    rejected) 도 허용. status='candidate' 로 되돌리면 reviewed_at NULL 로 초기화.
    """
    _validate_status(status)
    reviewed_at_expr = "NULL" if status == "candidate" else "now()"
    return _run(
        f"""
        UPDATE bridge.corp_entity
           SET reviewed_status = %s,
               reviewed_at = {reviewed_at_expr},
               reviewed_by = %s,
               notes = COALESCE(%s, notes),
               updated_at = now()
         WHERE id = %s
        """,
        (status, reviewer, note, int(row_id)),
        fetch="none",
    )


def bulk_set_status(row_ids: Sequence[int], status: str, *,
                    reviewer: str = "ui",
                    note: str | None = None) -> int:
    """다건 일괄 라벨. 변경 행 수 반환."""
    _validate_status(status)
    ids = [int(i) for i in row_ids]
    if not ids:
        return 0
    reviewed_at_expr = "NULL" if status == "candidate" else "now()"
    return _run(
        f"""
        UPDATE bridge.corp_entity
           SET reviewed_status = %s,
               reviewed_at = {reviewed_at_expr},
               reviewed_by = %s,
               notes = COALESCE(%s, notes),
               updated_at = now()
         WHERE id = ANY(%s)
        """,
        (status, reviewer, note, ids),
        fetch="none",
    )


# ── 자동 만료 (N일 미검토 → rejected) ────────────────────────────────
def auto_expire_stale(*, days: int = DEFAULT_STALE_DAYS,
                      apply: bool = False) -> dict[str, Any]:
    """``days`` 일 넘게 미검토인 candidate 를 rejected 로 자동 거부.

    ``apply=False`` (기본) 면 dry-run — 대상 건수만 반환, 변경 없음.
    cron 권장: ``python -m autonexusgraph.bridge_review expire --days 180 --apply``.
    """
    if int(days) < 1:
        raise ValueError("days 는 1 이상")
    if not apply:
        n = _run(
            """
            SELECT count(*) FROM bridge.corp_entity
             WHERE reviewed_status = 'candidate'
               AND created_at < now() - make_interval(days => %s)
            """,
            (int(days),), fetch="scalar",
        )
        return {"dry_run": True, "days": int(days), "would_reject": int(n or 0)}

    note = f"[auto-rejected: 미검토 {int(days)}일 경과 — Q-1]"
    n = _run(
        """
        UPDATE bridge.corp_entity
           SET reviewed_status = 'rejected',
               reviewed_at = now(),
               reviewed_by = 'auto-expire',
               notes = COALESCE(notes || ' ', '') || %s,
               updated_at = now()
         WHERE reviewed_status = 'candidate'
           AND created_at < now() - make_interval(days => %s)
        """,
        (note, int(days)), fetch="none",
    )
    log.info("[bridge_review] auto-expire %s일 → rejected %s건", days, n)
    return {"dry_run": False, "days": int(days), "rejected": int(n or 0)}


# ── 진행률 KPI ───────────────────────────────────────────────────────
def _kpi_summarize(status_counts: dict[str, int],
                   oldest_pending_age_days: int | None,
                   by_entity_type: list[dict] | None = None) -> dict[str, Any]:
    """순수 집계 (DB 없이 테스트 가능). 상태별 count → 진행률."""
    candidate = int(status_counts.get("candidate", 0))
    reviewed = int(status_counts.get("reviewed", 0))
    rejected = int(status_counts.get("rejected", 0))
    total = candidate + reviewed + rejected
    decided = reviewed + rejected
    pct = round(100.0 * decided / total, 1) if total else 0.0
    return {
        "total": total,
        "candidate": candidate,
        "reviewed": reviewed,
        "rejected": rejected,
        "reviewed_pct": pct,            # 검토 완료(reviewed+rejected) 비율
        "pending": candidate,
        "oldest_pending_age_days": oldest_pending_age_days,
        "by_entity_type": by_entity_type or [],
    }


def review_progress_kpi() -> dict[str, Any]:
    """검토 진행률 + 분포. UI 헤더·CLI·대시보드 공용."""
    rows = _run(
        "SELECT reviewed_status, count(*) AS n FROM bridge.corp_entity GROUP BY reviewed_status",
        fetch="rows",
    )
    counts = {r["reviewed_status"]: int(r["n"]) for r in rows}
    oldest = _run(
        """
        SELECT EXTRACT(DAY FROM now() - min(created_at))::int
          FROM bridge.corp_entity WHERE reviewed_status = 'candidate'
        """,
        fetch="scalar",
    )
    by_type = _run(
        """
        SELECT entity_type,
               count(*) FILTER (WHERE reviewed_status = 'candidate') AS pending,
               count(*) AS total
          FROM bridge.corp_entity
         GROUP BY entity_type
         ORDER BY pending DESC
        """,
        fetch="rows",
    )
    return _kpi_summarize(counts, int(oldest) if oldest is not None else None, by_type)


# ── CLI ──────────────────────────────────────────────────────────────
def _main(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="autonexusgraph.bridge_review",
                                description="Bridge candidate 검토 운영 (Q-1)")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("kpi", help="검토 진행률 KPI 출력")

    pe = sub.add_parser("expire", help="N일 미검토 candidate 자동 rejected")
    pe.add_argument("--days", type=int, default=DEFAULT_STALE_DAYS)
    pe.add_argument("--apply", action="store_true", help="실제 적용 (미지정 시 dry-run)")

    pl = sub.add_parser("list", help="검토 대상 목록")
    pl.add_argument("--status", default="candidate")
    pl.add_argument("--entity-type", default=None)
    pl.add_argument("--match-method", default=None)
    pl.add_argument("--limit", type=int, default=20)

    args = p.parse_args(argv)
    if args.cmd == "kpi":
        print(json.dumps(review_progress_kpi(), ensure_ascii=False, indent=2, default=str))
    elif args.cmd == "expire":
        print(json.dumps(auto_expire_stale(days=args.days, apply=args.apply),
                         ensure_ascii=False, indent=2))
    elif args.cmd == "list":
        rows = list_candidates(status=args.status, entity_type=args.entity_type,
                               match_method=args.match_method, limit=args.limit)
        print(json.dumps(rows, ensure_ascii=False, indent=2, default=str))
    return 0


__all__ = [
    "list_candidates", "set_review_status", "bulk_set_status",
    "auto_expire_stale", "review_progress_kpi",
    "VALID_STATUSES", "DEFAULT_STALE_DAYS",
]


if __name__ == "__main__":
    raise SystemExit(_main())

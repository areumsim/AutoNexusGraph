"""OEM IR/뉴스룸 raw → ``anxg_auto.events_oem_news`` UPSERT.

원본 위치:
    data/raw/auto/oem_ir/<oem>/_meta.jsonl              — 메타 (URL, title, ...)
    data/raw/auto/oem_ir/<oem>/<YYYY-MM-DD>_<slug>.html — raw 본문

라이선스: `_license.LICENSE_POLICY['{oem}_ir']` 가 'public_partial' 이면 body_text
저장. 'metadata_only' 이면 body_text 비우고 메타만. 'copyrighted' 이면 row 자체
skip.

DART corp_code 매핑 (OEM_CORP_CODES):
    hyundai → 00164742, mobis → 00164788, kia → 00106641 (현재 비활성).

UPSERT 키: ``(oem, url)``.

PRD §3.5: 공식 IR = B 등급, confidence 0.80.

CLI:
    python -m autograph.loaders.load_oem_ir_news --oem hyundai
    python -m autograph.loaders.load_oem_ir_news --all
    python -m autograph.loaders.load_oem_ir_news --dry-run
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path

from autonexusgraph.config import get_settings
from autonexusgraph.ingestion._license import (
    LICENSE_POLICY,
    OEM_NEWSROOM_POLICY,
    allow_body,
    policy as license_policy,
)


log = logging.getLogger(__name__)


_SOURCE_ROOT = "auto/oem_ir"


# OEM → DART corp_code (DART production loader 와 일관)
_OEM_CORP_CODE = {
    "hyundai":        "00164742",
    "kia":            "00106641",
    "kia_worldwide":  "00106641",   # 같은 Kia 법인 — 다른 도메인 정책
    "mobis":          "00164788",
}


def _meta_path(oem: str) -> Path:
    return get_settings().ingest_raw_dir / _SOURCE_ROOT / oem / "_meta.jsonl"


def _iter_meta(oem: str):
    """``_meta.jsonl`` 의 각 row dict 산출."""
    p = _meta_path(oem)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            continue


_DATE_RE = re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})")


def _read_body_text(html_path: str, *, body_allowed: bool) -> str | None:
    """라이선스 정책에 따라 본문 텍스트 반환.

    body_allowed=False → None (metadata_only / copyrighted).
    """
    if not body_allowed:
        return None
    p = Path(html_path)
    if not p.exists():
        return None
    try:
        html = p.read_text(encoding="utf-8", errors="replace")
    except Exception:   # noqa: BLE001
        return None
    # 텍스트 추출은 ingestion 측에서 이미 했지만 here 도 재 추출 가능.
    from autograph.ingestion.oem_ir_newsroom import _extract_text
    _title, body = _extract_text(html)
    return body[:200_000] if body else None   # 매우 큰 페이지는 cap


def _coerce_snapshot_year(published_date: str | None) -> int | None:
    if not published_date:
        return None
    m = _DATE_RE.match(published_date)
    return int(m.group(1)) if m else None


def _upsert_row(cur, *, oem: str, meta: dict, body_text: str | None) -> bool:
    """RETURN is_new."""
    cur.execute("""
        INSERT INTO anxg_auto.events_oem_news
          (oem, oem_corp_code, url, title, published_date, section,
           body_text, body_html_path, source, snapshot_year,
           license_tier, raw)
        VALUES (%s, %s, %s, %s, NULLIF(%s,'')::date, %s,
                %s, %s, %s, %s,
                %s, %s::jsonb)
        ON CONFLICT (oem, url) DO UPDATE SET
          title          = EXCLUDED.title,
          published_date = COALESCE(EXCLUDED.published_date,
                                     anxg_auto.events_oem_news.published_date),
          section        = EXCLUDED.section,
          body_text      = EXCLUDED.body_text,
          body_html_path = EXCLUDED.body_html_path,
          snapshot_year  = COALESCE(EXCLUDED.snapshot_year,
                                     anxg_auto.events_oem_news.snapshot_year),
          license_tier   = EXCLUDED.license_tier,
          raw            = EXCLUDED.raw,
          updated_at     = now()
        RETURNING (xmax = 0) AS is_new
    """, (
        oem,
        _OEM_CORP_CODE.get(oem),
        meta["url"],
        meta.get("title"),
        meta.get("published_date") or "",
        meta.get("section"),
        body_text,
        meta.get("body_html_path"),
        meta.get("source") or f"{oem}_ir",
        _coerce_snapshot_year(meta.get("published_date")),
        license_policy(f"{oem}_ir"),
        json.dumps(meta, ensure_ascii=False),
    ))
    return bool(cur.fetchone()[0])


def run_oem(oem: str, *, dry_run: bool = False) -> dict:
    """단일 OEM 의 _meta.jsonl + HTML → PG UPSERT."""
    pol = OEM_NEWSROOM_POLICY.get(oem)
    if pol is None:
        log.warning("[load:oem_ir:%s] 정책 미정 — skip", oem)
        return {"inserted": 0, "updated": 0, "skipped": 0,
                "metadata_only": 0, "rejected": 0}

    license_key = f"{oem}_ir"
    tier = license_policy(license_key)
    body_allowed = allow_body(license_key) or tier == "public_partial"
    metadata_only = tier == "metadata_only"
    if tier in ("copyrighted",):
        log.warning("[load:oem_ir:%s] 라이선스 'copyrighted' — 전체 skip", oem)
        return {"inserted": 0, "updated": 0, "skipped": 0,
                "metadata_only": 0, "rejected": 1}

    meta_p = _meta_path(oem)
    if not meta_p.exists():
        log.warning("[load:oem_ir:%s] %s 없음 — graceful skip", oem, meta_p)
        return {"inserted": 0, "updated": 0, "skipped": 0,
                "metadata_only": 0, "rejected": 0}

    rows = list(_iter_meta(oem))
    log.info("[load:oem_ir:%s] %d meta rows (tier=%s body_allowed=%s)",
             oem, len(rows), tier, body_allowed)

    if dry_run:
        return {
            "n_rows": len(rows),
            "tier": tier,
            "body_allowed": body_allowed,
            "metadata_only": int(metadata_only),
            "inserted": 0, "updated": 0, "skipped": 0,
        }

    from autonexusgraph.db.postgres import get_connection
    conn = get_connection()
    ins = upd = skip = 0
    meta_only_count = 0
    with conn.cursor() as cur:
        for meta in rows:
            if "url" not in meta:
                skip += 1
                continue
            body = (_read_body_text(meta.get("body_html_path") or "",
                                      body_allowed=body_allowed)
                    if not metadata_only else None)
            if metadata_only:
                meta_only_count += 1
            cur.execute("SAVEPOINT sp_oem_ir")
            try:
                if _upsert_row(cur, oem=oem, meta=meta, body_text=body):
                    ins += 1
                else:
                    upd += 1
                cur.execute("RELEASE SAVEPOINT sp_oem_ir")
            except Exception as exc:   # noqa: BLE001
                cur.execute("ROLLBACK TO SAVEPOINT sp_oem_ir")
                log.warning("[load:oem_ir:%s] %s 실패: %s",
                            oem, meta.get("url"), exc)
                skip += 1

    conn.commit()
    log.info("[load:oem_ir:%s] inserted=%d updated=%d skipped=%d "
             "metadata_only=%d",
             oem, ins, upd, skip, meta_only_count)
    return {"inserted": ins, "updated": upd, "skipped": skip,
            "metadata_only": meta_only_count, "rejected": 0}


def run(*, oems: list[str] | None = None, dry_run: bool = False) -> dict:
    """전체 또는 명시 OEM 적재. 통계 누계."""
    targets = oems or sorted(OEM_NEWSROOM_POLICY.keys())
    total = {"inserted": 0, "updated": 0, "skipped": 0,
             "metadata_only": 0, "rejected": 0, "by_oem": {}}
    for oem in targets:
        stats = run_oem(oem, dry_run=dry_run)
        total["by_oem"][oem] = stats
        for k in ("inserted", "updated", "skipped",
                   "metadata_only", "rejected"):
            total[k] += stats.get(k, 0)
    return total


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--oem", action="append", default=None,
                    help="대상 OEM (반복 가능). 미지정 시 등록된 OEM 전체.")
    ap.add_argument("--all", action="store_true",
                    help="--oem 미지정과 동일 — 전체 OEM")
    ap.add_argument("--dry-run", action="store_true",
                    help="PG 호출 없이 통계만")
    ap.add_argument("--log-level", default="INFO")
    args = ap.parse_args()
    logging.basicConfig(level=args.log_level,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    out = run(oems=args.oem, dry_run=args.dry_run)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())


__all__ = ["run", "run_oem"]

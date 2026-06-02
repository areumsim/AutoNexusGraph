"""USPTO Open Data Portal (data.uspto.gov) bulk dataset adapter — docs/ipgraph.md §5.

PatentsView 후속 (2026-03-20 이관 완료, REST 종료 → bulk dataset).

수집 대상 (모두 무인증):
- granted patents bulk     — pub_no / app_no / title / abstract / filing_date / grant_date
- assignees bulk           — assignee_id / name / type / country
- citations bulk           — citing_pub_no / cited_pub_no / citation_type
- inventors bulk           — inventor_id / name / country

본 단계는 **wire-up + graceful skip**: bulk dataset 다운로드 URL/포맷이 분기별로
변동하므로 사용자 환경에서 ``data/raw/ip/uspto_odp/`` 에 jsonl/csv 파일이 있으면
parse + 적재, 없으면 0 row + warning.

CLI:
    python -m ipgraph.ingestion.uspto_odp
    python -m ipgraph.ingestion.uspto_odp --dry-run
    python -m ipgraph.ingestion.uspto_odp --limit 100
"""

from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

ROOT = Path(__file__).resolve().parents[3]
RAW_DIR = ROOT / "data" / "raw" / "ip" / "uspto_odp"

log = logging.getLogger(__name__)


# Bulk dataset 안내 (사용자 다운로드 가이드).
USPTO_ODP_BULK_URL = "https://data.uspto.gov/bulkdata/datasets"


def _ensure_raw_dir() -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    return RAW_DIR


def _iter_jsonl(path: Path) -> Iterator[dict]:
    """jsonl 파일 stream (lazy)."""
    if not path.exists():
        return
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def collect_patents(*, limit: int | None = None) -> list[dict]:
    """``raw/ip/uspto_odp/patents.jsonl`` 의 USPTO 특허 stream → 정규화."""
    raw_dir = _ensure_raw_dir()
    fp = raw_dir / "patents.jsonl"
    if not fp.exists():
        log.warning("[uspto_odp] patents.jsonl 없음 (%s) — bulk download 필요. 가이드: %s",
                    fp, USPTO_ODP_BULK_URL)
        return []

    snapshot_year = datetime.now(timezone.utc).year
    out: list[dict] = []
    for i, r in enumerate(_iter_jsonl(fp)):
        if limit and i >= limit:
            break
        out.append({
            "pub_no":         r.get("publication_number") or r.get("pub_no") or "",
            "app_no":         r.get("application_number") or r.get("app_no"),
            "title":          r.get("title"),
            "abstract":       r.get("abstract"),
            "filing_date":    r.get("filing_date"),
            "grant_date":     r.get("grant_date"),
            "kind":           r.get("kind") or r.get("kind_code"),
            "jurisdiction":   "US",
            "source":         "uspto_odp",
            "snapshot_year":  snapshot_year,
            "schema_version": "v2.2",
        })
    return out


def collect_assignees(*, limit: int | None = None) -> list[dict]:
    """``raw/ip/uspto_odp/assignees.jsonl`` 의 출원인 stream."""
    raw_dir = _ensure_raw_dir()
    fp = raw_dir / "assignees.jsonl"
    if not fp.exists():
        log.warning("[uspto_odp] assignees.jsonl 없음 (%s) — bulk download 필요", fp)
        return []
    snapshot_year = datetime.now(timezone.utc).year
    out: list[dict] = []
    for i, r in enumerate(_iter_jsonl(fp)):
        if limit and i >= limit:
            break
        name = r.get("organization") or r.get("name") or ""
        out.append({
            "assignee_id":    r.get("assignee_id") or r.get("id"),
            "name":           name,
            "name_norm":      name.lower().strip() if name else None,
            "country":        r.get("country"),
            "type":           r.get("type", "company"),
            "wikidata_qid":   r.get("wikidata_qid"),
            "snapshot_year":  snapshot_year,
            "schema_version": "v2.2",
        })
    return out


def collect_inventors(*, limit: int | None = None) -> list[dict]:
    """``raw/ip/uspto_odp/inventors.jsonl`` 의 발명자 stream."""
    raw_dir = _ensure_raw_dir()
    fp = raw_dir / "inventors.jsonl"
    if not fp.exists():
        log.warning("[uspto_odp] inventors.jsonl 없음 (%s) — bulk download 필요", fp)
        return []
    out: list[dict] = []
    for i, r in enumerate(_iter_jsonl(fp)):
        if limit and i >= limit:
            break
        name = r.get("name_first") and r.get("name_last") and \
               f"{r['name_first']} {r['name_last']}" or r.get("name") or ""
        out.append({
            "inventor_id":    r.get("inventor_id") or r.get("id"),
            "name":           name,
            "name_norm":      name.lower().strip() if name else None,
            "country":        r.get("country"),
            "schema_version": "v2.2",
        })
    return out


def collect_citations(*, limit: int | None = None) -> list[dict]:
    """``raw/ip/uspto_odp/citations.jsonl`` 의 인용 stream."""
    raw_dir = _ensure_raw_dir()
    fp = raw_dir / "citations.jsonl"
    if not fp.exists():
        log.warning("[uspto_odp] citations.jsonl 없음 (%s) — bulk download 필요", fp)
        return []
    snapshot_year = datetime.now(timezone.utc).year
    out: list[dict] = []
    for i, r in enumerate(_iter_jsonl(fp)):
        if limit and i >= limit:
            break
        out.append({
            "citing_pub_no":  r.get("citing") or r.get("citing_pub_no"),
            "cited_pub_no":   r.get("cited") or r.get("cited_pub_no"),
            "citation_type":  r.get("category") or r.get("citation_type"),
            "snapshot_year":  snapshot_year,
            "schema_version": "v2.2",
        })
    return out


def collect_patent_assignees(*, limit: int | None = None) -> list[dict]:
    """``raw/ip/uspto_odp/patent_assignees.jsonl`` — Patent↔Assignee 다대다 link.

    각 row: {pub_no, assignee_id, sequence}. sequence 는 USPTO 의 출원인 순서.
    """
    raw_dir = _ensure_raw_dir()
    fp = raw_dir / "patent_assignees.jsonl"
    if not fp.exists():
        log.warning("[uspto_odp] patent_assignees.jsonl 없음 (%s)", fp)
        return []
    out: list[dict] = []
    for i, r in enumerate(_iter_jsonl(fp)):
        if limit and i >= limit:
            break
        out.append({
            "pub_no":      r.get("pub_no") or r.get("publication_number"),
            "assignee_id": r.get("assignee_id"),
            "sequence":    r.get("sequence"),
        })
    return out


def collect_patent_inventors(*, limit: int | None = None) -> list[dict]:
    """``raw/ip/uspto_odp/patent_inventors.jsonl`` — Patent↔Inventor 다대다 link."""
    raw_dir = _ensure_raw_dir()
    fp = raw_dir / "patent_inventors.jsonl"
    if not fp.exists():
        log.warning("[uspto_odp] patent_inventors.jsonl 없음 (%s)", fp)
        return []
    out: list[dict] = []
    for i, r in enumerate(_iter_jsonl(fp)):
        if limit and i >= limit:
            break
        out.append({
            "pub_no":      r.get("pub_no") or r.get("publication_number"),
            "inventor_id": r.get("inventor_id"),
            "sequence":    r.get("sequence"),
        })
    return out


def collect_patent_cpc(*, limit: int | None = None) -> list[dict]:
    """``raw/ip/uspto_odp/patent_cpc.jsonl`` — Patent ↔ CPC 코드 link."""
    raw_dir = _ensure_raw_dir()
    fp = raw_dir / "patent_cpc.jsonl"
    if not fp.exists():
        log.warning("[uspto_odp] patent_cpc.jsonl 없음 (%s)", fp)
        return []
    out: list[dict] = []
    for i, r in enumerate(_iter_jsonl(fp)):
        if limit and i >= limit:
            break
        out.append({
            "pub_no":       r.get("pub_no") or r.get("publication_number"),
            "cpc_code":     r.get("cpc_code") or r.get("code"),
            "primary_flag": bool(r.get("primary_flag", False)),
        })
    return out


def collect(*, limit: int | None = None, dry_run: bool = False) -> dict[str, Any]:
    """USPTO ODP bulk 일괄 수집 — 7 table 전 종류."""
    patents = collect_patents(limit=limit)
    assignees = collect_assignees(limit=limit)
    inventors = collect_inventors(limit=limit)
    citations = collect_citations(limit=limit)
    patent_assignees = collect_patent_assignees(limit=limit)
    patent_inventors = collect_patent_inventors(limit=limit)
    patent_cpc = collect_patent_cpc(limit=limit)
    out: dict[str, Any] = {
        "n_patents":          len(patents),
        "n_assignees":        len(assignees),
        "n_inventors":        len(inventors),
        "n_citations":        len(citations),
        "n_patent_assignees": len(patent_assignees),
        "n_patent_inventors": len(patent_inventors),
        "n_patent_cpc":       len(patent_cpc),
        "raw_dir":            str(RAW_DIR),
    }
    if dry_run:
        out["patents_head"]   = patents[:3]
        out["assignees_head"] = assignees[:3]
        out["citations_head"] = citations[:3]
    return out


def main() -> int:
    p = argparse.ArgumentParser(prog="ipgraph.ingestion.uspto_odp",
                                 description=__doc__.split("\n")[0])
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--limit", type=int, default=None,
                   help="각 파일별 첫 N row (smoke test)")
    p.add_argument("--log-level", default="INFO")
    args = p.parse_args()
    logging.basicConfig(level=args.log_level, format="%(levelname)s %(message)s")

    result = collect(limit=args.limit, dry_run=args.dry_run)
    print(f"[uspto_odp] {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

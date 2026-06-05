"""CPC scheme bulk 수집 — docs/ipgraph.md §5.

USPTO / EPO 공식 bulk text (무인증 즉시). 본 ingester 는 다운로드 + 정규화 후
``raw/ip/cpc_scheme/*.txt`` 에 저장. load 는 별도 (loaders/load_cpc_neo4j.py).

CPC 코드 계층 (PRD §6.7, depth ≥ 4):
    section (1자) → class (3자) → subclass (4자) → maingroup → subgroup
    예: A → A47 → A47C → A47C 1/00 → A47C 1/02

USPTO bulk URL:
    https://www.cooperativepatentclassification.org/Archive/  (zip → bulk text)

본 단계는 **수집 wire-up + graceful skip**: 네트워크 미접근 시 manual seed 파일
(``data/raw/ip/cpc_scheme/manual_cpc.tsv``) 사용 가능. 자세한 다운로드 절차는
README 의 IPGraph 섹션 참조.

CLI:
    python -m ipgraph.ingestion.cpc_scheme
    python -m ipgraph.ingestion.cpc_scheme --dry-run
    python -m ipgraph.ingestion.cpc_scheme --source-url <custom-url>
"""

from __future__ import annotations

import argparse
import csv
import logging
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RAW_DIR = ROOT / "data" / "raw" / "ip" / "cpc_scheme"

log = logging.getLogger(__name__)


# 공식 다운로드 페이지. zip 직접 링크는 분기 별로 변동 — README 가이드 권장.
DEFAULT_INDEX_URL = "https://www.cooperativepatentclassification.org/Archive/"


def _ensure_raw_dir() -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    return RAW_DIR


def _level_from_code(code: str) -> str:
    """CPC 코드 패턴 → level 추출."""
    code = code.strip()
    if len(code) == 1 and code[0].isalpha():
        return "section"
    if len(code) == 3 and code[0].isalpha() and code[1:].isdigit():
        return "class"
    if len(code) == 4 and code[3].isalpha():
        return "subclass"
    if "/" in code:
        suffix = code.split("/")[-1]
        if suffix == "00":
            return "maingroup"
        return "subgroup"
    return "unknown"


def _parent_from_code(code: str) -> str | None:
    """CPC 코드 → 부모 코드 (계층 1단계 위)."""
    code = code.strip()
    if "/" in code:
        head, tail = code.split("/", 1)
        if tail != "00":
            # subgroup → maingroup (.../00)
            return f"{head}/00"
        # maingroup → subclass (4자)
        return head
    if len(code) == 4:    # subclass → class
        return code[:3]
    if len(code) == 3:    # class → section
        return code[:1]
    return None


def normalize_row(code: str, title: str, *, snapshot_year: int,
                  schema_version: str = "v2.2") -> dict:
    code = (code or "").strip().replace("  ", " ")
    return {
        "code": code,
        "level": _level_from_code(code),
        "title": (title or "").strip(),
        "parent_code": _parent_from_code(code),
        "snapshot_year": snapshot_year,
        "schema_version": schema_version,
    }


def parse_tsv(path: Path, *, snapshot_year: int) -> list[dict]:
    """TSV (code\\ttitle) 형식 파싱. 빈 라인 / 주석 (# prefix) 무시."""
    if not path.exists():
        return []
    rows: list[dict] = []
    with path.open(encoding="utf-8") as f:
        reader = csv.reader(f, delimiter="\t")
        for r in reader:
            if not r or len(r) < 2:
                continue
            code = r[0].strip()
            if not code or code.startswith("#"):
                continue
            title = r[1].strip() if len(r) > 1 else ""
            rows.append(normalize_row(code, title, snapshot_year=snapshot_year))
    return rows


def _download_index(url: str, target: Path) -> bool:
    """공식 다운로드 페이지 1회 fetch — graceful fail-soft."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "AutoNexusGraph/IPG"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            target.write_bytes(resp.read())
        return True
    except Exception as e:   # noqa: BLE001 — fail-soft 흡수 → False 반환 (log 동반)
        log.warning("[cpc] index 다운로드 실패 (graceful skip): %s", e)
        return False


def collect(*, source_url: str = DEFAULT_INDEX_URL,
            manual_seed: Path | None = None,
            dry_run: bool = False) -> dict:
    """CPC bulk 수집 진입점.

    수집 우선순위:
        1. manual_seed (제공 시) — TSV 파일
        2. RAW_DIR/manual_cpc.tsv (기본 manual seed)
        3. source_url 다운로드 시도 — 실패 시 0 row

    Returns: {"n_rows": int, "source": str, "rows": list[dict] (dry_run 시만 채움)}
    """
    raw_dir = _ensure_raw_dir()
    seed = manual_seed or (raw_dir / "manual_cpc.tsv")
    snapshot_year = datetime.now(timezone.utc).year

    if seed.exists():
        rows = parse_tsv(seed, snapshot_year=snapshot_year)
        log.info("[cpc] manual seed (%s): %d rows", seed, len(rows))
        out = {"n_rows": len(rows), "source": str(seed), "snapshot_year": snapshot_year}
        if dry_run:
            out["rows"] = rows[:10]
        return out

    # manual seed 없음 — 공식 페이지 fetch 시도 (현재 zip 파싱 미구현 → graceful skip).
    index_path = raw_dir / "cpc_index.html"
    fetched = _download_index(source_url, index_path)
    if not fetched:
        log.warning("[cpc] manual_seed 없음 + 다운로드 실패 — 0 row 적재 skip")
        return {"n_rows": 0, "source": source_url, "snapshot_year": snapshot_year,
                "note": "manual seed 또는 zip 다운로드 + 파싱 필요 — README 참조"}

    # zip 파싱 — README 가이드 권장 (zip URL 분기 변동).
    log.info("[cpc] index 다운로드 성공 (%s) — zip 분기 별 파싱은 후속", index_path)
    return {"n_rows": 0, "source": str(index_path), "snapshot_year": snapshot_year,
            "note": "manual_cpc.tsv 작성 또는 zip 파싱 wire 필요"}


def main() -> int:
    p = argparse.ArgumentParser(prog="ipgraph.ingestion.cpc_scheme",
                                 description=__doc__.split("\n")[0])
    p.add_argument("--source-url", default=DEFAULT_INDEX_URL)
    p.add_argument("--manual-seed", type=Path, default=None)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--log-level", default="INFO")
    args = p.parse_args()
    logging.basicConfig(level=args.log_level, format="%(levelname)s %(message)s")

    result = collect(source_url=args.source_url,
                      manual_seed=args.manual_seed,
                      dry_run=args.dry_run)
    print(f"[cpc] n_rows={result['n_rows']} source={result['source']}")
    if args.dry_run and "rows" in result:
        for r in result["rows"]:
            print(f"  {r['code']:14s} [{r['level']:9s}] parent={r.get('parent_code')!s:8s} {r['title'][:60]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

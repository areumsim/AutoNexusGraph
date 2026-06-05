"""USGS Mineral Commodity Summaries (MCS) PDF → 구조화 dict 추출.

USGS 가 MCS 를 PDF 형태로만 배포 (https://pubs.usgs.gov/periodicals/mcs<year>/)
하기 때문에, raw PDF 를 ``data/raw/usgs_mcs/`` 에 보존하고 본 모듈에서
정형 표 (Salient Statistics + World Mine Production and Reserves) 를 텍스트
추출 후 정규식으로 파싱한다.

대상 광물 (배터리·소재 L6 시드): Li / Ni / Co / Mn / Graphite.

PDF 텍스트는 footnote superscript 가 숫자에 붙어 (e.g., "7240,000" 는 footnote 7
+ 240,000), 일부 가격 표는 다음 줄에 값이 배치된다. 본 파서는 5 광물의 row
패턴을 보수적으로 매칭하고, 신뢰성 검증을 위해 ``MIN_REASONABLE`` 범위 밖이면
보수적으로 reject (값 polluted → None) 한다.

API:
    fetch(commodity, year, *, raw_dir=None) -> Path   (다운로드 + 보존)
    parse(pdf_path, commodity_code) -> dict           (텍스트 → 구조화 dict)
    fetch_and_parse_all(...) -> list[dict]            (5 광물 × 최신 1년)

PRD §3.5: USGS MCS = A 등급 (US Gov 공식 통계), confidence 0.95.

라이선스: 공공 (US Gov, public domain).
"""

from __future__ import annotations

import json
import logging
import re
import sys
import urllib.request
from pathlib import Path
from typing import Any, Iterable

log = logging.getLogger(__name__)

_COMMODITY_TARGETS: dict[str, str] = {
    "lithium":   "Li",
    "nickel":    "Ni",
    "cobalt":    "Co",
    "manganese": "Mn",
    "graphite":  "Graphite",
}

_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "AutoNexusGraph/ingest-bot (+contact: ifkbn@kolon.com)"
)


# ── 1. 다운로드 ──────────────────────────────────────────────────

def _mcs_url(commodity_slug: str, year: int) -> str:
    return f"https://pubs.usgs.gov/periodicals/mcs{year}/mcs{year}-{commodity_slug}.pdf"


def fetch(commodity: str, year: int, *,
          raw_dir: Path | None = None) -> Path | None:
    if raw_dir is None:
        raw_dir = Path("data/raw/usgs_mcs")
    raw_dir.mkdir(parents=True, exist_ok=True)
    out = raw_dir / f"mcs{year}-{commodity}.pdf"
    if out.exists() and out.stat().st_size > 100_000:
        log.info("[usgs_mcs] already present: %s", out.name)
        return out
    url = _mcs_url(commodity, year)
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
    except Exception as exc:   # noqa: BLE001 — fail-soft 흡수 → None 반환 (log 동반)
        log.warning("[usgs_mcs] fetch fail %s/%s: %s", year, commodity, exc)
        return None
    if len(data) < 100_000:
        log.warning("[usgs_mcs] suspiciously small %s/%s: %d bytes",
                    year, commodity, len(data))
        return None
    out.write_bytes(data)
    log.info("[usgs_mcs] saved %s (%d bytes)", out.name, len(data))
    return out


# ── 2. 텍스트 추출 ─────────────────────────────────────────────────

def _extract_text(pdf_path: Path) -> str:
    import pypdf
    reader = pypdf.PdfReader(str(pdf_path))
    return "\n".join((p.extract_text() or "") for p in reader.pages)


# ── 3. 토큰 파싱 ──────────────────────────────────────────────────

# 수치 토큰: ">130,000,000" / "1,340" / "5.80" / "W" / "—" / "-"
# 콤마는 thousand separator 만 (3자리). 소수점 허용.
# 첫 alternative 는 `\d+(?:,\d{3})+` — '7204,000' (footnote prefix 포함) 까지 1 토큰.
_NUM_TOKEN_RE = re.compile(
    r">?\d+(?:,\d{3})+(?:\.\d+)?"        # 1+ digits + (,3digit)+
    r"|>?\d+(?:\.\d+)?"                  # plain number or >number
    r"|W|—|NA"
)

# footnote superscript 가 단일 숫자로 표시될 때 — 그 자체가 row 의 수치인지
# footnote 인지는 magnitude 로 판정.
_FOOTNOTE_DIGIT_RE = re.compile(r"^(\d)(\d{3,4},\d{3}.*)$")


def _coerce_num(tok: str | None) -> float | None:
    if tok is None:
        return None
    s = str(tok).strip()
    if s in ("", "W", "—", "-", "NA"):
        return None
    if s.startswith(">"):
        s = s[1:]
    s = s.replace(",", "")
    try:
        v = float(s)
        return v
    except (TypeError, ValueError):
        return None


def _strip_footnote_prefix(tok: str, *,
                            expected_max: float | None = None) -> str:
    """USGS PDF 추출 시 1-digit footnote 가 숫자 앞에 붙는 경우 제거.

    예: '7240,000' → '240,000' (lithium world total).
    expected_max 가 주어지면 magnitude 비교로 결정.
    """
    m = _FOOTNOTE_DIGIT_RE.match(tok)
    if not m:
        return tok
    stripped = m.group(2)
    if expected_max is not None:
        v_orig = _coerce_num(tok)
        v_strip = _coerce_num(stripped)
        if v_orig is None or v_strip is None:
            return tok
        if v_strip <= expected_max and v_orig > expected_max:
            return stripped
        return tok
    # expected_max 없으면 conservative — 안 자름.
    return tok


# ── 4. 라인 매칭 ──────────────────────────────────────────────────

def _find_row_with_n_nums(text: str, label_substring: str, *,
                          min_nums: int = 5,
                          start_idx: int = 0) -> tuple[list[str], int] | None:
    """``label_substring`` 을 포함하는 라인 중 **수치 토큰 ≥ min_nums** 인 첫
    라인을 우선 반환 (strict). 모든 라벨 라인이 부족하면 fallback 으로 라벨이
    있는 첫 라인의 +1/+2 (multi-line wrap) 에서 ≥ min_nums 검색.

    Returns: ([token_str, ...], line_index_in_text)
    """
    lines = text.splitlines()
    label_lower = label_substring.lower()
    label_lines: list[tuple[int, str]] = []
    for i in range(start_idx, len(lines)):
        if label_lower in lines[i].lower():
            label_lines.append((i, lines[i]))
    # 1차: strict — 라벨 라인 그 자체에 min_nums 이상.
    for i, line in label_lines:
        idx = line.lower().find(label_lower)
        tail = line[idx + len(label_substring):]
        tokens = _NUM_TOKEN_RE.findall(tail)
        if len(tokens) >= min_nums:
            return tokens, i
    # 2차: wrap — 라벨 라인의 다음 1~2 줄에서 검색.
    for i, line in label_lines:
        for j in (i + 1, i + 2):
            if j >= len(lines):
                break
            next_tokens = _NUM_TOKEN_RE.findall(lines[j])
            if len(next_tokens) >= min_nums:
                return next_tokens, j
    return None


def _find_world_total(text: str) -> tuple[str, str, str] | None:
    """마지막 'World total' 줄의 (prev, curr, reserves) 3 토큰."""
    lines = text.splitlines()
    for i in range(len(lines) - 1, -1, -1):
        line = lines[i]
        if "World total" not in line:
            continue
        tokens = _NUM_TOKEN_RE.findall(line)
        if len(tokens) >= 3:
            return tokens[-3], tokens[-2], tokens[-1]
    return None


# ── 5. commodity 별 매핑 ─────────────────────────────────────────

# (label_substring, min_nums_required, footnote_max_for_world_prefix_strip)
# expected_world_max → 5종의 합리적 world production 상한 (footnote 제거 판정).
_COMMODITY_SPEC: dict[str, dict[str, Any]] = {
    "Li": {
        "salient_year_offset": -1,  # mcs2025 → 2024 estimate
        "world_unit_multiplier": 1,
        "expected_world_production_max": 1_000_000,   # < 1M tons
        "expected_world_reserves_max":  500_000_000,
        "rows": {
            "us_imports":           ("Imports for consumption", 5),
            "us_exports":           ("Exports", 5),
            "us_import_reliance":   ("Net import reliance", 5),
            "price_usd_per_ton":    ("dollars per metric ton", 5),
        },
    },
    "Ni": {
        "salient_year_offset": -1,
        "world_unit_multiplier": 1,
        "expected_world_production_max": 10_000_000,
        "expected_world_reserves_max":  500_000_000,
        "rows": {
            "us_mine_production":   ("Mine ", 5),                # 'Mine 16,700 18,400 17,500 16,400 8,000'
            "price_usd_per_ton":    ("Dollars per metric ton", 5),
            "us_import_reliance":   ("apparent consumptione", 5),  # 'as a percentage of total apparent consumptione 46 49 55 53 48'
        },
    },
    "Co": {
        "salient_year_offset": -1,
        "world_unit_multiplier": 1,
        "expected_world_production_max": 1_000_000,
        "expected_world_reserves_max":  100_000_000,
        "rows": {
            "us_mine_production":   ("Mine ", 5),
            "us_imports":           ("Imports for consumption", 5),
            "us_exports":           ("Exports", 5),
            "us_import_reliance":   ("Net import reliance", 5),
            "price_usd_per_lb_lme": ("London Metal Exchange (LME), cash", 5),
        },
    },
    "Mn": {
        "salient_year_offset": -1,
        "world_unit_multiplier": 1000,  # 'thousand metric tons'
        "expected_world_production_max": 50_000_000,
        "expected_world_reserves_max":  5_000_000_000,
        "rows": {
            "us_import_reliance":   ("apparent consumption, ", 5),  # 'manganese content 100 100 100 100 100'
            "price_usd_per_dmtu":   ("metric ton unit", 5),
        },
    },
    "Graphite": {
        "salient_year_offset": -1,
        "world_unit_multiplier": 1,
        "expected_world_production_max": 5_000_000,
        "expected_world_reserves_max":  500_000_000,
        "rows": {
            "us_imports":           ("Imports for consumption", 5),
            "us_exports":           ("Exports", 5),
            "us_import_reliance":   ("Net import reliance", 5),
            "price_usd_per_ton":    ("Flake ", 5),
        },
    },
}


# ── 6. 파서 ─────────────────────────────────────────────────────

def parse(pdf_path: Path, commodity_code: str) -> dict | None:
    """PDF 1개 → 정형 dict."""
    try:
        text = _extract_text(pdf_path)
    except Exception as exc:   # noqa: BLE001 — fail-soft 흡수 → None 반환 (log 동반)
        log.warning("[usgs_mcs:parse] %s 텍스트 추출 실패: %s", pdf_path.name, exc)
        return None

    m = re.match(r"mcs(\d{4})-", pdf_path.name)
    if not m:
        log.warning("[usgs_mcs:parse] 파일명에서 연도 추출 실패: %s", pdf_path.name)
        return None
    mcs_year = int(m.group(1))
    snapshot_year = mcs_year + _COMMODITY_SPEC.get(commodity_code, {}).get(
        "salient_year_offset", -1)

    spec = _COMMODITY_SPEC.get(commodity_code)
    if not spec:
        log.warning("[usgs_mcs:parse] commodity %s spec 없음", commodity_code)
        return None

    out: dict[str, Any] = {
        "commodity": commodity_code,
        "snapshot_year": snapshot_year,
        "mcs_publication_year": mcs_year,
        "source_pdf": pdf_path.name,
    }

    # 6-1. Salient Statistics rows.
    for col, (label, min_n) in spec["rows"].items():
        found = _find_row_with_n_nums(text, label, min_nums=min_n)
        if not found:
            continue
        tokens, _line_idx = found
        val = _coerce_num(tokens[-1])   # 최신 estimate column (5번째).
        out[col] = val

    # 6-2. Price unit 정규화.
    if commodity_code == "Co" and out.get("price_usd_per_lb_lme") is not None:
        out["price_usd_per_ton"] = round(float(out["price_usd_per_lb_lme"]) * 2204.62, 2)
    if commodity_code == "Mn":
        # dmtu unit 으로는 정규 price 변환 어려움 → null.
        out["price_usd_per_ton"] = None

    # 6-3. World total row.
    world = _find_world_total(text)
    mult = spec.get("world_unit_multiplier", 1)
    exp_prod = spec.get("expected_world_production_max")
    exp_res  = spec.get("expected_world_reserves_max")
    if world:
        _prev, curr, reserves = world
        curr = _strip_footnote_prefix(curr, expected_max=exp_prod)
        reserves = _strip_footnote_prefix(reserves, expected_max=exp_res)
        v_curr = _coerce_num(curr)
        v_res  = _coerce_num(reserves)
        if v_curr is not None:
            out["world_production"] = int(v_curr * mult)
        if v_res is not None:
            out["world_reserves"] = int(v_res * mult)

    # 6-4. Sanity check — out-of-range 값은 reject.
    if exp_prod and out.get("world_production") is not None:
        if out["world_production"] > exp_prod * 10:
            log.warning("[usgs_mcs:parse] %s world_production sanity fail: %s",
                        commodity_code, out["world_production"])
            out["world_production"] = None

    out["raw"] = {
        "mcs_publication_year": mcs_year,
        "snapshot_year_estimate": True,
        "source_url": _mcs_url(
            next((s for s, c in _COMMODITY_TARGETS.items() if c == commodity_code), ""),
            mcs_year),
    }
    return out


# ── 7. fetch + parse 일괄 ────────────────────────────────────────

def fetch_and_parse_all(*, year: int = 2025,
                         commodities: Iterable[str] | None = None,
                         raw_dir: Path | None = None) -> list[dict]:
    commodities = list(commodities) if commodities else list(_COMMODITY_TARGETS.keys())
    rows: list[dict] = []
    for slug in commodities:
        code = _COMMODITY_TARGETS.get(slug, slug)
        pdf = fetch(slug, year, raw_dir=raw_dir)
        if pdf is None:
            log.warning("[usgs_mcs] %s/%s skip — fetch fail", year, slug)
            continue
        parsed = parse(pdf, code)
        if parsed is None:
            log.warning("[usgs_mcs] %s/%s skip — parse fail", year, slug)
            continue
        rows.append(parsed)
    return rows


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=2025)
    ap.add_argument("--commodities", nargs="*", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--log-level", default="INFO")
    args = ap.parse_args(argv)
    logging.basicConfig(level=args.log_level,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    rows = fetch_and_parse_all(year=args.year, commodities=args.commodities)
    out_str = json.dumps(rows, ensure_ascii=False, indent=2, default=str)
    if args.out:
        Path(args.out).write_text(out_str, encoding="utf-8")
        log.info("[usgs_mcs] wrote %s rows → %s", len(rows), args.out)
    else:
        print(out_str)
    return 0


if __name__ == "__main__":
    sys.exit(main())


__all__ = [
    "fetch",
    "parse",
    "fetch_and_parse_all",
    "_COMMODITY_TARGETS",
]

"""Wikidata 배터리 셀 chemistry 수집 — docs/autograph.md §2.5.4 (L6 부분 진입).

PRD v2.2 §2.3 — 배터리·소재 L5/L6 부분 진입.
materials_seed.yaml 의 manual seed (NCM811/LFP 등) 보강 — Wikidata SPARQL 로
chemistry family / cathode ratio / Q-IDs 동적 수집.

회사단위 셀↔OEM 소싱 (어느 OEM 이 어느 셀을 쓰는가) — Wikidata 가 sparse → **grade C
candidate** 로만 표기 (PRD v2.2 §2.3 명시).

라이선스: Wikidata = CC0 (본문 저장 OK, 무조건 자유).

CLI:
    python -m autograph.ingestion.wikidata_cell_chem
    python -m autograph.ingestion.wikidata_cell_chem --dry-run
    python -m autograph.ingestion.wikidata_cell_chem --limit 20
"""

from __future__ import annotations

import argparse
import json
import logging
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RAW_DIR = ROOT / "data" / "raw" / "auto" / "wikidata_cell_chem"

log = logging.getLogger(__name__)


WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"

# Cathode chemistry families — 배터리 cell 의 Wikidata Q-ID seed.
# 더 넓은 SPARQL 쿼리는 본 모듈 확장 — 본 wire-up 단계는 seed 5종.
CATHODE_QIDS = {
    "Q899037":  "Lithium-ion battery",            # 상위 카테고리.
    "Q1126478": "NCA cathode",                    # Nickel Cobalt Aluminum.
    "Q900614":  "NCM cathode",                    # Nickel Cobalt Manganese.
    "Q1411884": "LFP cathode",                    # Lithium iron phosphate.
    "Q1142080": "LCO cathode",                    # Lithium cobalt oxide.
    "Q900541":  "LMO cathode",                    # Lithium manganese oxide.
}

# SPARQL — cathode chemistry meta + 셀 제조사 매핑 (sparse).
# 본 쿼리는 manufacturer 직접 매칭이 약함 (Wikidata 의 P176/manufacturer 부재).
# → 결과는 chemistry 정의 위주, 회사 매핑은 별도 grade C candidate 추출.
_CATHODE_QUERY_TEMPLATE = """
SELECT ?chem ?chemLabel ?chemDesc ?formula ?wikidata_qid
WHERE {{
  VALUES ?chem {{ {qid_values} }}
  OPTIONAL {{ ?chem wdt:P274 ?formula }}
  BIND(STRAFTER(STR(?chem), "entity/") AS ?wikidata_qid)
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}}
LIMIT 50
"""


def _sparql(query: str) -> dict:
    """Wikidata SPARQL endpoint fetch — fail-soft."""
    url = f"{WIKIDATA_SPARQL}?{urllib.parse.urlencode({'query': query, 'format': 'json'})}"
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "AutoNexusGraph/Research (https://github.com/)",
            "Accept":     "application/sparql-results+json",
        })
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:   # noqa: BLE001
        log.warning("[wikidata_cell_chem] SPARQL 실패 (graceful skip): %s", e)
        return {}


def collect(*, limit: int | None = None, dry_run: bool = False) -> dict:
    """Wikidata cathode chemistry 메타 수집 — raw 저장 + 정규화 dict 반환.

    Returns:
        ``{"n_rows": int, "rows": [dict] (dry_run 시), "source": "wikidata"}``
    """
    raw_dir = RAW_DIR
    raw_dir.mkdir(parents=True, exist_ok=True)

    qids = list(CATHODE_QIDS.keys())[: limit] if limit else list(CATHODE_QIDS.keys())
    qid_values = " ".join(f"wd:{q}" for q in qids)
    query = _CATHODE_QUERY_TEMPLATE.format(qid_values=qid_values)

    result = _sparql(query)
    if not result:
        log.info("[wikidata_cell_chem] SPARQL 응답 없음 — manual seed 보강은 skip")
        return {"n_rows": 0, "source": "wikidata", "skipped": True,
                "note": "network/SPARQL 실패. materials_seed.yaml 의 manual seed 활용"}

    bindings = (result.get("results") or {}).get("bindings", [])
    snapshot_year = datetime.now(timezone.utc).year
    rows: list[dict] = []
    for b in bindings:
        rows.append({
            "wikidata_qid":  b.get("wikidata_qid", {}).get("value"),
            "name":          b.get("chemLabel", {}).get("value"),
            "description":   b.get("chemDesc", {}).get("value"),
            "formula":       b.get("formula", {}).get("value"),
            "source":        "wikidata",
            "snapshot_year": snapshot_year,
            "schema_version": "v2.2",
            "confidence_score": 0.80,   # PRD §3.5 — Wikidata B 등급.
        })

    # raw 저장 (멱등).
    raw_path = raw_dir / f"cathode_chem_{snapshot_year}.json"
    raw_path.write_text(json.dumps({"snapshot_year": snapshot_year,
                                     "n_rows": len(rows), "rows": rows},
                                    ensure_ascii=False, indent=2),
                        encoding="utf-8")
    log.info("[wikidata_cell_chem] %d rows → %s", len(rows), raw_path)

    out = {"n_rows": len(rows), "source": "wikidata",
           "raw_path": str(raw_path), "snapshot_year": snapshot_year}
    if dry_run:
        out["rows"] = rows
    return out


def collect_oem_supplier_candidates(*, max_qids: int = 50) -> dict:
    """**Grade C candidate** — 어느 OEM 이 어느 셀 제조사 / chemistry 를 쓰는가.

    Wikidata 의 manufacturer P176 / used by P3940 등 활용 가능 — 단 sparse.
    PRD v2.2 §2.3 명시: "회사단위 셀↔OEM 소싱은 sparse → grade C candidate 정직 표기".

    본 함수는 별도 SPARQL 쿼리 — 적재 시 confidence_score=0.40, validated_status='candidate'.
    실제 SPARQL 패턴 구축은 후속 PR (manual 검토 거쳐야 grade 승급).
    """
    log.info("[wikidata_cell_chem] OEM↔셀 매핑 — grade C candidate 수집 (skeleton)")
    # 본 단계 wire-up — 실 SPARQL 패턴은 후속 (manual review queue).
    return {
        "n_candidates":  0,
        "max_qids":      max_qids,
        "grade":         "C",
        "note":          "PRD v2.2 §2.3 — sparse 데이터 정직 표기. manual 검토 후 승급.",
    }


def main() -> int:
    p = argparse.ArgumentParser(prog="autograph.ingestion.wikidata_cell_chem",
                                 description=__doc__.split("\n")[0])
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--oem-candidates", action="store_true",
                   help="grade C OEM↔셀 매핑 후보 수집 (별도)")
    p.add_argument("--log-level", default="INFO")
    args = p.parse_args()
    logging.basicConfig(level=args.log_level, format="%(levelname)s %(message)s")

    if args.oem_candidates:
        out = collect_oem_supplier_candidates()
    else:
        out = collect(limit=args.limit, dry_run=args.dry_run)
    print(f"[wikidata_cell_chem] {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

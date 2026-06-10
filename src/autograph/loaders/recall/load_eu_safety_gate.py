"""EU Safety Gate weekly XML → anxg_auto.events_recalls UPSERT.

가이드 §1 표 EU Safety Gate (RAPEX) — Layer 2 회사귀속 리콜. EU 시장 커버.
NHTSA(US) + KOTSA(KR) + EU = 3개 지역 L2.

raw 파일 위치: data/raw/eu_safety_gate/xml/weekly_*.xml
적재 키:      (source='eu_safety_gate', source_recall_no=<caseNumber>)

라이선스: CC BY 4.0 (Commission Decision 2011/833/EU). grade A (공식 EU).

XML 구조 (verified 2026-06-04):
    <Safety-Gate>
      <report_date>DD/MM/YYYY</report_date>
      <report_year>YYYY</report_year>
      <report_week>NN</report_week>
      <notifications>
        <caseNumber>A12/01239/20</caseNumber>
        <category>Motor vehicles</category>   <!-- 필터 키 -->
        <product>Passenger car</product>
        <brand>Ford</brand>
        <name>Mustang, Fusion, MKZ, ...</name>
        <type_numberOfModel>...</type_numberOfModel>
        <riskType>Injuries</riskType>
        <danger>...</danger>                  <!-- defect_summary 매핑 -->
        <description>...</description>
        <measures>...</measures>              <!-- remedy_summary 매핑 -->
        <countryOfOrigin>...</countryOfOrigin>
        <notifyingCountry>DE</notifyingCountry>  <!-- country 매핑 (ISO-2) -->
        <reference>https://.../alertDetail/<ID></reference>
      </notifications>
      ...
    </Safety-Gate>

CLI:
    python -m autograph.loaders.recall.load_eu_safety_gate
    python -m autograph.loaders.recall.load_eu_safety_gate --dry-run
    python -m autograph.loaders.recall.load_eu_safety_gate --xml-dir data/raw/eu_safety_gate/xml
"""

from __future__ import annotations

import argparse
import json
import logging
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from datetime import date, datetime
from pathlib import Path
from typing import Any

from autonexusgraph.db.postgres import get_connection

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[4]
DEFAULT_XML_DIR = ROOT / "data" / "raw" / "eu_safety_gate" / "xml"

_SOURCE = "eu_safety_gate"
_SCHEMA_VERSION = "eu_safety_gate_v1"

# EU brand → 우리 anxg_auto.master_manufacturers.name (영문 정규형) 매핑.
# 기존 한국 OEM alias dict 와 동일 패턴. 미매칭은 raw 에만 보관.
_EU_BRAND_ALIAS: dict[str, str] = {
    "Hyundai":           "HYUNDAI",
    "Kia":               "KIA",
    "Genesis":           "GENESIS",
    "Toyota":            "TOYOTA",
    "Lexus":             "LEXUS",
    "Honda":             "HONDA",
    "Nissan":            "NISSAN",
    "Mazda":             "MAZDA",
    "Subaru":            "SUBARU",
    "Mitsubishi":        "MITSUBISHI",
    "BMW":               "BMW",
    "Mercedes-Benz":     "MERCEDES-BENZ",
    "Mercedes Benz":     "MERCEDES-BENZ",
    "Mercedes":          "MERCEDES-BENZ",
    "Audi":              "AUDI",
    "Volkswagen":        "VOLKSWAGEN",
    "VW":                "VOLKSWAGEN",
    "Porsche":           "PORSCHE",
    "Volvo":             "VOLVO",
    "Renault":           "RENAULT",
    "Peugeot":           "PEUGEOT",
    "Citroen":           "CITROEN",
    "Citroën":           "CITROEN",
    "Opel":              "OPEL",
    "Vauxhall":          "VAUXHALL",
    "Fiat":              "FIAT",
    "Lancia":            "LANCIA",
    "Alfa Romeo":        "ALFA ROMEO",
    "Maserati":          "MASERATI",
    "Ferrari":           "FERRARI",
    "Lamborghini":       "LAMBORGHINI",
    "Bentley":           "BENTLEY",
    "Rolls-Royce":       "ROLLS-ROYCE",
    "Jaguar":            "JAGUAR",
    "Land Rover":        "LAND ROVER",
    "Mini":              "MINI",
    "MINI":              "MINI",
    "Ford":              "FORD",
    "Tesla":             "TESLA",
    "Chevrolet":         "CHEVROLET",
    "Chrysler":          "CHRYSLER",
    "Dodge":             "DODGE",
    "Jeep":              "JEEP",
    "Smart":             "SMART",
    "Skoda":             "SKODA",
    "Škoda":             "SKODA",
    "SEAT":              "SEAT",
    "Cupra":             "CUPRA",
    "Dacia":             "DACIA",
    "Suzuki":            "SUZUKI",
    "Iveco":             "IVECO",
    "MAN":               "MAN",
    "Scania":            "SCANIA",
    "DAF":               "DAF",
    "BMW Motorrad":      "BMW",
    "Harley-Davidson":   "HARLEY-DAVIDSON",
    "Ducati":            "DUCATI",
}


def _text(elem: ET.Element, tag: str) -> str | None:
    v = elem.findtext(tag)
    if v is None:
        return None
    s = v.strip()
    return s or None


def _parse_date_dmy(s: str | None) -> date | None:
    if not s:
        return None
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s.strip(), fmt).date()
        except ValueError:
            continue
    return None


def _iter_motor_notifications(xml_path: Path) -> Iterator[dict[str, Any]]:
    """weekly XML 파일에서 category='Motor vehicles' 알림만 yield."""
    try:
        root = ET.parse(xml_path).getroot()
    except ET.ParseError as e:
        log.warning("[eu_safety_gate] %s parse 실패: %s", xml_path.name, e)
        return
    report_date_s = root.findtext("report_date")
    report_year = root.findtext("report_year")
    report_week = root.findtext("report_week")
    rdate = _parse_date_dmy(report_date_s)
    for n in root.findall("notifications"):
        if _text(n, "category") != "Motor vehicles":
            continue
        yield {
            "report_date": rdate,
            "report_year": int(report_year) if report_year else None,
            "report_week": int(report_week) if report_week else None,
            "report_id":   xml_path.stem.replace("weekly_", ""),
            "case_number": _text(n, "caseNumber"),
            "product":     _text(n, "product"),
            "brand":       _text(n, "brand"),
            "name":        _text(n, "name"),
            "type_model":  _text(n, "type_numberOfModel"),
            "batch":       _text(n, "batchNumber"),
            "risk_type":   _text(n, "riskType"),
            "danger":      _text(n, "danger"),
            "description": _text(n, "description"),
            "measures":    _text(n, "measures"),
            "country_of_origin":  _text(n, "countryOfOrigin"),
            "notifying_country":  _text(n, "notifyingCountry"),
            "reference":   _text(n, "reference"),
            "production_dates": _text(n, "productionDates"),
            "company_recall_code": _text(n, "companyRecallCode"),
            "level":       _text(n, "level"),
        }


_ALIAS_LOWER = {k.lower(): v for k, v in _EU_BRAND_ALIAS.items()}

import html as _html  # noqa: E402 — 별칭 상수 정의 후 지역 배치(의도적)
import re as _re  # noqa: E402 — 별칭 상수 정의 후 지역 배치(의도적)


def _candidate_brands(brand: str) -> list[str]:
    """brand 텍스트 → 후보 brand 토큰 list (multi-brand split + 정규화)."""
    if not brand:
        return []
    s = _html.unescape(brand)              # &amp; → &
    s = s.strip().rstrip(".")               # OPEL. → OPEL
    # multi-brand split — '/', ',', ' and ', ' & '
    parts = _re.split(r"\s*[/,]\s*|\s+and\s+|\s*&\s*", s)
    return [p.strip() for p in parts if p.strip()]


def _resolve_manufacturer_id(cur, brand: str | None) -> int | None:
    """EU brand 텍스트 → anxg_auto.master_manufacturers.manufacturer_id.

    1) brand multi-split → 각 후보에 대해:
    2) _EU_BRAND_ALIAS (case-insensitive) → 영문 정규명
    3) anxg_auto.master_manufacturers.name 정확 매치 (case-insensitive)
    첫 매칭 반환. 모두 실패 시 NULL.
    """
    if not brand:
        return None
    for cand in _candidate_brands(brand):
        norm = _ALIAS_LOWER.get(cand.lower(), cand.upper())
        cur.execute("""
            SELECT manufacturer_id FROM anxg_auto.master_manufacturers
             WHERE upper(name) = %s LIMIT 1
        """, (norm,))
        r = cur.fetchone()
        if r:
            return r[0]
    return None


def collect_rows(xml_dir: Path | None = None) -> list[dict[str, Any]]:
    xml_dir = xml_dir or DEFAULT_XML_DIR
    if not xml_dir.exists():
        log.warning("[eu_safety_gate] xml_dir 없음: %s", xml_dir)
        return []
    rows: list[dict[str, Any]] = []
    files = sorted(xml_dir.glob("weekly_*.xml"))
    log.info("[eu_safety_gate] %d weekly XMLs", len(files))
    for fp in files:
        for n in _iter_motor_notifications(fp):
            rows.append(n)
    log.info("[eu_safety_gate] %d Motor vehicle 알림 수집", len(rows))
    return rows


_UPSERT_SQL = """
INSERT INTO anxg_auto.events_recalls (
    source, source_recall_no, manufacturer_id, model_id, variant_id,
    component_text, defect_summary, consequence, remedy_summary,
    report_date, country, affected_units,
    confidence, validated_status, snapshot_year, raw
) VALUES (
    %s, %s, %s, NULL, NULL,
    %s, %s, %s, %s,
    %s, %s, NULL,
    1.000, 'verified', %s, %s::jsonb
)
ON CONFLICT (source, source_recall_no) DO UPDATE SET
    manufacturer_id = COALESCE(EXCLUDED.manufacturer_id, anxg_auto.events_recalls.manufacturer_id),
    component_text  = EXCLUDED.component_text,
    defect_summary  = EXCLUDED.defect_summary,
    consequence     = EXCLUDED.consequence,
    remedy_summary  = EXCLUDED.remedy_summary,
    report_date     = EXCLUDED.report_date,
    country         = EXCLUDED.country,
    raw             = EXCLUDED.raw
"""


def upsert_pg(rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    conn = get_connection()
    n = 0
    skipped = 0
    with conn.cursor() as cur:
        for r in rows:
            cn = r["case_number"]
            if not cn:
                skipped += 1
                continue
            mfr_id = _resolve_manufacturer_id(cur, r.get("brand"))
            comp = (r.get("product") or "") + (" / " + r["name"] if r.get("name") else "")
            comp = comp[:400] if comp else None
            year = r["report_year"] or (r["report_date"].year if r.get("report_date") else None)
            cur.execute(_UPSERT_SQL, (
                _SOURCE, cn[:80], mfr_id,
                comp, r.get("danger"), r.get("risk_type"), r.get("measures"),
                r.get("report_date"),
                (r.get("notifying_country") or "")[:8] or None,
                year,
                json.dumps(r, ensure_ascii=False, default=str),
            ))
            n += cur.rowcount or 0
    conn.commit()
    log.info("[eu_safety_gate] upserted=%d skipped(no caseNumber)=%d", n, skipped)
    return n


def run(*, xml_dir: str | Path | None = None, dry_run: bool = False) -> dict[str, Any]:
    src = Path(xml_dir) if xml_dir else None
    rows = collect_rows(src)
    stats = {
        "xml_dir": str(src or DEFAULT_XML_DIR),
        "rows":    len(rows),
        "with_brand": sum(1 for r in rows if r.get("brand")),
        "with_danger": sum(1 for r in rows if r.get("danger")),
        "years":   sorted({r["report_year"] for r in rows if r.get("report_year")}),
        "upserted": 0,
    }
    if dry_run:
        return stats
    stats["upserted"] = upsert_pg(rows)
    return stats


def main() -> int:
    ap = argparse.ArgumentParser(prog="autograph.loaders.recall.load_eu_safety_gate",
                                  description=__doc__.split("\n")[0])
    ap.add_argument("--xml-dir", default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--log-level", default="INFO")
    args = ap.parse_args()
    logging.basicConfig(level=args.log_level,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    stats = run(xml_dir=args.xml_dir, dry_run=args.dry_run)
    print(json.dumps(stats, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

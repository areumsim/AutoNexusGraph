"""data.go.kr 15155857 — KOTSA 수리검사내역 → anxg_auto.events_inspections UPSERT.

raw 파일 위치: ``data/raw/auto/datagokr_inspections/<year>.jsonl``
             (ingestion.datagokr_inspections 가 CSV → JSONL normalize 한 후 생성)

raw 파일 없으면 graceful skip — exit 0.

CLI:
    python -m autograph.loaders.load_datagokr_inspections
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from autonexusgraph.config import get_settings
from autonexusgraph.db.postgres import get_connection
from autonexusgraph.ingestion._common import normalize_corp_name

log = logging.getLogger(__name__)


_SOURCE_PATH = "auto/datagokr_inspections"
_SOURCE_TAG = "datagokr_kotsa"


def _resolve_manufacturer_id(cur, raw_name: str | None) -> int | None:
    if not raw_name:
        return None
    norm = normalize_corp_name(raw_name)
    cur.execute("""
        SELECT manufacturer_id FROM anxg_auto.master_manufacturers
         WHERE name_norm = %s OR name = %s
         ORDER BY manufacturer_id LIMIT 1
    """, (norm, raw_name))
    r = cur.fetchone()
    return r[0] if r else None


def _find_inputs() -> tuple[list, str]:
    """JSONL 우선, 없으면 datagokr 디렉토리의 CSV 자동 사용.

    Returns (file_list, kind) where kind ∈ {'jsonl', 'csv', 'none'}.
    """
    raw_root = get_settings().ingest_raw_dir / _SOURCE_PATH
    if raw_root.exists():
        jsonls = sorted(raw_root.glob("*.jsonl"))
        if jsonls:
            return jsonls, "jsonl"

    # CSV fallback — data/raw/datagokr/*수리검사*.csv (사용자 수동 다운)
    csv_root = get_settings().ingest_raw_dir / "datagokr"
    if csv_root.exists():
        csvs = sorted(csv_root.glob("*수리검사*.csv"))
        if csvs:
            return csvs, "csv"
    return [], "none"


def _iter_csv_rows(csv_path):
    """CSV → row dict iter. utf-8/cp949 자동 감지."""
    import csv as _csv
    for enc in ("utf-8-sig", "utf-8", "cp949", "euc-kr"):
        try:
            with csv_path.open("r", encoding=enc, newline="") as f:
                head = f.read(2048)
                f.seek(0)
                if "검사" in head:
                    log.info("[load:inspections] %s encoding=%s",
                             csv_path.name, enc)
                    for row in _csv.DictReader(f):
                        yield row
                    return
        except UnicodeDecodeError:
            continue
    log.warning("[load:inspections] %s encoding 자동 감지 실패", csv_path.name)


def _csv_to_normalized(row: dict) -> dict:
    """KOTSA CSV row → 표준 schema dict.

    Source columns (UVTOTLOSSRS_T):
      검사소코드 / 접수일자 / 접수일련번호 / 접수횟수 / 특이사항코드
    """
    inspector_code = (row.get("검사소코드") or "").strip()
    inspected_at = (row.get("접수일자") or "").strip()
    seq = (row.get("접수일련번호") or "").strip()
    insp_type = (row.get("특이사항코드") or "").strip()    # 사고/침수/도난
    # 합성 inspection_id — KOTSA 가 raw id 없어 (검사소+일자+순번) 사용
    syn_id = f"{inspector_code}_{inspected_at}_{seq}" if all([
        inspector_code, inspected_at, seq]) else ""
    return {
        "inspection_id":   syn_id,
        "vin":             None,
        "inspection_type": insp_type or None,
        "result":          None,
        "inspected_at":    inspected_at,
        "reason":          None,
        "make_kr":         None,   # CSV 에 제조사 정보 없음
    }


def run() -> dict:
    files, kind = _find_inputs()
    if kind == "none":
        log.warning("[load:inspections] raw 없음 (JSONL or CSV) — graceful skip")
        return {"inserted": 0, "updated": 0, "skipped": 0}
    log.info("[load:inspections] %d %s files", len(files), kind)

    conn = get_connection()
    inserted = updated = skipped = 0

    def _iter_all():
        """파일 형식 별로 row dict 산출 — kind 와 무관하게 통일."""
        for f in files:
            if kind == "jsonl":
                year = f.stem
                try:
                    snapshot_year = int(year)
                except ValueError:
                    snapshot_year = None
                for line in f.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        yield snapshot_year, json.loads(line)
                    except json.JSONDecodeError:
                        yield snapshot_year, None
            else:   # csv
                for raw_row in _iter_csv_rows(f):
                    norm = _csv_to_normalized(raw_row)
                    # snapshot_year 는 접수일자에서 추출
                    insp_date = norm.get("inspected_at") or ""
                    sy = None
                    if len(insp_date) >= 4 and insp_date[:4].isdigit():
                        sy = int(insp_date[:4])
                    yield sy, norm

    with conn.cursor() as cur:
        for snapshot_year, row in _iter_all():
            if row is None:
                skipped += 1
                continue
            cur.execute("SAVEPOINT sp_dg_insp")
            try:
                mfr_id = _resolve_manufacturer_id(cur, row.get("make_kr"))
                cur.execute("""
                    INSERT INTO anxg_auto.events_inspections
                      (source, source_inspection_id, vin,
                       manufacturer_id, model_id, variant_id,
                       inspection_type, result, inspected_at, reason,
                       snapshot_year, raw)
                    VALUES (%s, %s, %s,
                            %s, NULL, NULL,
                            %s, %s,
                            NULLIF(%s, '')::date, %s,
                            COALESCE(%s, EXTRACT(YEAR FROM now())::SMALLINT),
                            %s::jsonb)
                    ON CONFLICT (source, source_inspection_id) DO UPDATE SET
                      raw = EXCLUDED.raw,
                      ingested_at = now()
                    RETURNING (xmax = 0) AS is_new
                """, (
                    _SOURCE_TAG,
                    str(row.get("inspection_id") or ""),
                    row.get("vin"),
                    mfr_id,
                    row.get("inspection_type"),
                    row.get("result"),
                    row.get("inspected_at") or "",
                    row.get("reason"),
                    snapshot_year,
                    json.dumps(row, ensure_ascii=False),
                ))
                is_new = cur.fetchone()[0]
                cur.execute("RELEASE SAVEPOINT sp_dg_insp")
                if is_new:
                    inserted += 1
                else:
                    updated += 1
            except Exception as exc:  # noqa: BLE001 — [load:inspections] 검사 row UPSERT 실패 흡수 → SAVEPOINT rollback + skip + 다음 row
                cur.execute("ROLLBACK TO SAVEPOINT sp_dg_insp")
                log.warning("[load:inspections] %s 실패: %s",
                            row.get("inspection_id"), exc)
                skipped += 1
    conn.commit()
    log.info("[load:inspections] inserted=%d updated=%d skipped=%d",
             inserted, updated, skipped)
    return {"inserted": inserted, "updated": updated, "skipped": skipped}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--log-level", default="INFO")
    args = ap.parse_args()
    logging.basicConfig(level=args.log_level,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    run()
    return 0


if __name__ == "__main__":
    sys.exit(main())


__all__ = ["run"]

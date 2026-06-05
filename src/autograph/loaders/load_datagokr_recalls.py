"""data.go.kr 15089863 — 한국 KOTSA 리콜 → anxg_auto.events_recalls UPSERT.

raw 파일 위치: ``data/raw/auto/datagokr_recalls/page_*.json``
적재 키:       ``(source='datagokr_kotsa', source_recall_no=<리콜번호>)``

raw 파일 없으면 graceful skip — exit 0.

CLI:
    python -m autograph.loaders.load_datagokr_recalls
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import sys
from pathlib import Path

from autonexusgraph.config import get_settings
from autonexusgraph.db.postgres import get_connection
from autonexusgraph.ingestion._common import normalize_corp_name

log = logging.getLogger(__name__)


_SOURCE_PATH = "auto/datagokr_recalls"
_SOURCE_TAG = "datagokr_kotsa"

# data.go.kr 응답의 한국어 제조사명 → NHTSA vPIC 의 영문 정규형 (auto.master_*
# 의 name 필드와 매칭) 폴백 사전. ``anxg_auto.master_manufacturers.aliases`` 가
# 비어있어도 한국 OEM 12 사는 본 매핑으로 매칭.
#
# 수집 키 부재로 실측 검증은 못 했지만, 한국 시장 점유율 상위 사를 우선 등록.
# 신규 한국 OEM 등장 시 본 dict 에 한 줄 추가 + alias 등록 스크립트로 backfill.
_KO_MFR_ALIAS: dict[str, str] = {
    "현대자동차":      "HYUNDAI",
    "현대차":          "HYUNDAI",
    "기아":            "KIA",
    "기아자동차":      "KIA",
    "제네시스":        "GENESIS",
    "테슬라":          "TESLA",
    "테슬라코리아":    "TESLA",
    "포드":            "FORD",
    "포드코리아":      "FORD",
    "포드세일즈서비스코리아": "FORD",
    "쌍용자동차":      "SSANGYONG",
    "쌍용차":          "SSANGYONG",
    "kg모빌리티":      "KGM",
    "케이지모빌리티":  "KGM",
    "르노삼성자동차":  "RENAULT",
    "르노삼성":        "RENAULT",
    "르노코리아":      "RENAULT",
    "한국지엠":        "CHEVROLET",
    "쉐보레":          "CHEVROLET",
    "지엠코리아":      "CHEVROLET",
    "토요타":          "TOYOTA",
    "도요타":          "TOYOTA",
    "혼다":            "HONDA",
    "닛산":            "NISSAN",
    "비엠더블유":      "BMW",
    "bmw코리아":       "BMW",
    "메르세데스-벤츠": "MERCEDES-BENZ",
    "벤츠":            "MERCEDES-BENZ",
    "메르세데스벤츠":  "MERCEDES-BENZ",
    "아우디":          "AUDI",
    "폭스바겐":        "VOLKSWAGEN",
    "푸조":            "PEUGEOT",
    "포르쉐":          "PORSCHE",
    "볼보":            "VOLVO",
    "재규어":          "JAGUAR",
    "랜드로버":        "LAND ROVER",
    "랜드로버코리아":  "LAND ROVER",
}


def _iter_items(root: Path):
    for f in sorted(root.glob("page_*.json")):
        try:
            payload = json.loads(f.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001 — [load_datagokr_recalls] 1 unit 실패 흡수 → log + continue (부분 성공 보존)
            log.warning("[load:datagokr_recalls] %s 파싱 실패: %s", f.name, exc)
            continue
        items = payload.get("data") or payload.get("items") or []
        for item in items:
            yield f.name, item


def _iter_csv_items(csv_path: Path):
    """data.go.kr 3048950 — KOTSA '자동차결함 리콜현황' CSV (cp949) → item dict.

    구 15089863 오픈API 폐기 대체본. 컬럼(6):
        제작자 / 차명 / 생산기간(부터) / 생산기간(까지) / 리콜개시일 / 리콜사유.
    리콜번호 컬럼이 **없어** (제작자+차명+생산기간+개시일+사유) sha1 으로 안정적·
    멱등 합성 키를 만든다 (``csv:<개시일>:<16hex>`` ≤ 31자, source_recall_no(80) 적합).
    """
    with csv_path.open(encoding="cp949", newline="") as f:
        reader = csv.DictReader(f)
        for raw_row in reader:
            row = {(k or "").strip(): (v or "").strip()
                   for k, v in raw_row.items() if k}
            maker = row.get("제작자")
            reason = row.get("리콜사유")
            if not (maker and reason):
                continue
            start = row.get("리콜개시일")
            basis = "|".join([
                maker, row.get("차명", ""),
                row.get("생산기간(부터)", ""), row.get("생산기간(까지)", ""),
                start or "", reason,
            ])
            digest = hashlib.sha1(basis.encode("utf-8")).hexdigest()[:16]
            yield csv_path.name, {
                "리콜번호":        f"csv:{start or 'na'}:{digest}",
                "제작자":          maker,
                "차명":            row.get("차명"),
                "결함내용":        reason,        # run() → defect_summary
                "리콜개시일":      start,         # run() → report_date
                "생산기간(부터)":  row.get("생산기간(부터)"),
                "생산기간(까지)":  row.get("생산기간(까지)"),
            }


def _ko_alias_lookup(raw_name: str, norm: str) -> str | None:
    """한국어 이름 → NHTSA 영문 정규형 1차 매핑."""
    if not raw_name:
        return None
    # normalize_corp_name 이 한글 법인격(주식회사 등) 을 공백으로 치환 후 lower
    # 처리. dict 키는 모두 lower 처리된 정규형.
    key = (norm or "").strip().lower()
    if key in _KO_MFR_ALIAS:
        return _KO_MFR_ALIAS[key]
    # 부분 매칭 — '현대자동차주식회사' → '현대자동차'.
    for ko_key, en_name in _KO_MFR_ALIAS.items():
        if ko_key in key:
            return en_name
    return None


def _resolve_manufacturer_id(cur, raw_name: str | None) -> int | None:
    """한국어/영문 회사명 → manufacturer_id.

    매칭 우선순위:
      1. name_norm 또는 name exact (기존)
      2. ``aliases`` 배열 contains raw 또는 norm
      3. 한국어 alias dict → 영문 정규형 → name exact (e.g. '현대자동차' → 'HYUNDAI')
    """
    if not raw_name:
        return None
    norm = normalize_corp_name(raw_name)

    # 1) 직접 매칭
    cur.execute("""
        SELECT manufacturer_id FROM anxg_auto.master_manufacturers
         WHERE name_norm = %s OR name = %s
         ORDER BY manufacturer_id LIMIT 1
    """, (norm, raw_name))
    r = cur.fetchone()
    if r:
        return r[0]

    # 2) aliases 배열 매칭 (Wikidata loader 가 채운 별칭 활용)
    cur.execute("""
        SELECT manufacturer_id FROM anxg_auto.master_manufacturers
         WHERE %s = ANY(aliases) OR %s = ANY(aliases)
         ORDER BY manufacturer_id LIMIT 1
    """, (raw_name, norm))
    r = cur.fetchone()
    if r:
        return r[0]

    # 3) 한국어 alias dict 폴백
    en_name = _ko_alias_lookup(raw_name, norm)
    if en_name:
        cur.execute("""
            SELECT manufacturer_id FROM anxg_auto.master_manufacturers
             WHERE name = %s OR name_norm = %s
             ORDER BY manufacturer_id LIMIT 1
        """, (en_name, en_name.lower()))
        r = cur.fetchone()
        if r:
            return r[0]

    return None


def run(csv_path: Path | None = None) -> dict:
    if csv_path is not None:
        if not csv_path.exists():
            log.warning("[load:datagokr_recalls] CSV %s 없음 — graceful skip", csv_path)
            return {"inserted": 0, "updated": 0, "skipped": 0}
        items_iter = _iter_csv_items(csv_path)
    else:
        raw_root = get_settings().ingest_raw_dir / _SOURCE_PATH
        if not raw_root.exists():
            log.warning("[load:datagokr_recalls] %s 없음 — graceful skip", raw_root)
            return {"inserted": 0, "updated": 0, "skipped": 0}
        items_iter = _iter_items(raw_root)

    conn = get_connection()
    inserted = updated = skipped = 0

    with conn.cursor() as cur:
        for filename, item in items_iter:
            # 정확한 컬럼명은 data.go.kr 명세에 따라 다름 — 대표 키만.
            recall_no = (item.get("리콜번호") or item.get("recallNo")
                         or item.get("recall_no") or item.get("RECALL_NO"))
            manufacturer_name = (item.get("제작자") or item.get("제작사")
                                 or item.get("manufacturer"))
            item.get("차명") or item.get("model")
            defect = item.get("결함내용") or item.get("defect")
            remedy = item.get("시정조치") or item.get("remedy")
            report_date = item.get("리콜개시일") or item.get("startDate")

            if not recall_no:
                skipped += 1
                continue

            cur.execute("SAVEPOINT sp_dg_recall")
            try:
                mfr_id = _resolve_manufacturer_id(cur, manufacturer_name)
                cur.execute("""
                    INSERT INTO anxg_auto.events_recalls
                      (source, source_recall_no, manufacturer_id, model_id, variant_id,
                       component_text, defect_summary, consequence, remedy_summary,
                       report_date, country, affected_units, raw, snapshot_year)
                    VALUES (%s, %s, %s, NULL, NULL,
                            NULL, %s, NULL, %s,
                            NULLIF(%s, '')::date, %s,
                            NULL,
                            %s::jsonb,
                            COALESCE(
                              EXTRACT(YEAR FROM NULLIF(%s,'')::date)::SMALLINT,
                              EXTRACT(YEAR FROM now())::SMALLINT))
                    ON CONFLICT (source, source_recall_no) DO UPDATE SET
                      manufacturer_id = COALESCE(EXCLUDED.manufacturer_id,
                                                  anxg_auto.events_recalls.manufacturer_id),
                      raw             = EXCLUDED.raw,
                      ingested_at     = now()
                    RETURNING (xmax = 0) AS is_new
                """, (
                    _SOURCE_TAG, str(recall_no), mfr_id,
                    defect, remedy,
                    report_date, "KR",
                    json.dumps(item, ensure_ascii=False),
                    report_date,
                ))
                is_new = cur.fetchone()[0]
                cur.execute("RELEASE SAVEPOINT sp_dg_recall")
                if is_new:
                    inserted += 1
                else:
                    updated += 1
            except Exception as exc:  # noqa: BLE001 — [load:datagokr_recalls] 리콜 row UPSERT 실패 흡수 → SAVEPOINT rollback + skip + 다음 row
                cur.execute("ROLLBACK TO SAVEPOINT sp_dg_recall")
                log.warning("[load:datagokr_recalls] %s/%s 실패: %s",
                            filename, recall_no, exc)
                skipped += 1

    conn.commit()
    log.info("[load:datagokr_recalls] inserted=%d updated=%d skipped=%d",
             inserted, updated, skipped)
    return {"inserted": inserted, "updated": updated, "skipped": skipped}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=None,
                    help="KOTSA '자동차결함 리콜현황' CSV 경로 (data.go.kr 3048950). "
                         "지정 시 JSON page 대신 CSV 적재.")
    ap.add_argument("--log-level", default="INFO")
    args = ap.parse_args()
    logging.basicConfig(level=args.log_level,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    run(csv_path=Path(args.csv) if args.csv else None)
    return 0


if __name__ == "__main__":
    sys.exit(main())


__all__ = ["run"]

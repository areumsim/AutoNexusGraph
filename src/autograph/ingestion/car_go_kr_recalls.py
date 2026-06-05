"""한국 자동차리콜센터 (car.go.kr) — 리콜 정보 수집.

**운영 모드**: **수동 CSV (by design)**.
- car.go.kr 공식 Open API 는 2026-05 기준 미공개. 키 발급 채널 없음.
- 사용자가 car.go.kr 웹사이트에서 CSV/Excel 을 받아 `data/raw/auto/car_go_kr/`
  하위에 두면 본 모듈의 ``ingest_from_csv_dir()`` 가 jsonl 로 정규화.
- 환경변수 ``CAR_GO_KR_API_KEY`` 는 향후 API 공개 시를 위해 자리만 잡아둠 —
  현재 어떤 path 도 키를 읽지 않음.

대체안: NHTSA 리콜은 ``nhtsa_recalls`` 모듈이 자동 수집 (FDA-style API).
US 시장 출시 한국 OEM 의 리콜은 사실상 NHTSA 와 중복되므로 KR-only 리콜만
manual CSV 로 보강하면 충분.

운영 절차는 ``docs/operations/data_pipeline.md`` 의 "car.go.kr 수동 CSV" 절 참조.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging

from autonexusgraph.ingestion._common import raw_dir

from ..config import get_auto_settings

log = logging.getLogger(__name__)

_SOURCE = "auto/car_go_kr"


def _csv_row_to_recall(row: dict) -> dict:
    """car.go.kr CSV 컬럼 휴리스틱 매핑 — 공식 스키마 확인 후 정교화 필요."""
    # 컬럼명은 한국어/영문 혼재 가능. 최선 추정 매핑.
    def pick(*keys: str) -> str | None:
        for k in keys:
            if k in row and row[k] not in ("", None):
                return str(row[k])
        return None

    return {
        "source": "car_go_kr",
        "source_recall_no":  pick("리콜번호", "리콜ID", "ID", "id"),
        "manufacturer_name": pick("제작사", "제조사", "Manufacturer"),
        "model_name":        pick("차명", "모델명", "Model"),
        "model_year":        pick("모델연도", "연식", "ModelYear"),
        "component_text":    pick("결함부위", "부품", "Component"),
        "defect_summary":    pick("결함내용", "결함", "Defect"),
        "remedy_summary":    pick("시정조치", "Remedy"),
        "report_date":       pick("리콜개시일", "리콜일자", "ReportDate"),
        "country":           "KR",
        "raw": row,
    }


def ingest_from_csv_dir() -> dict:
    src = raw_dir(_SOURCE)
    files = sorted(src.glob("*.csv"))
    if not files:
        log.warning(
            "[car_go_kr] CSV 없음 — by design 수동 모드. "
            "car.go.kr 에서 받은 CSV 를 %s 에 두세요. "
            "(공식 API 미공개)", src,
        )
        return {"files": 0}

    out_path = src / "_normalized.jsonl"
    n = 0
    with out_path.open("w", encoding="utf-8") as f_out:
        for csvp in files:
            with csvp.open(encoding="utf-8-sig", newline="") as f_in:
                reader = csv.DictReader(f_in)
                for row in reader:
                    norm = _csv_row_to_recall(row)
                    f_out.write(json.dumps(norm, ensure_ascii=False) + "\n")
                    n += 1
    log.info("[car_go_kr] normalized %d rows -> %s", n, out_path)
    return {"files": len(files), "rows": n}


def main() -> None:
    ap = argparse.ArgumentParser(prog="autograph.ingestion.car_go_kr_recalls")
    ap.add_argument("--log-level", default="INFO")
    args = ap.parse_args()
    logging.basicConfig(level=args.log_level,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")

    settings = get_auto_settings()
    if not settings.car_go_kr_api_key:
        log.warning("[car_go_kr] CAR_GO_KR_API_KEY 미설정 — manual CSV 모드로 진입")
    ingest_from_csv_dir()


if __name__ == "__main__":
    main()

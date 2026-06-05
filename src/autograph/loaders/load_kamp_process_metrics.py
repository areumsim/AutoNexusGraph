"""KAMP 제조AI 데이터셋(data.go.kr 15089213) → anxg_auto.process_metrics 적재 (4단계, 익명).

ProcessGraph 로드맵 4단계 — **패턴·품질 (익명·회사 비귀속)**.
공정 유형별 cycle_time / yield / defect_rate **분포 통계**만 적재 (개별 레코드 아님,
회사 귀속 절대 금지 — anxg_auto.process_metrics 에 corp_code 컬럼 자체가 없음). grade B(0.80).

현 상태(정직): KAMP 원천은 ``DATA_GO_KR_API_KEY`` + raw CSV 의존. 키/데이터 부재 시
**graceful skip (0 rows)** — PRD "키 부재 시 graceful skip". 테이블·로더는 ready
(scaffold), 데이터는 키 확보 후 수집.

CSV 스키마(예상): 공정유형, 지표종류(cycle_time/yield/defect), 평균/표준편차/표본수.
실제 KAMP CSV 헤더 확정 시 ``_parse_row`` 보강.

CLI:
    python -m autograph.loaders.load_kamp_process_metrics [--csv PATH]
"""

from __future__ import annotations

import argparse
import glob
import logging
import os

from autonexusgraph.db.postgres import get_connection

log = logging.getLogger(__name__)

_RAW_GLOB = "data/raw/datagokr/*15089213*"   # KAMP 제조AI
_SOURCE = "kamp_15089213"


def _find_csv(csv_arg: str | None) -> str | None:
    if csv_arg and os.path.isfile(csv_arg):
        return csv_arg
    hits = sorted(glob.glob(_RAW_GLOB) + glob.glob(_RAW_GLOB + ".csv"))
    return hits[0] if hits else None


def run(*, csv_path: str | None = None) -> dict:
    """KAMP CSV → anxg_auto.process_metrics UPSERT. 데이터 부재 시 graceful skip."""
    stats: dict = {"inserted": 0, "updated": 0, "skipped": 0, "csv": None}

    src = _find_csv(csv_path)
    if src is None:
        log.warning("[load:kamp] KAMP raw(%s) 없음 — graceful skip "
                    "(DATA_GO_KR_API_KEY 로 수집 후 재시도)", _RAW_GLOB)
        return stats
    stats["csv"] = src

    # NOTE: 실제 KAMP CSV 확보 시 파싱 구현. 현재는 테이블 존재만 보장(멱등) 후 skip.
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('anxg_auto.process_metrics')")
        if cur.fetchone()[0] is None:
            log.error("[load:kamp] anxg_auto.process_metrics 미생성 — "
                      "make migrate-schema-pg MIGRATE_FILE=25_auto_process_metrics.sql 먼저")
            return stats
    log.info("[load:kamp] csv=%s 발견 — 파서 미구현(헤더 확정 전), 0 rows", src)
    return stats


def main() -> None:
    ap = argparse.ArgumentParser(prog="autograph.loaders.load_kamp_process_metrics")
    ap.add_argument("--csv")
    ap.add_argument("--log-level", default="INFO")
    args = ap.parse_args()
    logging.basicConfig(level=args.log_level,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    print(run(csv_path=args.csv))


if __name__ == "__main__":
    main()

"""anxg_auto.master_vehicle_models 한국어 alias 보강 — KO OEM 차종 한국어 질의 매칭.

배경: 모델은 두 출처가 **별도 행**으로 적재됨 —
- NHTSA vPIC: 영문명("Kona"/"Sonata") + variants + recalls 보유, wikidata_qid 없음
- Wikidata: 한국어명("현대 쏘나타") + qid 보유, **variants/recalls 없음**
두 행을 잇는 공통 키가 없어, 한국어 질의("코나"/"쏘나타")가 recall 보유 영문 행에
매칭되지 않는다. 본 loader 가 영문(variant 보유) 행의 ``aliases`` 에 한국어 변형을
추가해 ``lookup_vehicle`` (m.aliases 매칭) 이 recall 보유 행으로 해소되게 한다.

매칭: (oem, english_name ILIKE) → aliases 배열 합집합(멱등). 영문 행만 대상.
2026-06-05 신규.
"""

from __future__ import annotations

import argparse
import logging
import sys

log = logging.getLogger(__name__)


# (OEM canonical name, DB 영문 model name, [한국어 alias·철자 변형]).
# 모호한 US↔KR 명칭(Optima/K5, Sedona/Carnival, Forte/K3, Cadenza/K7, Rio/Pride)은
# 오매칭 위험으로 제외 — 명확·고빈도만.
MODEL_ALIASES: list[tuple[str, str, list[str]]] = [
    ("HYUNDAI", "Kona",        ["코나"]),
    ("HYUNDAI", "Kona N",      ["코나 N", "코나N"]),
    ("HYUNDAI", "Sonata",      ["쏘나타", "소나타"]),
    ("HYUNDAI", "Elantra",     ["아반떼", "엘란트라"]),
    ("HYUNDAI", "Tucson",      ["투싼"]),
    ("HYUNDAI", "Santa Fe",    ["싼타페", "산타페"]),
    ("HYUNDAI", "Palisade",    ["팰리세이드", "펠리세이드"]),
    ("HYUNDAI", "Ioniq",       ["아이오닉"]),
    ("HYUNDAI", "Ioniq 5",     ["아이오닉5", "아이오닉 5"]),
    ("HYUNDAI", "Ioniq 6",     ["아이오닉6", "아이오닉 6"]),
    ("HYUNDAI", "Nexo",        ["넥쏘", "넥소"]),
    ("HYUNDAI", "Veloster",    ["벨로스터"]),
    ("HYUNDAI", "Venue",       ["베뉴"]),
    ("HYUNDAI", "Accent",      ["엑센트", "액센트"]),
    ("HYUNDAI", "Santa Cruz",  ["싼타크루즈"]),
    ("KIA",     "Seltos",      ["셀토스"]),
    ("KIA",     "Sportage",    ["스포티지"]),
    ("KIA",     "Sorento",     ["쏘렌토", "소렌토"]),
    ("KIA",     "Soul",        ["쏘울", "소울"]),
    ("KIA",     "Carnival",    ["카니발"]),
    ("KIA",     "Niro",        ["니로"]),
    ("KIA",     "Stinger",     ["스팅어"]),
    ("KIA",     "Telluride",   ["텔루라이드"]),
    ("GENESIS", "Genesis",     ["제네시스"]),
    ("GENESIS", "G70",         ["제네시스 G70"]),
    ("GENESIS", "G80",         ["제네시스 G80"]),
    ("GENESIS", "G90",         ["제네시스 G90"]),
]

_SQL = """
UPDATE anxg_auto.master_vehicle_models m
   SET aliases = (
         SELECT array_agg(DISTINCT x)
           FROM unnest(coalesce(m.aliases, '{}'::text[]) || %(ko)s::text[]) AS x
       ),
       updated_at = now()
  FROM anxg_auto.master_manufacturers mm
 WHERE m.manufacturer_id = mm.manufacturer_id
   AND mm.name = %(oem)s
   AND m.name ILIKE %(en)s
"""


def backfill(*, dry_run: bool = False) -> dict:
    """MODEL_ALIASES 를 영문 model 행의 aliases 에 합집합 추가 (멱등)."""
    from autonexusgraph.db.postgres import get_connection

    conn = get_connection()
    updated = matched = 0
    with conn.cursor() as cur:
        for oem, en, ko in MODEL_ALIASES:
            cur.execute(
                "SELECT count(*) FROM anxg_auto.master_vehicle_models m "
                "JOIN anxg_auto.master_manufacturers mm ON m.manufacturer_id=mm.manufacturer_id "
                "WHERE mm.name=%(oem)s AND m.name ILIKE %(en)s",
                {"oem": oem, "en": en},
            )
            n = cur.fetchone()[0]
            if n == 0:
                log.warning("[ko_model_alias] %s / %s — 영문 행 없음 (skip)", oem, en)
                continue
            matched += n
            if not dry_run:
                cur.execute(_SQL, {"oem": oem, "en": en, "ko": ko})
                updated += cur.rowcount
    if dry_run:
        conn.rollback()
    else:
        conn.commit()
    log.info("[ko_model_alias] matched rows=%d, updated=%d (dry_run=%s)",
             matched, updated, dry_run)
    return {"matched": matched, "updated": updated, "dry_run": dry_run}


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser(prog="autograph.loaders.master.load_korean_model_aliases")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    stats = backfill(dry_run=args.dry_run)
    print(f"[load_korean_model_aliases] {stats}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

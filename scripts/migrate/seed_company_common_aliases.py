"""회사 통칭 alias seed — anxg_master.company_aliases (additive·멱등).

`company_aliases` 는 DART 공식명/정규화명만 보유(예: '에스케이하이닉스')해, 통칭
'SK하이닉스'·'POSCO' 로는 `lookup_company` 가 회사를 못 찾는다(triage 해석 실패 →
최단경로·뉴스 공동언급 gold 질문 차단). 사람이 검증한 통칭 ↔ corp_code 매핑을 seed.

source='manual_common', confidence=0.95. PK=(alias_norm, corp_code, source) → ON CONFLICT
DO NOTHING 으로 멱등. 비파괴(INSERT only).

사용:
    python3 scripts/migrate/seed_company_common_aliases.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from autonexusgraph.db.postgres import get_connection  # noqa: E402

# (alias, alias_norm, corp_code) — 사람 검증 통칭. corp_code 는 anxg_master.companies 기준.
_ALIASES: list[tuple[str, str, str]] = [
    ("SK하이닉스",   "SK하이닉스",   "00164779"),   # 에스케이하이닉스(주)
    ("POSCO홀딩스",  "POSCO홀딩스",  "00155319"),   # 포스코홀딩스(주)
    ("POSCO",        "POSCO",        "00155319"),
    ("포스코",       "포스코",       "00155319"),
    ("SK이노베이션", "SK이노베이션", "00631518"),   # SK이노베이션(주)
    ("SK텔레콤",     "SK텔레콤",     "00159023"),   # SK텔레콤(주)
]


def main() -> None:
    conn = get_connection()
    inserted = 0
    with conn.cursor() as cur:
        for alias, alias_norm, corp_code in _ALIASES:
            # corp_code 실재 확인 — FK 위반·오타 방지.
            cur.execute(
                "SELECT 1 FROM anxg_master.companies WHERE corp_code = %s", (corp_code,)
            )
            if cur.fetchone() is None:
                print(f"  [skip] corp_code {corp_code} 부재 ({alias})")
                continue
            cur.execute(
                """
                INSERT INTO anxg_master.company_aliases
                    (alias, alias_norm, corp_code, source, confidence)
                VALUES (%s, %s, %s, 'manual_common', 0.95)
                ON CONFLICT (alias_norm, corp_code, source) DO NOTHING
                """,
                (alias, alias_norm, corp_code),
            )
            inserted += cur.rowcount
    conn.commit()
    print(f"[seed-aliases] 통칭 alias {inserted}건 신규 삽입 (시도 {len(_ALIASES)}건, 멱등).")


if __name__ == "__main__":
    main()

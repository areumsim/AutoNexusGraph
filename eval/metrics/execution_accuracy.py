"""Execution Accuracy — pred/gold Cypher 의 result set 동등 비교.

runner 가 None 또는 cypher 가 비어있으면 None (NA) 반환 — 미평가.
v2 agent 가 cypher 를 응답에 노출 + gold_cypher 가 큐레이션되면 자동 작동.
"""

from __future__ import annotations

from typing import Any, Callable


def _row_set(rows: list[dict[str, Any]]) -> frozenset[tuple]:
    """결과 dict 리스트 → 비교 가능한 frozenset. list/dict 값은 repr 폴백."""
    out: set[tuple] = set()
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        items: list[tuple[str, str]] = []
        for k in sorted(r.keys()):
            v = r[k]
            if isinstance(v, (list, dict)):
                items.append((str(k), repr(v)))
            else:
                items.append((str(k), str(v)))
        out.add(tuple(items))
    return frozenset(out)


def execution_accuracy(
    pred_cypher: str | None,
    gold_cypher: str | None,
    *,
    runner: Callable[[str], list[dict[str, Any]]] | None = None,
) -> float | None:
    """Returns:
      - None: 입력 부족 / runner 미주입 / 실행 에러 (NA)
      - 1.0:  pred 와 gold 의 result set 동일
      - 0.0:  pred 와 gold 의 result set 다름
    """
    if not (pred_cypher and gold_cypher and runner):
        return None
    try:
        a = _row_set(runner(pred_cypher))
        b = _row_set(runner(gold_cypher))
    except Exception:
        return None
    return 1.0 if a == b else 0.0

"""Hits@k / Recall@k — pred entity 리스트와 gold entity 리스트의 매칭.

매칭 규칙:
1. 정규화 후 정확 일치
2. 부분문자열 포함 — 짧은 쪽 정규화 길이 ≥ 3 일 때만 (1~2글자 오탐 차단)
3. difflib SequenceMatcher ratio ≥ 0.85
"""

from __future__ import annotations

from difflib import SequenceMatcher

from ._text_norm import normalize_text


_SIM_THRESHOLD = 0.85
_MIN_SUBSTR_LEN = 3


def _matches(a: str, b: str) -> bool:
    na, nb = normalize_text(a), normalize_text(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    # 부분문자열 매칭은 짧은 쪽 ≥3 일 때만 — '의' / 'A' 같은 1~2글자 오탐 차단
    if (na in nb or nb in na) and min(len(na), len(nb)) >= _MIN_SUBSTR_LEN:
        return True
    return SequenceMatcher(None, na, nb).ratio() >= _SIM_THRESHOLD


def hits_at_k(pred_entities: list[str], gold_entities: list[str], k: int = 5) -> float:
    """pred 상위 k 중 gold 와 매칭 1건 이상이면 1.0."""
    if not gold_entities:
        return 0.0
    for p in (pred_entities or [])[:k]:
        if any(_matches(p, g) for g in gold_entities):
            return 1.0
    return 0.0


def recall_at_k(pred_entities: list[str], gold_entities: list[str], k: int = 5) -> float:
    """gold 중 pred 상위 k 에 매칭되는 비율."""
    if not gold_entities:
        return 0.0
    head = (pred_entities or [])[:k]
    if not head:
        return 0.0
    matched = sum(1 for g in gold_entities if any(_matches(g, p) for p in head))
    return matched / len(gold_entities)

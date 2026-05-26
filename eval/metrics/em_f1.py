"""EM (Exact Match) + Token-F1.

gold_answer_text 는 list[str] (paraphrase 지원). gold 중 max score 반환.
"""

from __future__ import annotations

from collections import Counter

from ._text_norm import normalize_text, tokenize


def exact_match(pred: str, golds: list[str]) -> float:
    """정규화 후 어떤 gold 와 정확 일치하면 1.0, 아니면 0.0."""
    if not golds:
        return 0.0
    p = normalize_text(pred)
    return 1.0 if any(normalize_text(g) == p for g in golds) else 0.0


def token_f1(pred: str, golds: list[str]) -> float:
    """gold 별 token-F1 계산 후 max 반환.

    token = 공백 split + 한글 char-bigram (_text_norm.tokenize).
    """
    if not golds:
        return 0.0
    pred_tokens = tokenize(pred)
    if not pred_tokens:
        return 0.0
    best = 0.0
    pred_counter = Counter(pred_tokens)
    for g in golds:
        gold_tokens = tokenize(g)
        if not gold_tokens:
            continue
        gold_counter = Counter(gold_tokens)
        overlap = sum((pred_counter & gold_counter).values())
        if overlap == 0:
            continue
        precision = overlap / sum(pred_counter.values())
        recall = overlap / sum(gold_counter.values())
        f1 = 2 * precision * recall / (precision + recall)
        if f1 > best:
            best = f1
    return best

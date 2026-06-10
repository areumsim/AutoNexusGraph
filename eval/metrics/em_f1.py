"""EM (Exact Match) + Token-F1.

gold_answer_text 는 list[str] (paraphrase 지원). gold 중 max score 반환.
"""

from __future__ import annotations

from collections import Counter

from ._text_norm import normalize_text, tokenize


_MIN_SUBSTR_LEN = 3   # hits_at_k._MIN_SUBSTR_LEN 미러 — 1~2글자 gold 오탐 차단


def exact_match(pred: str, golds: list[str]) -> float:
    """정규화 후 어떤 gold 와 정확 일치하면 1.0, 아니면 0.0."""
    if not golds:
        return 0.0
    p = normalize_text(pred)
    return 1.0 if any(normalize_text(g) == p for g in golds) else 0.0


def exact_match_contains(pred: str, golds: list[str],
                         *, min_substr_len: int = _MIN_SUBSTR_LEN) -> float:
    """span-aware EM — 정규화 후 gold 가 pred 의 부분문자열이면 1.0.

    어댑터 답변은 산문(markdown 다줄)이고 gold 는 짧은 정답 span 이라 strict
    full-string equality (``exact_match``) 는 정답을 담고도 항상 0 을 반환한다
    (예: pred "…**300조 8,709억원**…" ⊃ gold "300조 8,709억원" 인데 ≠). 본 함수는
    gold ⊆ pred 포함을 정답으로 인정해 그 측정 artifact 를 보정한다.

    오탐 가드: 정규화 gold 길이 < ``min_substr_len`` 이면 strict equality 로만
    매칭 (hits_at_k 와 동일 규약). ``normalize_text`` 가 ``,`` 를 제거하므로
    숫자 자릿수 구분기호(8,709)는 자동 정규화된다.
    """
    if not golds:
        return 0.0
    p = normalize_text(pred)
    if not p:
        return 0.0
    for g in golds:
        ng = normalize_text(g)
        if not ng:
            continue
        if ng == p:
            return 1.0
        if len(ng) >= min_substr_len and ng in p:
            return 1.0
    return 0.0


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

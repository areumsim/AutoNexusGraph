"""Faithfulness — 답변 토큰이 evidence 토큰 풀에서 발견되는 비율.

0.0 ~ 1.0. evidence 가 비거나 answer 비면 0.0.
RAG hallucination 측정에 쓰는 가장 단순한 metric.
"""

from __future__ import annotations

from typing import Iterable

from ._text_norm import tokenize


def faithfulness(answer: str, evidence_texts: Iterable[str]) -> float:
    """answer 토큰 ∩ evidence 토큰 풀 / |answer 토큰|."""
    pred_tokens = set(tokenize(answer))
    if not pred_tokens:
        return 0.0
    evidence_tokens: set[str] = set()
    for txt in evidence_texts or []:
        if txt:
            evidence_tokens.update(tokenize(str(txt)))
    if not evidence_tokens:
        return 0.0
    overlap = len(pred_tokens & evidence_tokens)
    return overlap / len(pred_tokens)

"""Refusal confusion matrix.

각 row = {"is_answerable": bool, "refused": bool}

- refusal_precision: refused ∧ unanswerable / refused
- refusal_recall:    refused ∧ unanswerable / unanswerable
- false_refusal_rate: refused ∧ answerable / answerable (over-refusal)
"""

from __future__ import annotations

from typing import Iterable


def refusal_metrics(rows: Iterable[dict]) -> dict:
    rows = list(rows)
    n_total = len(rows)
    n_refused = sum(1 for r in rows if r.get("refused"))
    n_unanswerable = sum(1 for r in rows if not r.get("is_answerable"))
    n_answerable = n_total - n_unanswerable

    tp = sum(1 for r in rows if r.get("refused") and not r.get("is_answerable"))
    fp = sum(1 for r in rows if r.get("refused") and r.get("is_answerable"))

    precision = (tp / n_refused) if n_refused else 0.0
    recall = (tp / n_unanswerable) if n_unanswerable else 0.0
    frr = (fp / n_answerable) if n_answerable else 0.0

    return {
        "n_total": n_total,
        "n_refused": n_refused,
        "n_unanswerable": n_unanswerable,
        "n_answerable": n_answerable,
        "refusal_precision": precision,
        "refusal_recall": recall,
        "false_refusal_rate": frr,
    }

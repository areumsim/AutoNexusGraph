"""Main-Hop Efficiency 메트릭 (PRD §10.13).

목표: "평균 노드 탐색 수 30% 감소" — main_hop 우선 탐색이 평면 그래프 대비
얼마나 적은 evidence 로 동일 답에 도달하는지.

본 메트릭은 evidence list 길이와 evidence 별 score / chunk score 를
adapter 별로 집계한다. graph/hybrid 어댑터가 vector_only 보다 적은
evidence 로 EM 을 달성하면 main_hop 효율이 확인된다.

본 메트릭은 그래프 path 의 정확한 노드 수를 직접 측정하지 않는다 —
어댑터가 응답에 cypher 와 evidence 만 노출하기 때문이다.
대신 "정답을 맞춘 row 당 evidence 평균 카운트" 를 프록시로 사용한다.
적을수록 효율적.
"""

from __future__ import annotations

from statistics import fmean
from typing import Any, Iterable

from ._thresholds import MAIN_HOP_TARGET_RATIO


def _evidence_count(pred_row: dict) -> int:
    ev = pred_row.get("evidence")
    if not isinstance(ev, list):
        return 0
    return len(ev)


def _hop_count(pred_row: dict) -> int | None:
    """E-3: 어댑터가 노출한 실제 cypher hop 수 (per-turn trace 파생). 없으면 None.

    있으면 evidence-count 프록시보다 직접적 — `hybrid_vs_vector_hops` 로 비교.
    """
    h = pred_row.get("hop_count")
    if isinstance(h, bool) or not isinstance(h, (int, float)):
        return None
    return int(h)


def main_hop_efficiency(pred_rows: Iterable[dict],
                        per_q_metrics: Iterable[dict] | None = None) -> dict[str, Any]:
    """adapter 별 main-hop 효율 프록시.

    Args:
        pred_rows: ``{adapter, qid, evidence: [...]}`` 행들.
        per_q_metrics: 옵션 — qid 별 ``{em, adapter}`` 를 포함하면 "정답 row 한정"
            평균 evidence 카운트도 계산.

    Returns:
        ``{adapter: {ev_avg, ev_avg_correct, n, n_correct, ...}, target_ratio: 0.7}``
        target_ratio = 0.7 (=30% 감소) — vector adapter 대비 hybrid 가 0.7 배
        이하 evidence 면 PRD §10.13 통과.
    """
    pred_rows = list(pred_rows)
    by_adapter: dict[str, list[int]] = {}
    hop_by_adapter: dict[str, list[int]] = {}   # E-3 — 실제 hop 수 (있는 row 만)
    for r in pred_rows:
        a = r.get("adapter", "")
        if not a:
            continue
        by_adapter.setdefault(a, []).append(_evidence_count(r))
        hc = _hop_count(r)
        if hc is not None:
            hop_by_adapter.setdefault(a, []).append(hc)

    # 정답 row 한정 평균.
    correct_by_adapter: dict[str, list[int]] = {}
    if per_q_metrics is not None:
        em_map: dict[tuple[str, str], float] = {
            (m["adapter"], m["qid"]): float(m.get("em") or 0.0)
            for m in per_q_metrics
        }
        for r in pred_rows:
            a = r.get("adapter", "")
            qid = r.get("qid", "")
            em = em_map.get((a, qid), 0.0)
            if em >= 1.0:
                correct_by_adapter.setdefault(a, []).append(_evidence_count(r))

    out: dict[str, Any] = {
        "target_efficiency_ratio": MAIN_HOP_TARGET_RATIO,   # PRD §10.13 — vector 대비 30% 감소
    }
    for a, counts in by_adapter.items():
        avg = fmean(counts) if counts else 0.0
        rec: dict[str, Any] = {
            "n":      len(counts),
            "ev_avg": round(avg, 3),
        }
        cc = correct_by_adapter.get(a)
        if cc is not None:
            rec["n_correct"]      = len(cc)
            rec["ev_avg_correct"] = round(fmean(cc), 3) if cc else 0.0
        hops = hop_by_adapter.get(a)
        if hops:
            rec["hop_avg"]   = round(fmean(hops), 3)
            rec["n_hop"]     = len(hops)
        out[a] = rec

    # vector vs hybrid 비교 — PRD §10.13.
    v = out.get("vector") or {}
    h = out.get("hybrid") or {}
    if v.get("ev_avg") and h.get("ev_avg") is not None:
        ratio = float(h["ev_avg"]) / float(v["ev_avg"]) if v["ev_avg"] else 0.0
        out["hybrid_vs_vector"] = {
            "vector_ev_avg": v["ev_avg"],
            "hybrid_ev_avg": h["ev_avg"],
            "ratio":         round(ratio, 3),
            "target_met":    ratio > 0.0 and ratio <= MAIN_HOP_TARGET_RATIO,
        }
    # E-3: 실제 hop 수가 있으면 직접 비교 (evidence 프록시보다 우선 신호).
    if v.get("hop_avg") and h.get("hop_avg") is not None:
        hratio = float(h["hop_avg"]) / float(v["hop_avg"]) if v["hop_avg"] else 0.0
        out["hybrid_vs_vector_hops"] = {
            "vector_hop_avg": v["hop_avg"],
            "hybrid_hop_avg": h["hop_avg"],
            "ratio":          round(hratio, 3),
            "target_met":     hratio > 0.0 and hratio <= MAIN_HOP_TARGET_RATIO,
        }
    return out


def format_summary_md(quality: dict[str, Any]) -> str:
    lines: list[str] = ["## Main-Hop Efficiency (PRD §10.13 목표: 평면 대비 −30%)"]
    target = quality.get("target_efficiency_ratio", MAIN_HOP_TARGET_RATIO)
    hvv = quality.get("hybrid_vs_vector")
    if not hvv:
        lines.append("- (vector/hybrid 어댑터가 모두 있을 때만 비교 가능)")
        adapter_rows = [k for k, v in quality.items() if isinstance(v, dict) and "ev_avg" in v]
        for a in adapter_rows:
            v = quality[a]
            extra = ""
            if "ev_avg_correct" in v:
                extra = f", correct_ev_avg={v['ev_avg_correct']} (n={v['n_correct']})"
            lines.append(f"- {a}: ev_avg={v['ev_avg']} (n={v['n']}){extra}")
        return "\n".join(lines)

    met = "✅" if hvv["target_met"] else "❌"
    lines.append(
        f"- vector ev_avg = **{hvv['vector_ev_avg']}**, hybrid ev_avg = **{hvv['hybrid_ev_avg']}**"
    )
    lines.append(
        f"- ratio (hybrid/vector) = **{hvv['ratio']}** — 목표 ≤ {target} {met}"
    )
    return "\n".join(lines)


__all__ = ["main_hop_efficiency", "format_summary_md"]

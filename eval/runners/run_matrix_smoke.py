#!/usr/bin/env python3
"""PRD §10 DoD #17 (d) — 축소 평가 매트릭스 enumerator (4 어댑터 × FAST × rerank ablation).

본 runner 는 평가 매트릭스의 **셀 enumeration 인프라** 를 검증한다 (PRD §11.1):
  - 4 어댑터 (vector / graph / hybrid / sql_vec) × rerank {on/off} = 8 base cells
  - (축2) hybrid 룰 vs LLM 자율 planner ablation 2 cells (``_planner1``) = 총 10 cells
  - 각 cell 의 식별자 (``<name>_<tier>_rerank<0|1>[_planner1]``) + 어댑터 인스턴스화
  - thesis headline 자동 계산 — ``hybrid_fast_rerank1`` vs ``vector_fast_rerank0``
    multi-hop EM 차이 (PRD §10.7 +30%p 목표)
  - (축2) planner_ablation headline — ``hybrid_*_rerank1`` (룰) vs ``_planner1`` (LLM)
    multi-hop EM 차이 (LLM 자율 planner 가 룰 템플릿 대비 품질 우위인지 정량화)

기본 = simulation (LLM 비용 0, mock AgentResponse). ``--full`` 옵션 시 실제
``run_qa_eval`` 를 cell 마다 호출 → LLM 비용 발생.

산출:
  - ``data/reports/audit_eval_matrix_<ISO>.json`` — cell 별 결과 + thesis
  - (full 모드) ``eval/reports/matrix_<run_id>/<cell>/`` — 기존 runner 출력
"""

from __future__ import annotations

import argparse
import itertools
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from eval.metrics._thresholds import (   # noqa: E402  PRD §10 임계 SSOT
    THESIS_DIFF_PP_TARGET,
    MAIN_HOP_TARGET_RATIO,
)
from eval.metrics._thesis import compute_diff_pp   # noqa: E402  §10.7 격차 helper

log = logging.getLogger(__name__)


# ── 축소 매트릭스 셀 정의 — PRD §10 DoD #17 (d) ────────────────
DEFAULT_ADAPTERS = ("vector", "graph", "hybrid", "sql_vec")
DEFAULT_TIERS = ("fast",)                 # PRD: "FAST tier 1종"
DEFAULT_RERANK = (True, False)            # ablation 양 셀


def enumerate_cells(adapters: tuple[str, ...] = DEFAULT_ADAPTERS,
                     tiers:    tuple[str, ...] = DEFAULT_TIERS,
                     reranks:  tuple[bool, ...] = DEFAULT_RERANK,
                     planner_ablation: bool = True,
                     ) -> list[dict[str, Any]]:
    """축소 매트릭스 셀 목록 — (adapter, tier, rerank) 직곱 + (축2) hybrid planner ablation.

    planner_ablation=True 이고 adapters 에 hybrid 가 포함되면, hybrid 셀마다 LLM 자율
    planner 버전(``_planner1``)을 추가한다 — 룰 planner vs LLM planner 정량 비교용.
    타 어댑터(vector/graph/sql_vec)는 agent planner 미경유라 ablation 무의미 → 미추가.
    """
    from eval.adapters import get_adapter

    cells: list[dict[str, Any]] = []
    for adapter_name, tier, rerank in itertools.product(adapters, tiers, reranks):
        adapter = get_adapter(adapter_name, rerank=rerank, llm_tier=tier)
        cells.append({
            "label":       adapter.label(),
            "adapter":     adapter_name,
            "tier":        tier,
            "rerank":      rerank,
            "llm_planner": False,
        })
    # 축2 — hybrid 룰 vs LLM planner 셀 추가 (rerank 별).
    if planner_ablation and "hybrid" in adapters:
        for tier, rerank in itertools.product(tiers, reranks):
            adapter = get_adapter("hybrid", rerank=rerank, llm_tier=tier, llm_planner=True)
            cells.append({
                "label":       adapter.label(),
                "adapter":     "hybrid",
                "tier":        tier,
                "rerank":      rerank,
                "llm_planner": True,
            })
    return cells


def _simulate_cell(cell: dict[str, Any]) -> dict[str, Any]:
    """simulation 모드 — 실 LLM 호출 없이 mock 결과. wire-up 검증만."""
    return {
        **cell,
        "ran":          True,
        "mode":         "simulation",
        "n_questions":  0,
        "em":           None,
        "f1":           None,
        "multi_hop_em": None,
        "cost_usd":     0.0,
    }


def _run_cell_full(cell: dict[str, Any], gold: Path, run_root: Path,
                    extra_args: list[str]) -> dict[str, Any]:
    """full 모드 — 실 run_qa_eval 호출. LLM 비용 발생.

    manifest.json 의 ``summary[cell_label]`` 에서 multi_hop_em / em / f1 / cost
    를 추출해 cell dict 에 직접 박는다 — compute_thesis_headline 이 cell["multi_hop_em"]
    키 직접 조회하므로 본 병합이 없으면 thesis 항상 unavailable.
    """
    import subprocess
    cell_dir = run_root / cell["label"]
    cell_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable, "-m", "eval.runners.run_qa_eval",
        "--gold", str(gold),
        "--adapters", cell["adapter"],
        "--run-id", str(cell_dir.relative_to(ROOT / "eval" / "reports")),
        *extra_args,
    ]
    # rerank/llm_tier 를 ENV 로 전달 — runner 의 get_adapter 가 받음.
    import os
    env = {**os.environ,
           "EVAL_RERANK":   "1" if cell["rerank"] else "0",
           "EVAL_LLM_TIER": cell["tier"],
           "EVAL_LLM_PLANNER": "1" if cell.get("llm_planner") else "0"}
    log.info("[matrix] full cell %s — cmd: %s", cell["label"], " ".join(cmd))
    rc = subprocess.run(cmd, env=env, cwd=str(ROOT)).returncode

    # manifest.json 의 summary + DoD #13/#14 메트릭 추출.
    multi_hop_em: float | None = None
    multi_hop_hits: float | None = None    # hits@k fallback (gold_answer_text 부재 시)
    em: float | None = None
    f1: float | None = None
    cost_usd: float = 0.0
    n_questions: int = 0
    ev_avg_correct: float | None = None        # DoD #13 (main_hop_efficiency) per-cell
    latency_internal_pass: float | None = None  # DoD #14 per-cell
    latency_cross_pass: float | None = None     # DoD #14 per-cell
    manifest_path = cell_dir / "manifest.json"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            summary = manifest.get("summary") or {}
            # 매트릭스 모드 활성 시 summary key 는 cell label, 아니면 adapter name.
            cell_summary = summary.get(cell["label"]) or summary.get(cell["adapter"]) or {}
            if cell_summary:
                multi_hop_em = cell_summary.get("multi_hop_em")
                # hits@k fallback — run_qa_eval.py:359 가 manifest 에 생성. 이 추출이
                # 없으면 compute_thesis_headline 의 hits fallback 이 항상 None 으로 죽음.
                multi_hop_hits = cell_summary.get("multi_hop_hits")
                em = cell_summary.get("em")
                f1 = cell_summary.get("f1")
                cost_usd = float(cell_summary.get("cost_usd_total") or 0.0)
                n_questions = int(cell_summary.get("n") or 0)
            # DoD #13 — main_hop_efficiency.<adapter>.ev_avg_correct
            mhe = manifest.get("main_hop_efficiency") or {}
            mhe_cell = mhe.get(cell["label"]) or mhe.get(cell["adapter"]) or {}
            ev_avg_correct = mhe_cell.get("ev_avg_correct") if mhe_cell else None
            # DoD #14 — latency.<adapter>.target_{internal,cross}_pass_rate
            lat = manifest.get("latency") or {}
            lat_cell = lat.get(cell["label"]) or lat.get(cell["adapter"]) or {}
            latency_internal_pass = lat_cell.get("target_internal_pass_rate") if lat_cell else None
            latency_cross_pass    = lat_cell.get("target_cross_pass_rate")    if lat_cell else None
        except Exception as exc:   # noqa: BLE001
            log.warning("[matrix] manifest 파싱 실패 (%s): %s", cell["label"], exc)

    return {
        **cell, "ran": rc == 0, "mode": "full",
        "n_questions":          n_questions,
        "em":                   em,
        "f1":                   f1,
        "multi_hop_em":         multi_hop_em,
        "multi_hop_hits":       multi_hop_hits,
        "cost_usd":             cost_usd,
        "ev_avg_correct":       ev_avg_correct,         # DoD #13
        "latency_internal_pass": latency_internal_pass,  # DoD #14
        "latency_cross_pass":    latency_cross_pass,     # DoD #14
    }


def compute_thesis_headline(cells_with_metrics: list[dict[str, Any]]
                             ) -> dict[str, Any]:
    """PRD §10.7 thesis — hybrid_*_rerank1 vs vector_*_rerank0 multi-hop EM 차이.

    가장 유리한 hybrid 셀 vs 가장 불리한 vector 셀 비교 — Hybrid 가 RAG 의 모든
    혜택을 누리고도 Vector baseline (rerank 없음) 을 못 이기면 실패.
    """
    hybrid_best = next(
        (c for c in cells_with_metrics if c["adapter"] == "hybrid" and c["rerank"]),
        None,
    )
    vector_baseline = next(
        (c for c in cells_with_metrics if c["adapter"] == "vector" and not c["rerank"]),
        None,
    )
    if not hybrid_best or not vector_baseline:
        return {"available": False, "reason": "필요 셀 미포함 (hybrid_rerank1 + vector_rerank0)"}
    if hybrid_best.get("multi_hop_em") is None or vector_baseline.get("multi_hop_em") is None:
        return {
            "available":  False,
            "reason":     "simulation 모드 — multi-hop EM 미산정 (full 모드 필요)",
            "hybrid":     hybrid_best["label"],
            "vector":     vector_baseline["label"],
        }
    em_diff_pp, em_met = compute_diff_pp(
        hybrid_best["multi_hop_em"], vector_baseline["multi_hop_em"],
    )
    # hits@k 도 비교 — gold_answer_text 부재 시 entity-level fallback.
    h_hits = hybrid_best.get("multi_hop_hits")
    v_hits = vector_baseline.get("multi_hop_hits")
    if h_hits is not None and v_hits is not None:
        hits_diff_pp, hits_met = compute_diff_pp(h_hits, v_hits)
    else:
        hits_diff_pp, hits_met = None, False
    target_met = em_met or hits_met
    # diff_pp 는 primary (em) 표시, 단 hits 가 met 이면 hits 기준으로 표기.
    primary_metric = "hits" if (hits_met and not em_met) else "em"
    primary_diff = hits_diff_pp if primary_metric == "hits" else em_diff_pp
    return {
        "available":     True,
        "hybrid_em":     hybrid_best["multi_hop_em"],
        "vector_em":     vector_baseline["multi_hop_em"],
        "em_diff_pp":    em_diff_pp,
        "hybrid_hits":   h_hits,
        "vector_hits":   v_hits,
        "hits_diff_pp":  hits_diff_pp,
        "diff_pp":       primary_diff,
        "primary":       primary_metric,
        "target_pp":     THESIS_DIFF_PP_TARGET,
        "target_met":    target_met,
    }


def compute_dod_13_14(cells_with_metrics: list[dict[str, Any]]) -> dict[str, Any]:
    """PRD §10 DoD #13 (main_hop 30% 감소) + #14 (latency <8s/<12s).

    DoD #13: vector_rerank0 (baseline) 대비 hybrid_rerank1 의 ev_avg_correct 비율 ≤ 0.7.
    DoD #14: hybrid_rerank1 (대표 셀) 의 latency target pass rate (internal/cross).
    """
    hybrid_best = next(
        (c for c in cells_with_metrics if c["adapter"] == "hybrid" and c["rerank"]),
        None,
    )
    vector_baseline = next(
        (c for c in cells_with_metrics if c["adapter"] == "vector" and not c["rerank"]),
        None,
    )

    # DoD #13.
    dod_13: dict[str, Any]
    if (hybrid_best is None or vector_baseline is None
        or hybrid_best.get("ev_avg_correct") is None
        or vector_baseline.get("ev_avg_correct") is None
        or vector_baseline.get("ev_avg_correct") in (0, 0.0)):
        dod_13 = {"available": False,
                  "reason": "필요 셀 또는 main_hop_efficiency 데이터 누락 (full 모드 + correct 답 필요)"}
    else:
        ratio = hybrid_best["ev_avg_correct"] / vector_baseline["ev_avg_correct"]
        dod_13 = {
            "available":  True,
            "hybrid_ev":  hybrid_best["ev_avg_correct"],
            "vector_ev":  vector_baseline["ev_avg_correct"],
            "ratio":      round(ratio, 3),
            "target":     MAIN_HOP_TARGET_RATIO,
            "target_met": ratio <= MAIN_HOP_TARGET_RATIO,   # PRD §10.13 — 30%+ 감소
        }

    # DoD #14 — hybrid_rerank1 셀의 internal/cross latency pass rate.
    dod_14: dict[str, Any]
    if (hybrid_best is None
        or hybrid_best.get("latency_internal_pass") is None):
        dod_14 = {"available": False,
                  "reason": "필요 셀 또는 latency 데이터 누락 (full 모드 + latency 메트릭 필요)"}
    else:
        internal = hybrid_best["latency_internal_pass"]
        cross = hybrid_best.get("latency_cross_pass")
        dod_14 = {
            "available":   True,
            "cell":        hybrid_best["label"],
            "internal_pass_rate": internal,
            "cross_pass_rate":    cross,
            "target_internal":    0.9,
            "target_cross":       0.9,
            "target_met":  (internal is not None and internal >= 0.9
                            and (cross is None or cross >= 0.9)),
        }

    return {"dod_13_main_hop_efficiency": dod_13, "dod_14_latency": dod_14}


def compute_planner_ablation(cells_with_metrics: list[dict[str, Any]]
                              ) -> dict[str, Any]:
    """축2 — hybrid 룰 planner vs LLM 자율 planner 비교 (동일 rerank=on 셀 기준).

    ``hybrid_*_rerank1`` (룰) vs ``hybrid_*_rerank1_planner1`` (LLM) 의 multi_hop_em
    (없으면 em) 차이. LLM planner 가 룰 템플릿 대비 멀티홉 품질을 올리는지 정량화.
    """
    def _pick(llm: bool):
        return next(
            (c for c in cells_with_metrics
             if c["adapter"] == "hybrid" and c["rerank"]
             and bool(c.get("llm_planner")) == llm),
            None,
        )
    rule, llm = _pick(False), _pick(True)
    if not rule or not llm:
        return {"available": False, "reason": "hybrid rule/LLM planner 셀 미포함"}

    def _metric(c):
        return c.get("multi_hop_em") if c.get("multi_hop_em") is not None else c.get("em")
    rule_m, llm_m = _metric(rule), _metric(llm)
    if rule_m is None or llm_m is None:
        return {
            "available": False,
            "reason": "simulation 모드 — EM 미산정 (full 모드 필요)",
            "rule_cell": rule["label"], "llm_cell": llm["label"],
        }
    diff_pp, _ = compute_diff_pp(llm_m, rule_m)   # LLM − 룰
    return {
        "available":  True,
        "rule_cell":  rule["label"],
        "llm_cell":   llm["label"],
        "rule_em":    rule_m,
        "llm_em":     llm_m,
        "diff_pp":    diff_pp,
        "llm_better": llm_m >= rule_m,
        "rule_cost":  rule.get("cost_usd"),
        "llm_cost":   llm.get("cost_usd"),
    }


def main() -> int:
    p = argparse.ArgumentParser(prog="run_matrix_smoke",
                                 description=__doc__.split("\n")[0])
    p.add_argument("--gold", type=Path,
                   default=ROOT / "eval" / "qa_gold" / "gold_qa_v0.jsonl",
                   help="gold jsonl (다중 gold 는 ;로 구분)")
    p.add_argument("--adapters",
                   default=",".join(DEFAULT_ADAPTERS),
                   help="csv — vector,graph,hybrid,sql_vec 중")
    p.add_argument("--tiers", default="fast",
                   help="csv — fast,smart (기본 fast)")
    p.add_argument("--reranks", default="on,off",
                   help="csv — on,off (기본 둘 다 — ablation)")
    p.add_argument("--no-planner-ablation", action="store_true",
                   help="축2 hybrid 룰 vs LLM planner 셀 추가를 끔 (기본 추가)")
    p.add_argument("--full", action="store_true",
                   help="실제 run_qa_eval 호출 (LLM 비용 발생). 미지정 시 simulation "
                        "(LLM 비용 0, 셀 enumeration 만).")
    p.add_argument("--out-dir", type=Path,
                   default=ROOT / "data" / "reports",
                   help="JSON 리포트 저장 디렉토리")
    p.add_argument("--limit", type=int, default=None,
                   help="(full 모드) gold 첫 N row 만. --full + 미지정 시 "
                        "기본 30 (multi-hop subset 포함 → §10.7 thesis 측정 가능).")
    p.add_argument("--log-level", default="INFO")
    args = p.parse_args()
    logging.basicConfig(level=args.log_level, format="%(levelname)s %(message)s")

    # --full 모드 + --limit 미지정 시 default = 30 (gold_qa_v0.jsonl 의 multi-hop
    # 16 row 가 11~30 번에 있어 §10.7 thesis multi_hop_em 산정 가능). limit 10 시
    # FIN-L1 (단일홉) 만 → multi_hop_em 미산정 → thesis "simulation" 표기.
    if args.full and args.limit is None:
        args.limit = 30

    adapters = tuple(a.strip() for a in args.adapters.split(",") if a.strip())
    tiers = tuple(t.strip() for t in args.tiers.split(",") if t.strip())
    reranks = tuple(
        r.strip().lower() in ("on", "1", "true", "yes")
        for r in args.reranks.split(",") if r.strip()
    )
    if not reranks:
        reranks = DEFAULT_RERANK

    simulation = not args.full       # default 가 simulation
    cells = enumerate_cells(adapters, tiers, reranks,
                            planner_ablation=not args.no_planner_ablation)
    log.info("[matrix] %d cells: %s", len(cells), [c["label"] for c in cells])

    extra_args = []
    if args.limit:
        extra_args.extend(["--limit", str(args.limit)])

    if simulation:
        results = [_simulate_cell(c) for c in cells]
    else:
        run_root = ROOT / "eval" / "reports" / f"matrix_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        results = [_run_cell_full(c, args.gold, run_root, extra_args) for c in cells]

    thesis = compute_thesis_headline(results)
    dod_13_14 = compute_dod_13_14(results)
    planner_ablation = compute_planner_ablation(results)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = args.out_dir / f"audit_eval_matrix_{ts}.json"
    payload = {
        "passed":   all(r.get("ran") for r in results),
        "mode":     "simulation" if simulation else "full",
        "n_cells":  len(results),
        "cells":    results,
        "thesis":   thesis,
        "dod_13":   dod_13_14["dod_13_main_hop_efficiency"],
        "dod_14":   dod_13_14["dod_14_latency"],
        "planner_ablation": planner_ablation,   # 축2 — 룰 vs LLM planner
        "gold":     str(args.gold),
    }
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False),
                        encoding="utf-8")

    labels = ", ".join(c["label"] for c in cells)
    mode = "simulation" if simulation else "full"
    if payload["passed"]:
        thesis_str = ""
        if thesis.get("available"):
            mark = "✅" if thesis.get("target_met") else "❌"
            thesis_str = f" thesis: hybrid−vector = {thesis['diff_pp']:+.1f}%p (target +30%p) {mark}"
        else:
            thesis_str = f" thesis: {thesis.get('reason', 'n/a')}"
        # DoD #13/#14 한 줄 표시.
        d13 = payload["dod_13"]
        d14 = payload["dod_14"]
        dod_str = ""
        if d13.get("available"):
            m13 = "✅" if d13.get("target_met") else "❌"
            dod_str += f" #13: ratio={d13['ratio']} (target ≤0.7) {m13}"
        if d14.get("available"):
            m14 = "✅" if d14.get("target_met") else "❌"
            cross_repr = (f"{d14.get('cross_pass_rate'):.2f}"
                          if d14.get('cross_pass_rate') is not None else "n/a")
            dod_str += f" #14: int={d14.get('internal_pass_rate'):.2f}/cross={cross_repr} {m14}"
        # 축2 — 룰 vs LLM planner 한 줄.
        pa = payload["planner_ablation"]
        planner_str = ""
        if pa.get("available"):
            mark = "✅" if pa.get("llm_better") else "⚠️"
            planner_str = (f" planner(LLM−룰): {pa['diff_pp']:+.1f}%p "
                           f"(룰={pa['rule_em']:.3f}/LLM={pa['llm_em']:.3f}) {mark}")
        elif "planner1" in labels:
            planner_str = f" planner: {pa.get('reason', 'n/a')}"
        print(f"[audit-eval-matrix] PASS ({mode}, {len(cells)} cells: {labels}){thesis_str}{dod_str}{planner_str}  ({out_path})")
        return 0
    failed = [r["label"] for r in results if not r.get("ran")]
    print(f"[audit-eval-matrix] FAIL ({mode}) — cells failed: {failed}  ({out_path})")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""PRD §3.5 Confidence calibration audit — Platt scaling + reliability diagram.

P1-(4) 정량 검증 routine (사용자 cold review 2026-06-02):
    "A/B/C 등급 → confidence_score 0.95/0.80/0.50 매핑이 실제 정답률과 단조 관계인지
     미검증" → 본 스크립트가 평가 run 의 predictions + per_question.csv 를 결합해
     (confidence, em-correct) 분포에서 Platt scaling 적합 + 10-bin reliability
     diagram 산출.

사용:
    python scripts/audit/calibrate_confidence.py                       # 최신 run 자동 선택
    python scripts/audit/calibrate_confidence.py --run-dir eval/reports/run_20260601_063455
    python scripts/audit/calibrate_confidence.py --em-threshold 0.5    # correct 정의 완화 (기본 0.8)
    python scripts/audit/calibrate_confidence.py --adapter hybrid      # adapter 한정

출력:
    data/reports/calibration_<run_id>_<adapter>.json — Platt 계수 + bin 통계
    data/reports/calibration_<run_id>_<adapter>.png  — reliability diagram

종료 코드:
    0: PASS (적합 성공 또는 의도된 SKIPPED — 데이터 부족 / 키 부재)
    1: FAIL (run-dir 부재 / 파일 손상)

reverse-feed (PRD §3.5):
    적합 결과 `a < 1` → overconfident (실제 정답률이 confidence 보다 낮음)
        → PRD §3.5 표의 A=0.95 / B=0.80 / C=0.50 할당값 하향 조정 검토
    `a > 1` → underconfident → 할당값 상향 검토
    `b ≠ 0` → systematic bias → 임계값 (LOW_CONFIDENCE_THRESHOLD=0.5) 재검토
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]

log = logging.getLogger(__name__)


def _row_confidence(pred: dict) -> float | None:
    """예측 row 의 confidence 대표값 추출.

    우선순위:
        1. ``answer_confidence`` (synth 가 명시 설정 시)
        2. ``evidence[].score`` 평균 (retriever similarity — proxy)
        3. ``diagnostics.edges_confidence_avg`` (있을 때)
        → 모두 부재 시 None (해당 row 제외)
    """
    ac = pred.get("answer_confidence")
    if ac is not None:
        try:
            return float(ac)
        except (TypeError, ValueError):
            pass
    ev = pred.get("evidence") or []
    scores: list[float] = []
    for e in ev:
        s = e.get("score") if isinstance(e, dict) else None
        if s is None:
            continue
        try:
            scores.append(float(s))
        except (TypeError, ValueError):
            continue
    if scores:
        return sum(scores) / len(scores)
    return None


def _load_predictions(run_dir: Path, adapter: str | None
                      ) -> dict[tuple[str, str], dict]:
    """run_dir 의 ``<adapter>_predictions.jsonl`` 일괄 로딩 → {(adapter, qid): row}."""
    out: dict[tuple[str, str], dict] = {}
    for fp in sorted(run_dir.glob("*_predictions.jsonl")):
        ada = fp.name[: -len("_predictions.jsonl")]
        if adapter and ada != adapter:
            continue
        for line in fp.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            qid = row.get("qid")
            if qid:
                out[(row.get("adapter") or ada, qid)] = row
    return out


def _load_per_question(run_dir: Path) -> dict[tuple[str, str], dict]:
    """``per_question.csv`` → {(adapter, qid): {em, f1, ...}}."""
    fp = run_dir / "per_question.csv"
    if not fp.exists():
        return {}
    out: dict[tuple[str, str], dict] = {}
    with fp.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            ada = r.get("adapter") or ""
            qid = r.get("qid") or ""
            if ada and qid:
                out[(ada, qid)] = r
    return out


def _platt_fit(X: list[float], y: list[int]) -> dict[str, Any]:
    """sklearn LogisticRegression 으로 sigmoid(a*x + b) 적합. (a, b) 반환."""
    if len(X) < 10:
        return {"fitted": False,
                "reason": f"표본 {len(X)} 개 — Platt 적합 최소 10 필요"}
    if len(set(y)) < 2:
        return {"fitted": False,
                "reason": f"정답 클래스 단일 ({set(y)}) — calibration 무의미"}
    try:
        from sklearn.linear_model import LogisticRegression   # type: ignore[import-not-found]
        import numpy as np
    except ImportError as e:
        return {"fitted": False,
                "reason": f"sklearn / numpy 미설치: {e} — `pip install scikit-learn`"}
    Xa = np.array(X).reshape(-1, 1)
    ya = np.array(y)
    clf = LogisticRegression()
    clf.fit(Xa, ya)
    a = float(clf.coef_[0][0])
    b = float(clf.intercept_[0])
    return {
        "fitted":      True,
        "a":           a,
        "b":           b,
        "expression":  f"sigmoid({a:.3f} * conf + {b:.3f})",
        "n_samples":   len(X),
        "n_positive":  int(sum(y)),
        "n_negative":  len(y) - int(sum(y)),
    }


def _reliability_bins(X: list[float], y: list[int], n_bins: int = 10
                       ) -> list[dict[str, Any]]:
    """10-bin reliability diagram 데이터 — confidence ∈ [0.0, 1.0] 등분."""
    if not X:
        return []
    import numpy as np
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    bins: list[dict[str, Any]] = []
    Xa = np.array(X)
    ya = np.array(y)
    for k in range(n_bins):
        mask = (Xa >= edges[k]) & (Xa < edges[k + 1])
        if k == n_bins - 1:   # 마지막 bin 은 closed
            mask = (Xa >= edges[k]) & (Xa <= edges[k + 1])
        n = int(mask.sum())
        bins.append({
            "bin_lo":      float(edges[k]),
            "bin_hi":      float(edges[k + 1]),
            "n_samples":   n,
            "mean_conf":   float(Xa[mask].mean()) if n else None,
            "frac_correct": float(ya[mask].mean()) if n else None,
        })
    return bins


def _save_diagram(bins: list[dict], platt: dict, out_png: Path,
                   title: str) -> bool:
    """matplotlib reliability diagram + perfect-calibration diagonal."""
    try:
        import matplotlib
        matplotlib.use("Agg")        # headless
        import matplotlib.pyplot as plt
    except ImportError:
        log.warning("[calibrate] matplotlib 미설치 — PNG 생략 (JSON 만 산출)")
        return False
    xs, ys, ns = [], [], []
    for b in bins:
        if b.get("frac_correct") is None:
            continue
        xs.append(b["mean_conf"])
        ys.append(b["frac_correct"])
        ns.append(b["n_samples"])
    if not xs:
        log.warning("[calibrate] reliability 표본 없음 — PNG 생략")
        return False
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(7, 6))
    ax.plot([0, 1], [0, 1], "--", color="gray",
            label="perfect calibration (y=x)")
    sizes = [max(50, n * 10) for n in ns]
    ax.scatter(xs, ys, s=sizes, c="steelblue", alpha=0.7,
                edgecolors="navy", label=f"bins (size ∝ n)")
    ax.plot(xs, ys, "-", color="steelblue", alpha=0.5)
    if platt.get("fitted"):
        import numpy as np
        a, b = platt["a"], platt["b"]
        grid = np.linspace(0.0, 1.0, 100)
        sig = 1.0 / (1.0 + np.exp(-(a * grid + b)))
        ax.plot(grid, sig, "-", color="crimson", linewidth=2,
                label=f"Platt: σ({a:.2f}x + {b:.2f})")
    ax.set_xlabel("Predicted confidence")
    ax.set_ylabel("Empirical accuracy (frac. correct)")
    ax.set_title(title)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.grid(True, alpha=0.3)
    ax.legend(loc="lower right")
    plt.tight_layout()
    plt.savefig(out_png, dpi=120)
    plt.close(fig)
    return True


def _find_latest_run(reports_dir: Path) -> Path | None:
    """가장 최근 modified run dir — predictions.jsonl 적어도 1 개 + per_question.csv."""
    candidates: list[Path] = []
    if not reports_dir.exists():
        return None
    for d in reports_dir.iterdir():
        if not d.is_dir():
            continue
        if (d / "per_question.csv").exists() and any(d.glob("*_predictions.jsonl")):
            candidates.append(d)
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def calibrate(run_dir: Path, *, adapter: str | None = None,
               em_threshold: float = 0.8, out_dir: Path | None = None,
               metric: str = "em") -> dict[str, Any]:
    """단일 run 의 calibration 분석.

    Args:
        run_dir: ``eval/reports/<run>/`` — predictions.jsonl + per_question.csv 있어야.
        adapter: 한정. None 이면 모든 adapter 합산.
        em_threshold: 정답성 metric ≥ 이 값 = correct.
        metric: "em" (기본 — 엄격) 또는 "f1" (완화 — synth 미동작 데이터셋 대응).

    Returns:
        ``{platt, bins, n, run_id, adapter, em_threshold, metric}``
    """
    if metric not in ("em", "f1"):
        return {"skipped": True,
                "reason": f"unsupported metric {metric!r} — 'em' or 'f1'",
                "run_id": run_dir.name}
    preds = _load_predictions(run_dir, adapter)
    per_q = _load_per_question(run_dir)

    if not preds:
        return {"skipped": True,
                "reason": f"{run_dir}: predictions 0 row "
                           f"(adapter={adapter or 'any'})",
                "run_id": run_dir.name}
    if not per_q:
        return {"skipped": True,
                "reason": f"{run_dir}/per_question.csv 부재 또는 빈 파일",
                "run_id": run_dir.name}

    X: list[float] = []
    y: list[int] = []
    n_no_conf = 0
    n_no_label = 0
    for key, pred in preds.items():
        conf = _row_confidence(pred)
        if conf is None:
            n_no_conf += 1
            continue
        m = per_q.get(key)
        if not m:
            n_no_label += 1
            continue
        v_str = m.get(metric) or "0"
        try:
            v = float(v_str)
        except (TypeError, ValueError):
            n_no_label += 1
            continue
        X.append(conf)
        y.append(1 if v >= em_threshold else 0)

    platt = _platt_fit(X, y)
    bins = _reliability_bins(X, y)

    return {
        "run_id":       run_dir.name,
        "adapter":      adapter or "all",
        "metric":       metric,
        "em_threshold": em_threshold,
        "n_samples":    len(X),
        "n_no_conf":    n_no_conf,
        "n_no_label":   n_no_label,
        "platt":        platt,
        "bins":         bins,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="audit-calibrate",
                                  description=__doc__.split("\n")[0])
    ap.add_argument("--run-dir", type=Path, default=None,
                    help="eval/reports/<run> 디렉토리. 생략 시 최신 자동 선택.")
    ap.add_argument("--adapter", default=None,
                    help="adapter 한정 (예: hybrid). 생략 시 모든 adapter 합산.")
    ap.add_argument("--em-threshold", type=float, default=0.8,
                    help="metric ≥ 이 값 = correct (기본 0.8). 완화 시 0.5.")
    ap.add_argument("--metric", choices=("em", "f1"), default="em",
                    help="정답성 metric. EM (기본) 또는 F1 (synth 미동작 데이터셋 대응).")
    ap.add_argument("--out-dir", type=Path,
                    default=ROOT / "data" / "reports",
                    help="JSON + PNG 리포트 저장 위치.")
    ap.add_argument("--log-level", default="INFO")
    args = ap.parse_args(argv)
    logging.basicConfig(level=args.log_level,
                         format="%(asctime)s %(levelname)s %(name)s %(message)s")

    run_dir = args.run_dir
    if run_dir is None:
        run_dir = _find_latest_run(ROOT / "eval" / "reports")
        if run_dir is None:
            print("[audit-calibrate] FAIL — eval/reports/ 에 predictions.jsonl + "
                  "per_question.csv 가 있는 run 부재. `make eval-full` 먼저 실행.")
            return 1
        log.info("[calibrate] 최신 run 자동 선택: %s", run_dir.name)

    if not run_dir.is_dir():
        print(f"[audit-calibrate] FAIL — run-dir 부재: {run_dir}")
        return 1

    result = calibrate(run_dir, adapter=args.adapter,
                        em_threshold=args.em_threshold,
                        out_dir=args.out_dir,
                        metric=args.metric)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"calibration_{run_dir.name}_{args.adapter or 'all'}_{args.metric}"
    out_json = args.out_dir / f"{stem}.json"
    out_json.write_text(json.dumps(result, ensure_ascii=False, indent=2,
                                     default=str), encoding="utf-8")

    if result.get("skipped"):
        print(f"[audit-calibrate] SKIPPED — {result['reason']}  ({out_json})")
        return 0

    platt = result.get("platt", {})
    if not platt.get("fitted"):
        print(f"[audit-calibrate] SKIPPED — {platt.get('reason')}  ({out_json})")
        return 0

    out_png = args.out_dir / f"{stem}.png"
    png_ok = _save_diagram(result["bins"], platt, out_png,
                            title=f"Calibration {run_dir.name} ({args.adapter or 'all'}, "
                                   f"{args.metric.upper()} ≥ {args.em_threshold})")
    a, b = platt["a"], platt["b"]
    direction = ("overconfident — 등급별 confidence 하향 검토"
                  if a < 0.9 else
                  "underconfident — 등급별 confidence 상향 검토"
                  if a > 1.1 else
                  "well-calibrated")
    line = (f"[audit-calibrate] PASS — n={result['n_samples']} "
            f"Platt σ({a:.3f}x + {b:.3f}) → {direction}")
    if png_ok:
        line += f"  ({out_json} + {out_png.name})"
    else:
        line += f"  ({out_json})"
    print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

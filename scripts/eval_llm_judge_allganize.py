"""Allganize full 60 예측에 LLM-judge(Claude Sonnet) 전수 — F1 보완 측정.

기존 vector/hybrid 예측(eval/reports/allganize_full_*/＊_predictions.jsonl)을 재검색·
재합성 없이 그대로 사용해 judge(correctness/completeness/fluency)만 매긴다. judge 는
시스템 합성 LLM(OpenAI gpt-4o-mini)과 다른 provider(Anthropic Claude)로 자기편향 회피.

사용:
  env -u ... LLM_MODEL_JUDGE=claude-sonnet-4-6 LLM_SESSION_HARD_LIMIT_USD=50 \
    python3 scripts/eval_llm_judge_allganize.py
"""
from __future__ import annotations

import csv
import json
import statistics as st
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))            # eval 패키지
sys.path.insert(0, str(_ROOT / "src"))    # autonexusgraph

from eval.metrics.llm_judge import llm_judge  # noqa: E402

GOLD = "eval/qa_gold/gold_qa_allganize_v0.jsonl"
ADAPTERS = {
    "vector": "eval/reports/allganize_full_vector",
    "hybrid": "eval/reports/allganize_full_hybrid",
}
OUT = "eval/reports/allganize_full_judge.json"


def _kif(qid: str) -> bool:
    return 13 <= int(qid.split("-")[-1]) <= 30


def _gold_text(row: dict) -> str:
    g = row.get("gold_answer_text") or ""
    return g[0] if isinstance(g, list) and g else (g if isinstance(g, str) else "")


def main() -> None:
    gold = {json.loads(ln)["qid"]: json.loads(ln) for ln in open(GOLD)}
    results: dict = {}
    for name, d in ADAPTERS.items():
        preds = {json.loads(ln)["qid"]: json.loads(ln)
                 for ln in open(f"{d}/{name}_predictions.jsonl")}
        f1 = {r["qid"]: float(r["f1"]) for r in csv.DictReader(open(f"{d}/per_question.csv"))}
        rows = []
        for i, (qid, p) in enumerate(sorted(preds.items()), 1):
            g = gold[qid]
            j = llm_judge(g["question"], p.get("answer", ""), _gold_text(g), enable=True)
            j = j or {}
            rows.append({
                "qid": qid, "kif": _kif(qid),
                "correctness": j.get("correctness"), "completeness": j.get("completeness"),
                "fluency": j.get("fluency"), "f1": f1.get(qid),
                "rationale": j.get("rationale", ""),
            })
            c = j.get("correctness")
            print(f"  [{name}] {i}/{len(preds)} {qid} correctness={c}", flush=True)
        results[name] = rows
    # 집계
    summary = {}
    for name, rows in results.items():
        def agg(rs, k):
            vals = [r[k] for r in rs if r[k] is not None]
            return round(st.mean(vals), 3) if vals else None
        kif = [r for r in rows if r["kif"]]
        non = [r for r in rows if not r["kif"]]
        summary[name] = {
            "n": len(rows),
            "correctness": agg(rows, "correctness"),
            "completeness": agg(rows, "completeness"),
            "fluency": agg(rows, "fluency"),
            "f1_mean": agg(rows, "f1"),
            "correctness_KIF18": agg(kif, "correctness"),
            "correctness_nonKIF42": agg(non, "correctness"),
        }
    Path(OUT).write_text(json.dumps({"summary": summary, "per_question": results},
                                    ensure_ascii=False, indent=2))
    print("\n=== JUDGE SUMMARY ===")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"\nsaved → {OUT}")


if __name__ == "__main__":
    main()

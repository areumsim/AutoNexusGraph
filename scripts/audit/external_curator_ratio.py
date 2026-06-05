#!/usr/bin/env python3
"""외부 큐레이터 비율 측정 — gold_qa_guide.md §6.4 routine 의 정규 구현.

P1-(7) 자기충족 위험 완화 KPI:
    PRD §11.6 / docs/gold_qa_guide.md §6.1 의 "외부 큐레이터 30%+ 목표"
    를 실측. external_curator / allganize_external / academic 태그가 있는
    row 비율을 도메인별 + 전체로 계산.

사용:
    python scripts/audit/external_curator_ratio.py            # 전체
    python scripts/audit/external_curator_ratio.py --target 0.30   # 목표 30%
    python scripts/audit/external_curator_ratio.py --strict   # 목표 미달 시 exit 1

판정 기준:
    row 가 "외부 큐레이터" 로 카운트되려면 다음 중 하나:
      - tags 에 'external_curator' / 'allganize_external' / 'academic_external' 포함
      - notes 에 정규식 매칭 ('external_curator' / 'allganize' / 'academic')
      - qid 가 'ALG-' / 'EXT-' / 'ACA-' 로 시작

출력:
    data/reports/external_curator_ratio.json — 도메인별 + 전체 + 목표 대비
    stdout — 한 줄 요약 + 도메인 표
"""

from __future__ import annotations

import argparse
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

log = logging.getLogger(__name__)

GOLD_DIR = ROOT / "eval" / "qa_gold"
SUFFIX_EXAMPLE = (".example.jsonl",)   # 픽스처 — ratio 계산 제외

# row tag/notes/qid 의 외부 큐레이터 패턴.
_EXT_TAG_SET = {"external_curator", "allganize_external", "academic_external"}
_EXT_NOTES_RE = re.compile(r"\b(external_curator|allganize|academic)\b",
                            re.IGNORECASE)
_EXT_QID_RE = re.compile(r"^(ALG|EXT|ACA)-")


def _is_external(row: dict) -> bool:
    """row 가 외부 큐레이터 출처인지 판정."""
    tags = row.get("tags") or []
    if isinstance(tags, list) and any(t in _EXT_TAG_SET for t in tags):
        return True
    notes = row.get("notes") or ""
    if isinstance(notes, str) and _EXT_NOTES_RE.search(notes):
        return True
    qid = row.get("qid") or ""
    if isinstance(qid, str) and _EXT_QID_RE.match(qid):
        return True
    return False


def _domain_of(row: dict, fp: Path) -> str:
    """row.domain 우선, 없으면 파일명 휴리스틱."""
    d = (row.get("domain") or "").strip().lower()
    if d:
        return d
    n = fp.name.lower()
    if "auto" in n:
        return "auto"
    if "ip" in n:
        return "ip"
    if "cross" in n:
        return "cross_domain"
    return "finance"


def scan() -> dict:
    """모든 gold_qa_*_v0.jsonl 스캔 → 도메인별·합산 비율."""
    if not GOLD_DIR.exists():
        return {"error": f"GOLD_DIR 부재: {GOLD_DIR}"}

    by_domain: dict[str, dict] = {}
    total_n = total_ext = 0
    file_breakdown: list[dict] = []
    for fp in sorted(GOLD_DIR.glob("gold_qa_*.jsonl")):
        # example/staging 픽스처 제외.
        if fp.name.endswith(SUFFIX_EXAMPLE):
            continue
        if "staging" in fp.parts:
            continue
        n = ext = 0
        try:
            for line in fp.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                n += 1
                if _is_external(row):
                    ext += 1
                d = _domain_of(row, fp)
                slot = by_domain.setdefault(d, {"n": 0, "ext": 0})
                slot["n"] += 1
                if _is_external(row):
                    slot["ext"] += 1
        except Exception as exc:   # noqa: BLE001 — 1 unit 실패 흡수 → log + continue (부분 성공 보존)
            log.warning("[ratio] read %s 실패: %s", fp.name, exc)
            continue
        total_n += n
        total_ext += ext
        file_breakdown.append({
            "file":  fp.name,
            "n":     n,
            "ext":   ext,
            "ratio": (ext / n) if n else 0.0,
        })

    domain_breakdown = sorted(
        ({"domain": d, "n": v["n"], "ext": v["ext"],
          "ratio": (v["ext"] / v["n"]) if v["n"] else 0.0}
         for d, v in by_domain.items()),
        key=lambda r: r["domain"],
    )
    return {
        "total_n":    total_n,
        "total_ext":  total_ext,
        "total_ratio": (total_ext / total_n) if total_n else 0.0,
        "by_domain":  domain_breakdown,
        "by_file":    file_breakdown,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="external_curator_ratio",
                                  description=__doc__.split("\n")[0])
    ap.add_argument("--target", type=float, default=0.30,
                    help="목표 비율 (기본 0.30 = 30%). PRD §11.6 / gold_qa_guide §6")
    ap.add_argument("--strict", action="store_true",
                    help="목표 미달 시 exit 1 (CI 게이트용)")
    ap.add_argument("--out", type=Path,
                    default=ROOT / "data" / "reports" / "external_curator_ratio.json",
                    help="JSON 리포트 경로")
    ap.add_argument("--log-level", default="WARNING")
    args = ap.parse_args(argv)
    logging.basicConfig(level=args.log_level,
                         format="%(asctime)s %(levelname)s %(name)s %(message)s")

    result = scan()
    if "error" in result:
        print(f"[external-ratio] FAIL — {result['error']}")
        return 1

    ts = datetime.now(timezone.utc).isoformat()
    payload = {
        "measured_at": ts,
        "target":      args.target,
        "met":         result["total_ratio"] >= args.target,
        **result,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                        encoding="utf-8")

    pct = result["total_ratio"] * 100
    mark = "✅" if payload["met"] else "❌"
    summary = (f"[external-ratio] {result['total_ext']}/{result['total_n']} "
               f"= {pct:.1f}% (target {args.target*100:.0f}%) {mark}")
    print(summary)
    for d in result["by_domain"]:
        dp = d["ratio"] * 100
        print(f"  {d['domain']:13s} {d['ext']:3d} / {d['n']:3d} = {dp:5.1f}%")
    print(f"  → {args.out}")

    if args.strict and not payload["met"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

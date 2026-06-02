#!/usr/bin/env python3
"""Allganize RAG-Evaluation-Dataset-KO → 본 시스템 gold_qa schema 변환기.

P1-(7) gold QA 자기충족 위험 해결 routine (사용자 cold review 2026-06-02):
    docs/gold_qa_guide.md §6.3 의 "표준 변환 스크립트 미구현" 슬롯을 실제 runnable
    스크립트로 대체. Allganize 외부 벤치 흡수로 "외부 큐레이터 30%" 정책 진입.

라이선스: Allganize RAG-Evaluation-Dataset-KO 는 공개 dataset (GitHub allganize/
RAG-Evaluation-Dataset-KO). 본 변환은 schema 매핑만 — 원문 라이선스 그대로 유지.

사용:
    # 1. Allganize raw 다운로드 (사용자 단계)
    git clone https://github.com/allganize/RAG-Evaluation-Dataset-KO \
        data/external/allganize-rag-kor

    # 2. 변환 (도메인 한정)
    python scripts/audit/convert_allganize_gold.py \
        --src data/external/allganize-rag-kor/finance \
        --domain finance \
        --out eval/qa_gold/staging/gold_qa_allganize_v0.jsonl

    # 3. 검증 (--no-db 옵션 — 외부 row 는 우리 DB 매칭 안 될 수 있음)
    python scripts/audit/validate_gold_qa.py \
        eval/qa_gold/staging/gold_qa_allganize_v0.jsonl --no-db

    # 4. 답변 가능한 row 만 staging → live
    mv eval/qa_gold/staging/gold_qa_allganize_v0.jsonl eval/qa_gold/

    # 5. 비율 검증
    python scripts/audit/external_curator_ratio.py

input 포맷 (Allganize 일반 RAG eval schema — best-effort):
    {
      "question": "현대자동차의 2023년 매출은?",
      "answer": "162조 원",
      "context": "...",
      "domain": "finance",          # optional — CLI --domain override
      "difficulty": "easy"           # optional — level 매핑
    }

output 포맷 (`docs/gold_qa_guide.md §1 스키마`):
    {
      "qid": "ALG-FIN-001",
      "question": "...",
      "gold_answer_text": ["..."],  # 원문 answer 1개 — paraphrase 보강은 후속
      "gold_answer_entities": [],
      "domain": "finance",
      "level": "L1",
      "is_answerable": true,
      "evidence_corp_codes": [],     # Allganize 는 본 시스템 corp_code 없음 — 비움
      "tags": ["allganize_external", "external_curator"],
      "notes": "external_curator;allganize_external;src=<source_path>"
    }
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[2]

log = logging.getLogger(__name__)


# Allganize difficulty → 본 시스템 level 매핑 (best-effort, 휴리스틱).
_LEVEL_MAP = {
    "easy":   "L1",
    "medium": "L2",
    "hard":   "L3",
    "쉬움":   "L1",
    "보통":   "L2",
    "어려움": "L3",
}


def _iter_rows(src: Path) -> Iterable[dict]:
    """jsonl / json / csv 자동 감지 stream."""
    if src.is_file():
        files = [src]
    elif src.is_dir():
        files = sorted(list(src.rglob("*.jsonl")) + list(src.rglob("*.json"))
                       + list(src.rglob("*.csv")))
    else:
        return
    for fp in files:
        try:
            if fp.suffix.lower() == ".jsonl":
                for line in fp.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line:
                        try:
                            row = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        row["_src"] = str(fp)
                        yield row
            elif fp.suffix.lower() == ".json":
                data = json.loads(fp.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    for r in data:
                        r["_src"] = str(fp)
                        yield r
                elif isinstance(data, dict) and isinstance(data.get("data"), list):
                    for r in data["data"]:
                        r["_src"] = str(fp)
                        yield r
            elif fp.suffix.lower() == ".csv":
                with fp.open(encoding="utf-8") as f:
                    for r in csv.DictReader(f):
                        r["_src"] = str(fp)
                        yield r
        except Exception as exc:   # noqa: BLE001
            log.warning("[allganize] read %s 실패: %s", fp.name, exc)


def _level_from_difficulty(row: dict, default: str = "L1") -> str:
    diff = (row.get("difficulty") or row.get("level") or "").strip().lower()
    return _LEVEL_MAP.get(diff, default)


def convert_one(row: dict, *, qid: str, domain: str) -> dict | None:
    """Allganize row → 본 schema. None 시 skip."""
    q = (row.get("question") or row.get("query")
          or row.get("title") or "").strip()
    a = row.get("answer") or row.get("gold_answer") or row.get("response")
    if not q or not a:
        return None
    if isinstance(a, list):
        gold_answer_text = [str(x).strip() for x in a if str(x).strip()]
    else:
        gold_answer_text = [str(a).strip()]
    if not gold_answer_text:
        return None
    return {
        "qid":                  qid,
        "question":             q,
        "question_type":        "single_entity",
        "complexity":           "medium",
        "requires_multi_hop":   False,
        "hop_count":            1,
        "domain":               domain,
        "level":                _level_from_difficulty(row),
        "gold_answer_text":     gold_answer_text,
        "gold_answer_entities": [],
        "evidence_corp_codes":  [],
        "is_answerable":        True,
        "tags":                 ["allganize_external", "external_curator"],
        "notes": (f"external_curator;allganize_external;"
                  f"src={row.get('_src', 'unknown')}"
                  + (f";orig_difficulty={row['difficulty']}"
                     if row.get('difficulty') else "")),
    }


def convert(src: Path, *, domain: str, qid_prefix: str = "ALG-FIN",
             limit: int | None = None) -> list[dict]:
    """Allganize raw → 변환된 row list."""
    out: list[dict] = []
    for i, raw in enumerate(_iter_rows(src), start=1):
        if limit and len(out) >= limit:
            break
        qid = f"{qid_prefix}-{i:03d}"
        norm = convert_one(raw, qid=qid, domain=domain)
        if norm:
            out.append(norm)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="convert_allganize_gold",
                                  description=__doc__.split("\n")[0])
    ap.add_argument("--src", type=Path, required=True,
                    help="Allganize raw 파일 또는 디렉토리 (jsonl/json/csv 자동 감지)")
    ap.add_argument("--domain", default="finance",
                    choices=("finance", "auto", "ip", "cross_domain"),
                    help="모든 row 의 domain (Allganize finance subset = 'finance')")
    ap.add_argument("--qid-prefix", default=None,
                    help="qid 접두사. 기본 = 도메인별 자동 (ALG-FIN/ALG-AUTO/...)")
    ap.add_argument("--limit", type=int, default=None,
                    help="첫 N row 만 (smoke)")
    ap.add_argument("--out", type=Path, required=True,
                    help="출력 jsonl — 통상 eval/qa_gold/staging/gold_qa_allganize_v0.jsonl")
    ap.add_argument("--log-level", default="INFO")
    args = ap.parse_args(argv)
    logging.basicConfig(level=args.log_level,
                         format="%(asctime)s %(levelname)s %(name)s %(message)s")

    if not args.src.exists():
        print(f"[convert-allganize] FAIL — src 부재: {args.src}")
        print("Allganize 데이터는 별도 다운로드 필요:")
        print("  git clone https://github.com/allganize/RAG-Evaluation-Dataset-KO "
              "data/external/allganize-rag-kor")
        return 1

    qid_prefix = args.qid_prefix or {
        "finance":      "ALG-FIN",
        "auto":         "ALG-AUTO",
        "ip":           "ALG-IP",
        "cross_domain": "ALG-CD",
    }[args.domain]

    rows = convert(args.src, domain=args.domain,
                    qid_prefix=qid_prefix, limit=args.limit)
    if not rows:
        print(f"[convert-allganize] WARN — 변환된 row 0 (src 미존재 / 빈 / parse 실패)")
        return 0

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"[convert-allganize] PASS — {len(rows)} rows → {args.out}")
    print("다음 단계:")
    print(f"  python scripts/audit/validate_gold_qa.py {args.out} --no-db")
    print(f"  mv {args.out} eval/qa_gold/")
    print( "  python scripts/audit/external_curator_ratio.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

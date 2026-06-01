"""P3 IR LLM 추출 — OEM IR/뉴스룸 본문 → MANUFACTURED_AT / CAPACITY_REPORTED.

흐름 (run_p3.py 와 동일 패턴):
  1) chunk_selector.select_ir_chunks(oems=[...]) — vec.chunks (source='oem_ir') 필터.
  2) (옵션) --dry-run-cost 시 추정만 출력.
  3) ExtractorEngine([IRRelationExtractor()]) 로 chunk 별 LLM 호출.
  4) merged relations → staging_writer.upsert_staging → auto.staging_relations.
  5) cross_validate.run_p4 (별도) 가 DART production 표와 정합 검사 후
     Neo4j MANUFACTURED_AT 보강.

CLI:
    # 비용 추정만 (LLM 호출 0)
    python -m autograph.extractors.run_p3_ir --oems hyundai --dry-run-cost

    # 실제 추출 (budget guard hard limit $1)
    python -m autograph.extractors.run_p3_ir --oems hyundai \\
        --sections ir --limit 30 --hard-limit-usd 1.0
"""

from __future__ import annotations

import argparse
import logging
from typing import Sequence

from autonexusgraph.extractors.base import RunContext
from autonexusgraph.extractors.engine import ExtractorEngine
from autonexusgraph.llm.base import get_llm_client
from autonexusgraph.llm.budget_aware import budget_aware_client
from autonexusgraph.llm.cost import estimate

from .chunk_selector import IR_SOURCES, select_ir_chunks
from .ir_relation_extractor import IRRelationExtractor
from .staging_writer import upsert_staging


log = logging.getLogger(__name__)


# corp_code → 한국어 OEM 이름 (LLM prompt context 보강용)
_OEM_DISPLAY_NAMES = {
    "hyundai":       "현대자동차",
    "kia":           "기아",
    "kia_worldwide": "기아 (worldwide)",
    "mobis":         "현대모비스",
}


def estimate_ir_cost(chunks: list[dict], model: str = "gpt-4o-mini"):
    """IR 본문은 일반적으로 더 김 (avg 8000+ chars)."""
    n = len(chunks)
    if n == 0:
        return None
    avg_chunk_chars = sum(len(c.get("text") or "") for c in chunks) / n
    # IR prompt: system 1800 + user_template 700 + chunk_text/3
    avg_in_tokens = 1800 + 700 + avg_chunk_chars / 3
    avg_out_tokens = 500
    return estimate(model, n, avg_in_tokens, avg_out_tokens)


def run(
    *,
    oems: Sequence[str] | None,
    sections: Sequence[str] | None,
    sources: Sequence[str],
    limit: int,
    dry_run_cost: bool,
    hard_limit_usd: float | None,
) -> dict:
    chunks = select_ir_chunks(
        oems=oems,
        sources=sources or IR_SOURCES,
        sections=sections,
        limit=limit,
    )
    if not chunks:
        log.info("[run_p3_ir] 0 chunks selected — skip")
        return {"chunks": 0}

    if dry_run_cost:
        est = estimate_ir_cost(chunks)
        log.info("[run_p3_ir] DRY-RUN-COST: %s", est)
        return {"chunks": len(chunks), "estimate": est}

    extractor = IRRelationExtractor()
    inner = get_llm_client(role="research")
    client = budget_aware_client(inner, caller="ir_p3",
                                  hard_limit=hard_limit_usd)

    ctx = RunContext(
        llm_client=client,
        prompt_spec=extractor.prompt,
        extra={"oem_names": _OEM_DISPLAY_NAMES},
    )

    engine = ExtractorEngine([extractor], max_concurrency=1)
    all_rels: list[dict] = []
    for c in chunks:
        merged, _ = engine.process(c, ctx)
        all_rels.extend(merged)

    counts = upsert_staging(all_rels,
                             extractor_name=extractor.name,
                             extractor_version=extractor.version)

    log.info("[run_p3_ir] chunks=%d relations=%d gate=%s",
             len(chunks), len(all_rels), counts)
    return {
        "chunks": len(chunks),
        "relations": len(all_rels),
        "gate": counts,
        "engine_stats": {
            "n_chunks": engine.stats.n_chunks,
            "n_extractor_calls": engine.stats.n_extractor_calls,
            "n_warnings": engine.stats.n_warnings,
            "total_latency_ms": engine.stats.total_latency_ms,
        },
    }


def main() -> None:
    ap = argparse.ArgumentParser(prog="autograph.extractors.run_p3_ir")
    ap.add_argument("--oems",
                    type=lambda s: [x.strip() for x in s.split(",") if x.strip()],
                    default=None,
                    help="콤마 구분 (예: hyundai,kia_worldwide). 빈값=전체.")
    ap.add_argument("--sections",
                    type=lambda s: [x.strip() for x in s.split(",") if x.strip()],
                    default=None,
                    help="section prefix 필터 (예: ir/quarterly_earnings)")
    ap.add_argument("--sources",
                    type=lambda s: [x.strip() for x in s.split(",") if x.strip()],
                    default=list(IR_SOURCES))
    ap.add_argument("--limit", type=int, default=50,
                    help="IR 본문은 크므로 보수적 기본값.")
    ap.add_argument("--dry-run-cost", action="store_true",
                    help="LLM 호출 없이 비용 추정만")
    ap.add_argument("--hard-limit-usd", type=float, default=None,
                    help="BudgetExceeded 보호 — USD")
    ap.add_argument("--log-level", default="INFO")
    args = ap.parse_args()
    logging.basicConfig(level=args.log_level,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")

    out = run(
        oems=args.oems,
        sections=args.sections,
        sources=args.sources,
        limit=args.limit,
        dry_run_cost=args.dry_run_cost,
        hard_limit_usd=args.hard_limit_usd,
    )
    import json
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()


__all__ = ["run", "estimate_ir_cost"]

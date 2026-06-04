"""LLM 기반 :DefectType taxonomy 추출 — NHTSA + KOTSA defect_summary → auto.defect_types.

Phase 1 (본 모듈): 1,434 리콜 텍스트 중 N건 샘플 → Claude API 1회 호출 →
                   ~30~50 결함 메커니즘 카테고리 추출 → auto.defect_types 적재.
Phase 2 (별도):    1,434건 전체 → 카테고리 분류 → auto.defect_matches (llm_assign).

grade C (LLM): confidence_score=0.700, validated_status='candidate', extraction_method='llm'.

CLI:
    python -m autograph.loaders.extract_defect_types_llm --dry-run
    python -m autograph.loaders.extract_defect_types_llm --n-sample 200 --model claude-sonnet-4-6
"""

from __future__ import annotations

import argparse
import json
import logging
import re
from typing import Any

from autonexusgraph.db.postgres import get_connection


log = logging.getLogger(__name__)


PROMPT_TAXONOMY = """You are a senior quality-engineering taxonomist analyzing **automotive recall texts** (mixed English from NHTSA and Korean from KOTSA).

Read the {n} recall texts below and identify **30 to 50 distinct defect MECHANISM categories** that cover them. Categories must describe **how** the defect happens (mechanism), not which part. Group similar mechanisms across different parts.

For EACH category produce a JSON object with these fields:
- "name":              snake_case English identifier, <= 60 chars, unique. Example: "fuel_pump_impeller_interference"
- "name_en":           natural English, <= 100 chars. Example: "Fuel pump impeller interference"
- "name_ko":           Korean translation, <= 100 chars. Example: "연료펌프 임펠러 간섭"
- "category":          ONE of: mechanical | electrical | software | material | assembly | design | process | safety_system
- "description":       ONE concise sentence (<= 200 chars) describing the mechanism
- "representative_text": ONE canonical text from the INPUT that exemplifies this category (verbatim)

Output rules — MUST FOLLOW:
1. Output a single JSON object: {{"defect_types": [ ... ]}}
2. NO commentary outside JSON. NO markdown fences. JSON only.
3. Cover both Korean and English texts. Categories should be **mechanism-level** (e.g. "weld_porosity", "software_logic_error", "adhesive_bond_failure"), not part-level ("airbag", "brake").
4. Avoid duplicates. If two texts describe the same mechanism, they share one category.

Texts:
{texts}
"""


def sample_recall_texts(n: int = 200, seed: int = 42) -> list[tuple]:
    """auto.events_recalls 에서 N건 무작위 샘플. source 균형 위해 stratified."""
    conn = get_connection()
    # NHTSA 493 + KOTSA 941 = 1,434 → 비율대로 (NHTSA 34% / KOTSA 66%)
    nhtsa_n = int(n * 0.34)
    kotsa_n = n - nhtsa_n
    out: list[tuple] = []
    with conn.cursor() as cur:
        cur.execute("SELECT setseed(%s)", (0.42,))
        for src, cnt in (("nhtsa", nhtsa_n), ("datagokr_kotsa", kotsa_n)):
            cur.execute("""
                SELECT recall_id, source, source_recall_no, component_text, defect_summary
                  FROM auto.events_recalls
                 WHERE source = %s
                   AND defect_summary IS NOT NULL
                   AND length(defect_summary) > 30
                 ORDER BY random()
                 LIMIT %s
            """, (src, cnt))
            out.extend(cur.fetchall())
    return out


def format_corpus(samples: list[tuple]) -> str:
    """샘플 → LLM 입력 텍스트 블록. 각 행은 source/component/defect 한 줄."""
    lines: list[str] = []
    for i, (rid, src, no, comp, defect) in enumerate(samples, 1):
        comp_s = (comp or "-").strip()[:80]
        defect_s = (defect or "").strip().replace("\n", " ")[:400]
        src_tag = "NHTSA" if src == "nhtsa" else ("KOTSA" if src == "datagokr_kotsa" else src)
        lines.append(f"[{i}] ({src_tag}) component={comp_s} | defect={defect_s}")
    return "\n".join(lines)


def _strip_json_fence(text: str) -> str:
    """LLM이 ```json ... ``` 감싸면 벗기기."""
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, flags=re.DOTALL)
    if m:
        return m.group(1)
    # 첫 { 부터 마지막 } 까지
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return text[start:end + 1]
    return text


def call_llm(prompt: str, *, model: str, max_tokens: int = 8000) -> tuple[str, dict]:
    """get_llm_client + budget_aware 경유 — cost_log 기록 + 비용 가드 통과.

    (과거: raw ``Anthropic()`` 직접 호출로 cost_log/guard 를 통째로 우회했음.
    이제 다른 모든 LLM 호출과 동일하게 LoggingLLMClient + BudgetAwareLLMClient
    경유 → 누적 비용 기록 및 세션 한도 차단 대상에 포함.)
    """
    from autonexusgraph.llm.base import get_llm_client
    from autonexusgraph.llm.budget_aware import budget_aware_client

    inner = get_llm_client(model=model)
    client = budget_aware_client(inner, caller="extract_defect_types_llm")
    resp = client.chat(
        [{"role": "user", "content": prompt}],
        temperature=0.0,
        max_tokens=max_tokens,
        purpose="defect_taxonomy",
    )
    usage = {
        "input_tokens": resp.usage.prompt_tokens,
        "output_tokens": resp.usage.completion_tokens,
        "model": resp.usage.model or model,
    }
    return resp.content, usage


def extract_taxonomy(*, n_sample: int = 200, model: str) -> tuple[list[dict], dict]:
    samples = sample_recall_texts(n_sample)
    if not samples:
        raise RuntimeError("샘플 0건 — auto.events_recalls 비어있음")
    corpus = format_corpus(samples)
    prompt = PROMPT_TAXONOMY.format(n=len(samples), texts=corpus)
    log.info("[llm.taxonomy] %d samples, prompt %d chars, model=%s",
             len(samples), len(prompt), model)
    raw, usage = call_llm(prompt, model=model)
    cleaned = _strip_json_fence(raw)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        log.error("[llm.taxonomy] JSON parse 실패: %s\n--- raw ---\n%s", e, raw[:2000])
        raise
    types = data.get("defect_types") or []
    log.info("[llm.taxonomy] extracted %d defect_types | usage in=%d out=%d",
             len(types), usage["input_tokens"], usage["output_tokens"])
    return types, usage


def upsert_defect_types(types: list[dict], *, model_tag: str) -> int:
    from datetime import datetime
    snapshot_year = datetime.utcnow().year
    conn = get_connection()
    n = 0
    sql = """
    INSERT INTO auto.defect_types
        (name, name_en, name_ko, description, category, representative_text,
         source, source_type, source_id, confidence_score, validated_status,
         snapshot_year, extraction_method, schema_version, raw)
    VALUES (%s, %s, %s, %s, %s, %s,
            'recall_text_llm', 'recall_text_label_extraction',
            %s, 0.700, 'candidate',
            %s, 'llm', 'defect_type_v1', %s::jsonb)
    ON CONFLICT (name) DO UPDATE SET
        name_en             = EXCLUDED.name_en,
        name_ko             = EXCLUDED.name_ko,
        description         = EXCLUDED.description,
        category            = EXCLUDED.category,
        representative_text = COALESCE(EXCLUDED.representative_text, auto.defect_types.representative_text),
        updated_at          = now()
    """
    try:
        with conn.cursor() as cur:
            for t in types:
                name = (t.get("name") or "").strip()
                if not name:
                    continue
                meta = {**t, "_llm_model": model_tag}
                cur.execute(sql, (
                    name[:120],
                    (t.get("name_en") or None) and t["name_en"][:160],
                    (t.get("name_ko") or None) and t["name_ko"][:160],
                    t.get("description"),
                    (t.get("category") or "").strip().lower() or None,
                    t.get("representative_text"),
                    f"defect_type:{name}",
                    snapshot_year,
                    json.dumps(meta, ensure_ascii=False),
                ))
                n += cur.rowcount or 0
        conn.commit()
    except Exception as e:   # noqa: BLE001
        log.warning("[llm.taxonomy] upsert 실패 — rollback: %s", e)
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    return n


def main() -> int:
    ap = argparse.ArgumentParser(prog="autograph.loaders.extract_defect_types_llm",
                                  description=__doc__.split("\n")[0])
    ap.add_argument("--n-sample", type=int, default=200,
                    help="taxonomy 추출용 무작위 샘플 행수 (NHTSA 34% + KOTSA 66% stratified)")
    ap.add_argument("--model", default="claude-sonnet-4-6",
                    help="Anthropic 모델 ID — sonnet-4-6 권장 (taxonomy 추출은 1회)")
    ap.add_argument("--dry-run", action="store_true",
                    help="LLM 호출 후 적재 안 함 (검수용)")
    ap.add_argument("--log-level", default="INFO")
    args = ap.parse_args()
    logging.basicConfig(level=args.log_level,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")

    types, usage = extract_taxonomy(n_sample=args.n_sample, model=args.model)
    print(f"\n[taxonomy] {len(types)} defect_types extracted")
    print(f"[usage] model={usage['model']} in={usage['input_tokens']} out={usage['output_tokens']}")
    # 카테고리 분포
    from collections import Counter
    cat = Counter((t.get("category") or "?").lower() for t in types)
    print(f"[category dist] {dict(cat)}")
    # 첫 10건 미리보기
    print("\n=== 추출된 :DefectType 미리보기 (앞 10) ===")
    for t in types[:10]:
        print(f"  - {t.get('name'):<45} [{t.get('category'):<13}] {(t.get('name_ko') or '')[:25]:<25} | {(t.get('description') or '')[:80]}")

    if args.dry_run:
        print("\n[dry-run] 적재 생략")
        # JSON 덤프 (검수용)
        out_path = "data/raw/kamp/_defect_taxonomy_dryrun.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump({"usage": usage, "defect_types": types}, f, ensure_ascii=False, indent=2)
        print(f"[dry-run] saved: {out_path}")
        return 0

    n = upsert_defect_types(types, model_tag=args.model)
    print(f"\n[OK] upserted {n} rows into auto.defect_types")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

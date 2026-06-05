"""자동차 텍스트 청크 → anxg_vec.chunks 적재.

대상:
- nhtsa_recalls 의 Summary / Consequence / Remedy 본문
- nhtsa_complaints 의 summary 본문
- wikipedia_auto 본문 (extract + html 일부) — autograph.ingestion.wikipedia_auto 가 producer

청크 단위:
- 보고서 1건당 1청크 (작아서 분리 불필요). token_count 는 단순 char/4 추정.
- wiki: 페이지당 1청크 (extract + infobox key=value 직렬화).
- source: 'nhtsa_recall' | 'nhtsa_complaint' | 'wikipedia_auto'
- 메타: source_recall_no / source_complaint_no, manufacturer_id, model_id, variant_id

embedding 은 본 모듈에서 호출하지 않음 — 기존 finance 와 동일하게 별도
`make embed-chunks` 등으로 BGE-M3 호출 후 backfill.

CLI:
    python -m autograph.loaders.build_chunks_auto
    python -m autograph.loaders.build_chunks_auto --source wikipedia
    python -m autograph.loaders.build_chunks_auto --dry-run
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from autonexusgraph.config import get_settings
from autonexusgraph.db.postgres import get_connection

log = logging.getLogger(__name__)


# anxg_vec.chunks 의 rcept_no/section/chunk_idx UNIQUE(rcept_no, chunk_idx) 가 있어
# 자동차 청크는 rcept_no=NULL → unique 충돌 회피 위해 metadata.uniq 키 활용.
# section='auto.recall'|'auto.complaint' 로 구분.
def _upsert_chunk(cur, *, source: str, section: str, text: str,
                  metadata: dict,
                  manufacturer_id: int | None,
                  model_id: int | None,
                  variant_id: int | None) -> None:
    # corp_code 는 nullable 로 완화됨 (09 migration). source_uniq 를 metadata 에 박아 dedup.
    uniq = metadata.get("uniq")
    if not uniq:
        raise ValueError("metadata['uniq'] 필요")

    cur.execute("""
        SELECT id, manufacturer_id, model_id, variant_id FROM anxg_vec.chunks
        WHERE source = %s AND metadata->>'uniq' = %s
        LIMIT 1
    """, (source, uniq))
    existing = cur.fetchone()
    if existing:
        # 기존 row 의 NULL 메타만 보강 (이미 채워진 값은 보존).
        cid, ex_mfr, ex_model, ex_variant = existing
        if (manufacturer_id and not ex_mfr) or (model_id and not ex_model) or (variant_id and not ex_variant):
            cur.execute("""
                UPDATE anxg_vec.chunks
                   SET manufacturer_id = COALESCE(manufacturer_id, %s),
                       model_id        = COALESCE(model_id, %s),
                       variant_id      = COALESCE(variant_id, %s)
                 WHERE id = %s
            """, (manufacturer_id, model_id, variant_id, cid))
        return

    # 통합 estimator — chunking/chunker.estimate_tokens 가 단일 진실. 과거 //4
    # 휴리스틱은 finance loaders/chunks 의 //2 와 불일치 → 동일 값으로 정렬.
    from autonexusgraph.chunking.chunker import estimate_tokens
    token_est = estimate_tokens(text)
    cur.execute("""
        INSERT INTO anxg_vec.chunks
          (corp_code, rcept_no, section, chunk_idx, text, token_count,
           metadata, source, manufacturer_id, model_id, variant_id)
        VALUES (NULL, NULL, %s, 0, %s, %s,
                %s::jsonb, %s, %s, %s, %s)
    """, (section, text, token_est,
          json.dumps(metadata, ensure_ascii=False, default=str),
          source, manufacturer_id, model_id, variant_id))


_RECALL_SRC_MAP: dict[str, str] = {
    "nhtsa":          "nhtsa_recall",
    "datagokr_kotsa": "kotsa_recall",
    "eu_safety_gate": "eu_recall",
}


def build_from_recalls() -> int:
    """anxg_auto.events_recalls 모든 행 → anxg_vec.chunks.

    source 별 chunk 라벨 (DEFECT_MATCHES 빌더가 이 라벨로 매칭):
        nhtsa            → 'nhtsa_recall'   (영문)
        datagokr_kotsa   → 'kotsa_recall'   (한국어, KOTSA)
        그 외             → 'other_recall'
    """
    conn = get_connection()
    n_by_src: dict[str, int] = {}
    with conn.cursor() as cur:
        cur.execute("""
            SELECT recall_id, source, source_recall_no, manufacturer_id, model_id, variant_id,
                   component_text, defect_summary, consequence, remedy_summary,
                   report_date
              FROM anxg_auto.events_recalls
        """)
        rows = cur.fetchall()
    with conn.cursor() as cur:
        for r in rows:
            (recall_id, src, no, mfr_id, model_id, variant_id,
             comp, defect, conseq, remedy, rdate) = r
            chunk_src = _RECALL_SRC_MAP.get(src, "other_recall")
            text_parts = []
            if comp:
                text_parts.append(f"부품: {comp}")
            if defect:
                text_parts.append(f"결함: {defect}")
            if conseq:
                text_parts.append(f"위험: {conseq}")
            if remedy:
                text_parts.append(f"조치: {remedy}")
            text = "\n".join(text_parts).strip()
            if not text:
                continue
            try:
                _upsert_chunk(cur,
                    source=chunk_src,
                    section="auto.recall",
                    text=text,
                    metadata={
                        "uniq": f"{chunk_src}::{no}",
                        "source_recall_no": no,
                        "recall_source": src,
                        "report_date": rdate.isoformat() if rdate else None,
                    },
                    manufacturer_id=mfr_id,
                    model_id=model_id,
                    variant_id=variant_id)
                n_by_src[chunk_src] = n_by_src.get(chunk_src, 0) + 1
            except Exception as e:  # noqa: BLE001 — [chunks:recall] %s 흡수 → total 반환
                log.warning("[chunks:recall] %s: %s", no, e)
    conn.commit()
    total = sum(n_by_src.values())
    log.info("[chunks:recall] inserted/updated=%d by_source=%s", total, n_by_src)
    return total


def build_from_complaints() -> int:
    conn = get_connection()
    n = 0
    with conn.cursor() as cur:
        cur.execute("""
            SELECT complaint_id, source_complaint_no, manufacturer_id, model_id, variant_id,
                   summary, filed_date
              FROM anxg_auto.events_complaints
        """)
        rows = cur.fetchall()
    with conn.cursor() as cur:
        for r in rows:
            (cid, no, mfr_id, model_id, variant_id, summary, fdate) = r
            if not summary:
                continue
            try:
                _upsert_chunk(cur,
                    source="nhtsa_complaint",
                    section="auto.complaint",
                    text=summary,
                    metadata={
                        "uniq": f"nhtsa_complaint::{no}",
                        "filed_date": fdate.isoformat() if fdate else None,
                    },
                    manufacturer_id=mfr_id,
                    model_id=model_id,
                    variant_id=variant_id)
                n += 1
            except Exception as e:  # noqa: BLE001 — [chunks:complaint] %s 흡수 → n 반환
                log.warning("[chunks:complaint] %s: %s", no, e)
    conn.commit()
    log.info("[chunks:complaint] inserted=%d", n)
    return n


def _wikipedia_root() -> Path:
    return get_settings().ingest_raw_dir / "auto" / "wikipedia"


def _infobox_to_text(infobox: dict | None) -> str:
    """{{Infobox 회사 ...}} dict → 'key: value\\n' 직렬화. 검색 가능 텍스트화."""
    if not infobox:
        return ""
    lines: list[str] = []
    for k, v in infobox.items():
        if not (k and v):
            continue
        # 너무 긴 값은 트리밍 (이미 client 가 1000 자 cap).
        lines.append(f"{k}: {v}")
    return "\n".join(lines)


def _strip_html(html: str) -> str:
    """매우 단순 HTML → 텍스트. 태그 제거 + entity 단순 처리. 외부 lib 의존 회피."""
    import re as _re
    if not html:
        return ""
    # script/style 블록 제거.
    txt = _re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html,
                  flags=_re.IGNORECASE | _re.DOTALL)
    # 모든 태그 제거.
    txt = _re.sub(r"<[^>]+>", " ", txt)
    # entity 단순 디코드.
    txt = (txt.replace("&amp;", "&").replace("&lt;", "<")
              .replace("&gt;", ">").replace("&quot;", '"')
              .replace("&#160;", " ").replace("&nbsp;", " "))
    # 공백 정리.
    txt = _re.sub(r"\s+", " ", txt).strip()
    return txt


def build_from_wikipedia(*, max_html_chars: int = 4000) -> int:
    """data/raw/auto/wikipedia/**/*.json → anxg_vec.chunks (source='wikipedia_auto').

    페이지 1건당 1 청크. 본문은:
        title + '\\n' + summary(extract) + '\\n[Infobox]\\n' + key:value... + '\\n' + html_text(앞부분)

    매우 큰 페이지의 html_text 는 ``max_html_chars`` 까지만 — embedding 비용 가드.
    """
    root = _wikipedia_root()
    if not root.exists():
        log.warning("[chunks:wiki] root missing: %s — ingestion 먼저 실행", root)
        return 0

    conn = get_connection()
    n = 0
    with conn.cursor() as cur:
        # 경로: {lang}/{models|manufacturers}/{id}.json
        for f in root.glob("*/*/*.json"):
            try:
                payload = json.loads(f.read_text(encoding="utf-8"))
            except json.JSONDecodeError as e:
                log.warning("[chunks:wiki] bad json %s: %s", f, e)
                continue

            ent = payload.get("__entity") or {}
            kind = ent.get("kind")        # 'models' | 'manufacturers'
            ent_id = ent.get("id")
            ent_name = ent.get("name")
            title = payload.get("title") or ent_name or ""
            extract = (payload.get("extract") or "").strip()
            infobox_text = _infobox_to_text(payload.get("infobox"))
            html_text = _strip_html(payload.get("html") or "")
            if max_html_chars and len(html_text) > max_html_chars:
                html_text = html_text[:max_html_chars] + " ..."

            parts: list[str] = []
            if title:
                parts.append(f"제목: {title}")
            if extract:
                parts.append(extract)
            if infobox_text:
                parts.append("[Infobox]\n" + infobox_text)
            if html_text:
                parts.append(html_text)
            text = "\n\n".join(parts).strip()
            if not text:
                continue

            # 메타 — kind 에 따라 manufacturer_id / model_id 만 채움 (variant 없음).
            mfr_id = ent_id if kind == "manufacturers" else None
            model_id = ent_id if kind == "models" else None
            uniq = f"wikipedia_auto::{f.parent.parent.name}::{kind}::{ent_id}"
            metadata = {
                "uniq": uniq,
                "title": title,
                "lang": payload.get("lang") or f.parent.parent.name,
                "kind": kind,
                "qid": ent.get("qid"),
                "revision_id": payload.get("revision_id"),
                "fullurl": (payload.get("raw_summary") or {}).get("fullurl"),
                "extract_len": len(extract),
            }
            try:
                _upsert_chunk(cur,
                    source="wikipedia_auto",
                    section="auto.wiki",
                    text=text,
                    metadata=metadata,
                    manufacturer_id=mfr_id,
                    model_id=model_id,
                    variant_id=None)
                n += 1
            except Exception as e:  # noqa: BLE001 — [chunks:wiki] %s 흡수 → n 반환
                log.warning("[chunks:wiki] %s: %s", uniq, e)
    conn.commit()
    log.info("[chunks:wiki] inserted/updated=%d", n)
    return n


def build_from_dart_narrative(*, context_chars: int = 600) -> int:
    """4 supplier OEM (현대모비스/한온/HL만도/현대위아) 의 DART 사업보고서
    III. 생산 및 설비 narrative → anxg_vec.chunks (source='dart_narrative').

    Hyundai/Kia 는 표 기반이라 dart_production_parser 가 자동 추출. 그 외 4 사 는
    narrative 본문에 capacity 가 적혀있어 LLM P3 추출이 필요.

    추출 전략:
        1. zip → main XML
        2. 정규식으로 '생산능력' / '가동률' / '생산실적' 키워드 주변
           ``context_chars`` (default 600) 만큼 컨텍스트 발췌
        3. XML 태그 strip, 공백 정규화
        4. (corp_code, rcept_no, match_idx) 단위로 anxg_vec.chunks 적재

    metadata:
        oem (mobis/hanon/mando/wia), corp_code, rcept_no, sequence_in_zip

    실측: 4 OEM × 16~17 zip × 3~7 matches = 200+ narrative chunks 기대.
    2026-06-01 신규.
    """
    import re
    import zipfile

    SUPPLIER_OEMS = {  # noqa: N806 — 지역 상수(매핑)
        "00164788": "mobis",     # 현대모비스
        "00161125": "hanon",     # 한온시스템
        "01042775": "mando",     # HL만도
        "00106623": "wia",       # 현대위아
    }
    KEYWORD_RE = re.compile(r"생산\s*능력|가동\s*률|생산\s*실적")  # noqa: N806 — 지역 정규식 상수
    XML_TAG_RE = re.compile(r"<[^>]+>")  # noqa: N806 — 지역 정규식 상수
    WS_RE = re.compile(r"\s+")  # noqa: N806 — 지역 정규식 상수

    bulk_root = get_settings().ingest_raw_dir / "dart_bulk" / "corp"
    if not bulk_root.exists():
        log.warning("[chunks:dart_narrative] %s 없음 — skip", bulk_root)
        return 0

    conn = get_connection()
    n = 0
    with conn.cursor() as cur:
        for cc, oem in SUPPLIER_OEMS.items():
            docs = bulk_root / cc / "documents"
            if not docs.exists():
                continue
            for z in sorted(docs.glob("*.zip")):
                rcept_no = z.stem
                try:
                    with zipfile.ZipFile(z) as zf:
                        xml_name: str | None = f"{rcept_no}.xml"
                        if xml_name not in zf.namelist():
                            xml_name = next(
                                (nm for nm in zf.namelist()
                                 if nm.endswith(".xml")
                                 and "_" not in Path(nm).stem),
                                None,
                            )
                        if not xml_name:
                            continue
                        xml = zf.read(xml_name).decode("utf-8",
                                                        errors="replace")
                except Exception as e:   # noqa: BLE001 — [build_chunks_auto] 1 unit 실패 흡수 → log + continue (부분 성공 보존)
                    log.warning("[chunks:dart_narrative] %s 손상: %s", z.name, e)
                    continue

                # 키워드 주변 컨텍스트 추출 — overlap 방지로 마지막 end 추적
                last_end = -1
                seq_in_zip = 0
                for m in KEYWORD_RE.finditer(xml):
                    if m.start() < last_end:
                        continue   # 이전 컨텍스트와 겹침
                    start = max(0, m.start() - 100)
                    end = min(len(xml), m.end() + context_chars)
                    last_end = end
                    raw_ctx = xml[start:end]
                    ctx = XML_TAG_RE.sub(" ", raw_ctx)
                    ctx = WS_RE.sub(" ", ctx).strip()
                    if len(ctx) < 150:
                        continue
                    seq_in_zip += 1
                    uniq = f"dart_narrative::{cc}::{rcept_no}::{seq_in_zip}"
                    try:
                        _upsert_chunk(
                            cur,
                            source="dart_narrative",
                            section="dart.생산설비",
                            text=ctx,
                            metadata={
                                "uniq": uniq,
                                "oem": oem,
                                "oem_corp_code": cc,
                                "rcept_no": rcept_no,
                                "sequence_in_zip": seq_in_zip,
                                "context_chars": context_chars,
                            },
                            manufacturer_id=None,
                            model_id=None,
                            variant_id=None,
                        )
                        n += 1
                    except Exception as e:   # noqa: BLE001 — [chunks:dart_narrative] %s 흡수 → n 반환
                        log.warning("[chunks:dart_narrative] %s: %s", uniq, e)
    conn.commit()
    log.info("[chunks:dart_narrative] inserted/updated=%d "
             "(4 supplier OEMs × DART zips)", n)
    return n


def build_from_oem_ir() -> int:
    """anxg_auto.events_oem_news.body_text → anxg_vec.chunks (source='oem_ir').

    OEM 별 corp_code 를 메타데이터에 동봉 — finance 측 검색과도 cross 가능.
    Body 가 비어있거나 SPA 한계로 너무 짧으면 skip (< 300 chars).

    2026-06-01 신규.
    """
    conn = get_connection()
    n = 0
    skipped_short = 0
    with conn.cursor() as cur:
        cur.execute("""
            SELECT news_id, oem, oem_corp_code, url, title, section,
                   body_text, published_date, source
              FROM anxg_auto.events_oem_news
             WHERE body_text IS NOT NULL AND length(body_text) >= 300
        """)
        rows = cur.fetchall()
        cur.execute("""
            SELECT count(*) FROM anxg_auto.events_oem_news
             WHERE body_text IS NULL OR length(coalesce(body_text,'')) < 300
        """)
        skipped_short = cur.fetchone()[0]
    with conn.cursor() as cur:
        for r in rows:
            (nid, oem, corp_code, url, title, section,
             body_text, pub_date, source_tag) = r
            try:
                _upsert_chunk(
                    cur,
                    source="oem_ir",
                    section=section or "ir/other",
                    text=body_text,
                    metadata={
                        "uniq": f"oem_ir::{oem}::{url}",
                        "oem": oem,
                        "oem_corp_code": corp_code,
                        "url": url,
                        "title": title,
                        "published_date": (pub_date.isoformat()
                                            if pub_date else None),
                        "ir_source_tag": source_tag,
                    },
                    manufacturer_id=None,
                    model_id=None,
                    variant_id=None,
                )
                n += 1
            except Exception as e:   # noqa: BLE001 — [chunks:oem_ir] %s 흡수 → n 반환
                log.warning("[chunks:oem_ir] %s: %s", url, e)
    conn.commit()
    log.info("[chunks:oem_ir] inserted/updated=%d skipped_too_short=%d",
             n, skipped_short)
    return n


def main() -> None:
    ap = argparse.ArgumentParser(prog="autograph.loaders.build_chunks_auto")
    ap.add_argument("--source",
                    choices=["recalls", "complaints", "wikipedia",
                              "oem_ir", "dart_narrative", "all"],
                    default="all")
    ap.add_argument("--log-level", default="INFO")
    args = ap.parse_args()
    logging.basicConfig(level=args.log_level,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")

    if args.source in ("recalls", "all"):
        build_from_recalls()
    if args.source in ("complaints", "all"):
        build_from_complaints()
    if args.source in ("wikipedia", "all"):
        build_from_wikipedia()
    if args.source in ("oem_ir", "all"):
        build_from_oem_ir()
    if args.source in ("dart_narrative", "all"):
        build_from_dart_narrative()


if __name__ == "__main__":
    main()

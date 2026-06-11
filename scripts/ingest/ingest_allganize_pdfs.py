"""Allganize 외부 벤치 원문 PDF → anxg_vec.chunks 적재 (외부 코퍼스 answerability).

`gold_qa_allganize_v0.jsonl`(외부 gold)은 자체 PDF 코퍼스 기반이라, 그 PDF 를 우리
vector store 에 적재해야 답변 실측이 된다. 본 로더는 디렉토리의 PDF 들을 추출·청크·임베딩해
`source='allganize'` 로 적재한다.

⚠️ **PDF 확보는 수동**: documents.csv 의 출처 URL 은 한국 정부·금융 사이트 랜딩페이지(직접
다운로드 불가, fsc.go.kr 차단)다. `--list` 로 받을 문서 목록을 출력하고, 사람이 다운로드해
`--pdf-dir` 에 넣은 뒤 `--apply` 한다.

사용:
  # 1) 받을 문서 목록 (documents.csv finance 10건)
  python3 scripts/ingest/ingest_allganize_pdfs.py --list
  # 2) PDF 를 data/external/allganize/finance_pdfs/ 에 수동 저장 후
  python3 scripts/ingest/ingest_allganize_pdfs.py --pdf-dir data/external/allganize/finance_pdfs --dry-run
  python3 scripts/ingest/ingest_allganize_pdfs.py --pdf-dir data/external/allganize/finance_pdfs --apply
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

_CHUNK_CHARS = 1200          # 페이지가 길면 ~1200자 윈도우로 분할
_DOMAIN = "finance"
_INSERT = """
INSERT INTO anxg_vec.chunks
  (corp_code, rcept_no, section, chunk_idx, text, token_count, metadata,
   source, fiscal_year, report_type, embedding)
VALUES (NULL, %(rcept_no)s, %(section)s, %(chunk_idx)s, %(text)s,
        %(token_count)s, %(metadata)s::jsonb, 'allganize', NULL,
        'allganize_external', %(embedding)s)
ON CONFLICT (rcept_no, chunk_idx) DO UPDATE SET
  text=EXCLUDED.text, section=EXCLUDED.section, metadata=EXCLUDED.metadata,
  embedding=EXCLUDED.embedding
"""


def _slug(name: str) -> str:
    return re.sub(r"[^0-9a-zA-Z가-힣]+", "-", Path(name).stem)[:60].strip("-")


def list_documents() -> list[dict]:
    """documents.csv 에서 finance 문서 목록(파일명·페이지·URL) 반환."""
    import csv

    from huggingface_hub import hf_hub_download
    p = hf_hub_download("allganize/RAG-Evaluation-Dataset-KO", "documents.csv",
                        repo_type="dataset")
    return [r for r in csv.DictReader(open(p, encoding="utf-8"))
            if (r.get("domain") or "").strip() == _DOMAIN]


def _extract_chunks(pdf_path: Path) -> list[tuple[str, str]]:
    """PDF → [(section, text)] (페이지 단위, 긴 페이지는 윈도우 분할)."""
    import pdfplumber
    out: list[tuple[str, str]] = []
    with pdfplumber.open(pdf_path) as pdf:
        for pno, page in enumerate(pdf.pages, 1):
            txt = (page.extract_text() or "").strip()
            if not txt:
                continue
            for i in range(0, len(txt), _CHUNK_CHARS):
                out.append((f"p{pno}", txt[i:i + _CHUNK_CHARS]))
    return out


def ingest(pdf_dir: Path, *, apply: bool) -> None:
    pdfs = sorted(pdf_dir.glob("*.pdf"))
    if not pdfs:
        print(f"[allganize] {pdf_dir} 에 PDF 없음 — --list 로 받을 문서 확인 후 수동 저장.")
        return
    client = conn = None
    if apply:
        from autonexusgraph.db.postgres import get_connection
        from autonexusgraph.embeddings import get_embedding_client
        client = get_embedding_client()
        conn = get_connection()

    total_chunks = 0
    for pdf in pdfs:
        chunks = _extract_chunks(pdf)
        rcept = f"alg-{_DOMAIN}-{_slug(pdf.name)}"
        print(f"  {pdf.name}: {len(chunks)} chunks (rcept={rcept})")
        total_chunks += len(chunks)
        if not apply:
            continue
        texts = [t for _, t in chunks]
        vecs = client.embed(texts)          # BGE-M3 1024-dim
        with conn.cursor() as cur:
            for idx, ((section, text), vec) in enumerate(zip(chunks, vecs, strict=True)):
                cur.execute(_INSERT, {
                    "rcept_no": rcept, "section": section, "chunk_idx": idx,
                    "text": text, "token_count": len(text.split()),
                    "metadata": json.dumps({"file_name": pdf.name, "domain": _DOMAIN,
                                            "benchmark": "allganize"}, ensure_ascii=False),
                    "embedding": vec,
                })
        conn.commit()
    print(f"[allganize] {'적재 완료' if apply else 'dry-run'} — PDF {len(pdfs)}, chunk {total_chunks}"
          + ("" if apply else " (변경 없음, --apply 로 적재)"))


def main() -> None:
    ap = argparse.ArgumentParser(description="Allganize PDF → vec.chunks 적재")
    ap.add_argument("--list", action="store_true", help="받을 finance 문서 목록 출력")
    ap.add_argument("--pdf-dir", type=Path, default=Path("data/external/allganize/finance_pdfs"))
    ap.add_argument("--apply", action="store_true", help="실제 임베딩+적재 (없으면 dry-run)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.list:
        docs = list_documents()
        print(f"# Allganize finance 원문 {len(docs)}건 — 수동 다운로드 대상 (→ {args.pdf_dir}/)")
        for d in docs:
            print(f"  - {d['file_name']}  (p{d.get('pages')})  {d.get('url')}")
        return
    ingest(args.pdf_dir, apply=args.apply and not args.dry_run)


if __name__ == "__main__":
    main()

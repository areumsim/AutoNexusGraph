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
# rcept_no NULL — Allganize 는 DART filing 이 아니라 filings FK 미적용(NULL 허용).
# 문서 식별은 metadata.doc_id/file_name. 멱등은 ingest() 의 source='allganize' 사전삭제.
_INSERT = """
INSERT INTO anxg_vec.chunks
  (corp_code, rcept_no, section, chunk_idx, text, token_count, metadata,
   source, fiscal_year, report_type, embedding)
VALUES (NULL, NULL, %(section)s, %(chunk_idx)s, %(text)s,
        %(token_count)s, %(metadata)s::jsonb, 'allganize', NULL,
        'allganize_external', %(embedding)s)
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


_OCR_MIN_CHARS = 100        # 페이지 추출 텍스트가 이보다 적으면 OCR fallback (이미지 스캔 PDF)
_MAX_PAGES = 60             # PDF 당 처리 상한 (거대 스캔 PDF 시간 바운드)
_ocr_reader = None


def _get_ocr_reader():
    """easyocr 한국어+영어 Reader (lazy, GPU). 미설치면 None."""
    global _ocr_reader
    if _ocr_reader is None:
        try:
            import easyocr
            _ocr_reader = easyocr.Reader(["ko", "en"], gpu=True)
        except Exception:   # noqa: BLE001 — OCR 엔진 부재/로드 실패 → OCR 생략(텍스트 PDF 만)
            _ocr_reader = False
    return _ocr_reader or None


def _reconstruct_layout(results: list) -> str:
    """easyocr detail=1 결과(bbox+text) → 행(y) 그룹화 + 열(x) 정렬로 표 구조 보존.

    paragraph=True 는 열을 가로질러 문단으로 뭉쳐 표를 파괴한다(주가·수치 질문에서
    셀-행 대응 상실). 대신 각 텍스트 박스의 y중심으로 같은 행을 묶고, 행 안에서 x좌측
    으로 정렬해 "셀 | 셀" 로 복원 → 표의 행·열 인접성이 청크에 보존된다.
    """
    boxes = []
    for box, text, *_conf in results:
        t = (text or "").strip()
        if not t:
            continue
        ys = [p[1] for p in box]
        xs = [p[0] for p in box]
        boxes.append((sum(ys) / len(ys), min(xs), max(ys) - min(ys), t))  # (y중심, x좌, 높이, 글자)
    if not boxes:
        return ""
    boxes.sort(key=lambda b: (b[0], b[1]))
    median_h = sorted(b[2] for b in boxes)[len(boxes) // 2] or 10
    row_thresh = median_h * 0.6                  # y중심 차이가 글자높이 60% 이내면 동일 행
    lines, cur = [], [boxes[0]]
    for b in boxes[1:]:
        cur_y = sum(x[0] for x in cur) / len(cur)
        if abs(b[0] - cur_y) <= row_thresh:
            cur.append(b)
        else:
            lines.append(cur)
            cur = [b]
    lines.append(cur)
    out = []
    for ln in lines:
        ln.sort(key=lambda b: b[1])              # 행 내 좌→우
        out.append(" | ".join(b[3] for b in ln) if len(ln) > 1 else ln[0][3])
    return "\n".join(out).strip()


def _ocr_page(fitz_doc, pno: int) -> str:
    """fitz 페이지 렌더(200dpi) → easyocr 한국어 OCR (행/열 레이아웃 재구성)."""
    import numpy as np
    reader = _get_ocr_reader()
    if reader is None:
        return ""
    pix = fitz_doc[pno].get_pixmap(dpi=200)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    if pix.n == 4:
        img = img[:, :, :3]
    return _reconstruct_layout(reader.readtext(img, detail=1, paragraph=False))


def _tables_text(page) -> str:
    """pdfplumber 로 텍스트층 PDF 의 표를 "셀 | 셀" 행으로 추출 (디지털 표 대응).

    extract_text() 는 표를 평탄화해 열 경계를 잃는다. extract_tables() 는 격자/공백
    기반 표를 행렬로 복원 → 수치 질문(ALG-FIN-006 등)에서 행·값 대응을 보존한다.
    """
    try:
        tables = page.extract_tables()
    except Exception:   # noqa: BLE001 — 표 탐지 실패(복잡 레이아웃) → 표 없음으로 취급
        return ""
    rows = []
    for tbl in tables or []:
        for row in tbl:
            cells = [(c or "").strip().replace("\n", " ") for c in row]
            if any(cells):
                rows.append(" | ".join(cells))
    return "\n".join(rows)


def _extract_chunks(pdf_path: Path) -> list[tuple[str, str]]:
    """PDF → [(section, text)]. 텍스트층 우선, 이미지 스캔 페이지는 OCR fallback."""
    import fitz
    import pdfplumber
    out: list[tuple[str, str]] = []
    fdoc = fitz.open(pdf_path)
    with pdfplumber.open(pdf_path) as pdf:
        for pno, page in enumerate(pdf.pages[:_MAX_PAGES], 1):
            txt = (page.extract_text() or "").strip()
            if len(txt) < _OCR_MIN_CHARS:           # 이미지 스캔 → OCR (행/열 재구성)
                ocr = _ocr_page(fdoc, pno - 1)
                if len(ocr) > len(txt):
                    txt = ocr
            tbl_txt = _tables_text(page)            # 텍스트층 디지털 표 → 구조 보존 추가
            if tbl_txt:
                txt = f"{txt}\n\n[표]\n{tbl_txt}".strip()
            if not txt:
                continue
            for i in range(0, len(txt), _CHUNK_CHARS):
                out.append((f"p{pno}", txt[i:i + _CHUNK_CHARS]))
    fdoc.close()
    return out


def ingest(pdf_dir: Path, *, apply: bool) -> None:
    pdfs = sorted(pdf_dir.glob("*.pdf"))
    if not pdfs:
        print(f"[allganize] {pdf_dir} 에 PDF 없음 — --list 로 받을 문서 확인 후 수동 저장.")
        return
    import hashlib
    client = conn = None
    if apply:
        from autonexusgraph.db.postgres import get_connection
        from autonexusgraph.embeddings import get_embedding_client
        client = get_embedding_client()
        conn = get_connection()
        with conn.cursor() as cur:        # 멱등 — 기존 allganize chunk 제거 후 재적재
            cur.execute("DELETE FROM anxg_vec.chunks WHERE source = 'allganize'")
        conn.commit()

    total_chunks = 0
    gidx = 0                              # 전역 chunk_idx (rcept_no NULL 이라 문서 간 충돌 무관)
    for pdf in pdfs:
        chunks = _extract_chunks(pdf)
        doc_id = "ALG" + hashlib.md5(pdf.name.encode()).hexdigest()[:11]
        print(f"  {pdf.name}: {len(chunks)} chunks (doc_id={doc_id})")
        total_chunks += len(chunks)
        if not apply:
            continue
        texts = [t for _, t in chunks]
        vecs = client.embed(texts)          # BGE-M3 1024-dim
        with conn.cursor() as cur:
            for (section, text), vec in zip(chunks, vecs, strict=True):
                cur.execute(_INSERT, {
                    "section": section, "chunk_idx": gidx,
                    "text": text, "token_count": len(text.split()),
                    "metadata": json.dumps({"doc_id": doc_id, "file_name": pdf.name,
                                            "domain": _DOMAIN, "benchmark": "allganize"},
                                           ensure_ascii=False),
                    "embedding": vec,
                })
                gidx += 1
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

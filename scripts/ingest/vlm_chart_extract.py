"""차트/그래프 수치 VLM 추출 — Allganize 차트-수치 질문 대응 (보고서 §4.2 #1).

easyocr 은 시각 차트(막대/선)·스타일 표의 수치를 텍스트로 복원하지 못한다(ALG-FIN-006
등 judge 0.0). 해당 차트 페이지를 Claude vision(VLM)으로 읽어 수치를 구조화 텍스트로
추출하고 **사이드카 JSON**(`vlm_charts/<stem>.json` = {page_idx: text})으로 저장한다.

사이드카는 작은 텍스트(추출 수치)라 커밋 가능 → 적재 파이프라인(`ingest_allganize_pdfs.py`)이
이를 읽어 `[차트]` 청크로 합류한다. VLM 은 오프라인 1회만 실행(비용·재현 분리), footgun 없음.

사용:
  env -u ANTHROPIC_API_KEY ... python3 scripts/ingest/vlm_chart_extract.py [--apply]
"""
from __future__ import annotations

import argparse
import base64
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

PDF_DIR = Path("data/external/allganize/finance_pdfs")
OUT_DIR = Path("data/external/allganize/vlm_charts")
_MODEL = "claude-sonnet-4-6"

# 차트-수치 질문이 가리키는 페이지(0-indexed). target_page_no(HF) + 2-slide/page 오프셋 보정.
TARGETS: dict[str, list[int]] = {
    # 증시콘서트(2슬라이드/page): KOSPI 성과·테마·채권·S&P 등 — ALG-FIN-006/007/009/010
    "kofia__2019_제1회_증시콘서트_자료집_최종_.pdf": [6, 7, 8, 9, 10],
    # KIF 일본 고령화(1슬라이드/page) — ALG-FIN-014/016
    "kif_KIFVIP2013-10_55p.pdf": [19, 20, 21, 36, 37, 38],
    # FSC 상생금융 보도자료 표 — ALG-FIN-045/046
    "fsc_sangsaeng_0_7p.pdf": [3, 4, 5],
    # FSC 핀테크 혁신펀드 보도자료 표 — ALG-FIN-050
    "fsc_fintech_0_6p.pdf": [1, 2, 3, 4],
}

_PROMPT = (
    "이 페이지의 모든 표·차트·그래프의 수치를 한국어로 빠짐없이 구조화해 추출하라. "
    "각 표/차트는 제목과 함께 '항목: 값' 또는 '행 | 값' 형식으로. 막대/선 그래프의 수치 "
    "라벨, 표의 모든 셀 값을 포함하라. 설명 문장 없이 데이터만. 수치가 없으면 '(수치 없음)'."
)


def _vision_extract(client, png_bytes: bytes) -> str:
    b64 = base64.b64encode(png_bytes).decode()
    msg = client.messages.create(
        model=_MODEL, max_tokens=2000,
        messages=[{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64",
                                         "media_type": "image/png", "data": b64}},
            {"type": "text", "text": _PROMPT},
        ]}],
    )
    return msg.content[0].text.strip()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="실제 VLM 호출+사이드카 저장")
    ap.add_argument("--dpi", type=int, default=200)
    args = ap.parse_args()

    import fitz
    if args.apply:
        import anthropic

        from autonexusgraph.config import get_settings
        client = anthropic.Anthropic(api_key=get_settings().anthropic_api_key)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    for pdf_name, pages in TARGETS.items():
        pdf = PDF_DIR / pdf_name
        if not pdf.exists():
            print(f"  [skip] {pdf_name} 없음")
            continue
        doc = fitz.open(pdf)
        sidecar: dict[str, str] = {}
        for idx in pages:
            if idx >= doc.page_count:
                continue
            if not args.apply:
                print(f"  [dry] {pdf_name} p{idx + 1}")
                continue
            pix = doc[idx].get_pixmap(dpi=args.dpi)
            text = _vision_extract(client, pix.tobytes("png"))
            sidecar[str(idx)] = text
            print(f"  {pdf_name} p{idx + 1}: {len(text)} chars", flush=True)
        doc.close()
        if args.apply and sidecar:
            out = OUT_DIR / f"{pdf.stem}.json"
            out.write_text(json.dumps(sidecar, ensure_ascii=False, indent=1))
            print(f"  → {out}")
    print(f"[vlm-charts] {'완료' if args.apply else 'dry-run'} — {len(TARGETS)} PDF")


if __name__ == "__main__":
    main()

# Allganize KIF 원문 2건 — 프로비넌스 (바이너리 미커밋)

KIF(한국금융연구원) 연구논문 2건은 **제3자 저작물**이라, PUBLIC repo·저작권 정책상
원본 바이너리(PDF·페이지이미지 ~71MB)는 git 에 커밋하지 않는다. 본 디렉토리의
`manifest.json` 으로 **재취득·검증**한다. (repo 의 `data/` 데이터-제외 관례와 정합.)

대상: `KIFVIP2013-10`(일본 고령화·연금, 55p), `WP22-05`(KIF working paper, 69p).

## 왜 페이지이미지 OCR 인가

`vwserver.kif.re.kr/flexer/viewer.jsp` 레거시 뷰어가 **원본 PDF 를 노출하지 않고**
페이지이미지(PNG)로 변환해 서빙한다. 그래서 원본 PDF 직접 다운로드가 불가하고,
뷰어 JS 를 역설계해 페이지이미지를 전수 취득한 뒤 OCR 한다.

## 재취득 절차

1. **페이지수 확인** — `…/pdf.txt` (plaintext): KIFVIP2013-10=55, WP22-05=69.
2. **페이지이미지 다운로드** — `manifest.json` 의 `image_base` + `00001.png`~`000NN.png`
   (5자리 zero-pad). `Referer: https://vwserver.kif.re.kr/flexer/` 헤더 필요.
3. **무손실 PDF 조립** — `fitz` 로 페이지 크기를 `px×72/200` pt 로 설정(→ `get_pixmap(dpi=200)`
   시 native 해상도 보존) 후 `finance_pdfs/kif_*.pdf` 로 저장.
4. **검증** — 조립 PDF 의 `sha256` 을 `manifest.json` 의 `assembled_pdf_sha256` 과 대조.
5. **적재** — `CUDA_VISIBLE_DEVICES=1 … ingest_allganize_pdfs.py --apply` (§2.6 GPU 함정 주의).

상세 방법론·eval 결과: `docs/operations/allganize_external_benchmark_report.md` §2.6 / §3.5.

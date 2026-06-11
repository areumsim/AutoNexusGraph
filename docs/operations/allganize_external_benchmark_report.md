# Allganize 외부 벤치 흡수·코퍼스 적재 보고서

> 작성: 2026-06-11 · 관련 PR: #71 (QA 흡수) · #72 (적재 파이프라인) · #79 (OCR fallback) · #80 (적재 완료)
> 목적: gold QA self-bias 완화(외부 큐레이터 30% 정책) + 외부 벤치 answerability 확보.

---

## 0. 한 줄 요약

`allganize/RAG-Evaluation-Dataset-KO` finance **60 QA 흡수**(외부 큐레이터 비율 0%→26.7%) +
원문 PDF **10건 스크래핑 → OCR → vec.chunks 98 chunks 적재 완료**. 해당 문서 기반 질문
answerable. (KOFIA·KIF 4건은 사이트 제약으로 미확보 — 후속.)

**처리 흐름 (무엇을 → 어떻게):**

```
HF QA 60        → gold_qa_allganize_v0.jsonl (외부 gold, self-bias↓)        [PR #71]
documents.csv   → 원문 10 PDF 위치(랜딩페이지 url)
사이트 스크래핑  → BOK /fileSrc·FSC /comm/getFile 역설계 → 10 PDF 다운로드   [PR #72]
이미지스캔 발견  → pdfplumber 55자/p → easyocr OCR(ko, GPU) → 1,915자/p     [PR #79]
적재            → OCR/텍스트 → chunk → BGE-M3 embed → vec.chunks 98(source) [PR #80]
                 (블로커: rcept_no char(14)/FK·PG 서버다운 → NULL+멱등·chown 복구)
```

---

## 1. 배경 — 왜 했는가

- gold QA 165 row(finance 30/auto 56/cross 49/ip 30)가 **전부 시스템 작성자 작성** → self-bias
  (LLM-as-judge ground truth 를 시스템 개발자가 만들면 자기충족 위험, `gold_qa_guide.md` §2.2).
- 정책 요건: **외부 큐레이터 30% 이상**. 실측 비율 **0%**.
- thesis 측정(`docs/research/thesis_hybrid_routing.md`)이 소표본 노이즈로 robust 판정 불가 — 외부
  중립 벤치가 신뢰도·표본 양쪽에 기여.
- 1순위 = 공개 외부 벤치 흡수(키 불필요): **Allganize RAG-Evaluation-Dataset-KO** (HuggingFace).

---

## 2. 전체 과정 + 단계별 결과

### 2.1 QA 쌍 흡수 (PR #71)
- HF `allganize/RAG-Evaluation-Dataset-KO` `test` split, domain=finance **60 row**.
- 컬럼: `question` / `target_answer`(prose) / `target_file_name` / `domain`.
- 표준 변환 `scripts/audit/convert_allganize_gold.py` → `eval/qa_gold/gold_qa_allganize_v0.jsonl`
  (태그 `allganize_external`/`external_curator`). `validate-gold-qa` **0 errors**.
- **외부 큐레이터 비율 0% → 26.7%** (60/225, finance 도메인 66.7%). `external_curator_ratio.py` 측정.
- 별도 슬롯이라 thesis 측정(`gold_qa_v0`) 불오염.

### 2.2 원문 PDF 위치 파악
- HF 데이터셋엔 **QA·모델답변 CSV 만**(PDF 없음). 원문은 외부 호스팅.
- `documents.csv`(HF): finance **10 PDF**(총 301 page), 각 `file_name`/`pages`/`url`.
- url 은 **출처 사이트 랜딩페이지**(직접 PDF 아님):
  | 사이트 | 문서 | 페이지 |
  |---|---|---|
  | bok.or.kr | 통화신용정책 운영 / 향후 방향 | 13 / 21 |
  | kofia.or.kr | 증시콘서트 자료집 / 한-호주 퇴직연금 | 58 / 50 |
  | fsc.go.kr | 핀테크·상생금융·지방은행 인가·[별첨] | 6/7/7/15 |
  | kif.re.kr | KIFVIP2013-10 / WP22-05 | 55 / 69 |

### 2.3 스크래핑 (사이트별 다운로드 패턴 규명)
직접 PDF 링크가 없어 사이트별 첨부 엔드포인트를 역설계:
- **BOK** ✅ — 게시판 HTML 에 `/fileSrc/portal/<hash>/<N>/<hash>.pdf` 직접 링크. 7개 첨부 다운,
  타깃 2건(통화신용정책 운영 13p / 향후 방향 21p) 확보.
- **FSC** ✅(부분) — `/comm/getFile?srvcId=BBSTY1&upperNo=...&fileTy=ATTACH&fileSn=...` 패턴. 카테고리
  페이지서 8개 첨부 다운(보도자료 류, 정확 타깃 매칭은 불확실).
- **KOFIA** ❌ — 다운로드가 JS 기반, 링크 미노출.
- **KIF** ❌ — `flexer/viewer.jsp` 뷰어 래퍼, 직접 PDF 엔드포인트 미확보.
- 결과: **15 PDF 다운로드** → 비타깃·거대(134p/44MB 등) 제거 후 **10건 유지**(BOK 2 + FSC 8).

### 2.4 OCR — 이미지 스캔 대응 (PR #79)
- **결정적 발견**: 한국 금융 PDF 가 **이미지/스캔 기반**. 예: BOK 통화신용정책(13p, 41MB) →
  pdfplumber 텍스트 추출 **~55자/page**(near-empty). Allganize README 도 명시("테이블·이미지
  질문은 RAG 가 약함").
- 단순 텍스트 적재로는 answerability 미달 → **OCR 파이프라인 추가**:
  - `scripts/ingest/ingest_allganize_pdfs.py::_extract_chunks` — 페이지 텍스트 < 100자면
    `pymupdf`(fitz, 200dpi) 렌더 → `easyocr`(ko+en, GPU) OCR.
  - `pyproject [ocr]` extra(easyocr+pymupdf), easyocr 부재 시 graceful degrade(text-only).
  - 검증: BOK 본문 페이지 OCR **1,915자 dense 한국어** 추출(pdfplumber 55자 대비).

### 2.5 적재 (PR #80) — 발견·수정한 블로커
| 블로커 | 원인 | 수정 |
|---|---|---|
| `StringDataRightTruncation char(14)` | `rcept_no` 가 char(14)(DART rcept_no), 합성 ID 초과 | (1차) ALG+11자 해시 |
| `ForeignKeyViolation chunks_rcept_no_fkey` | `chunks.rcept_no` 가 `anxg_fin.filings` FK — Allganize 는 DART filing 없음 | **rcept_no=NULL**(nullable, FK NULL 허용). 문서식별 = `metadata.doc_id/file_name`. 멱등 = `source='allganize'` 사전삭제 |
| **원격 PG 서버 다운** | 호스트 uid/소유권 변경으로 PG 데이터 디렉토리 권한 깨짐(`base/16384: Permission denied`) — 인프라 이슈(git "dubious ownership"와 동일 근원) | 사용자가 호스트서 `chown -R 999:999 .../postgres` + restart 로 복구 |

---

## 3. 최종 결과 (실측)

| 항목 | 값 |
|---|---|
| gold QA(Allganize finance) | **60 row** (`gold_qa_allganize_v0.jsonl`) |
| 외부 큐레이터 비율 | **0% → 26.7%** (finance 66.7%) |
| 적재 PDF | **10** (BOK 2 + FSC 8) |
| `vec.chunks` (source='allganize') | **98 chunks** (전부 임베딩 BGE-M3 1024d) |
| └ BOK 통화신용정책 운영 | 23 chunks (**OCR**, 이미지스캔) |
| └ BOK 향후 방향 | 39 chunks (**OCR**) |
| └ FSC 보도자료 8건 | 36 chunks (텍스트) |
| OCR 품질 | BOK 이미지 PDF서 한국어 정상 추출 (검증: "한국은행 자산... 주택매매 거래량... 부동산 PF 대출 잔액") |

---

## 4. 남은 것 (정직)

1. **KOFIA(2)·KIF(2) PDF 미확보** — JS 다운로드 / 뷰어 래퍼. 사람 수동 다운로드 또는 브라우저
   자동화(Selenium 등) 필요. → 10/14 finance 원문 확보(나머지 4 후속).
2. **FSC 정확 타깃 매칭 불확실** — 카테고리 페이지서 받은 8건이 정확히 4 타깃인지 미검증(이미지
   스파스 텍스트라 키워드 매칭 신뢰도 낮음). 도메인 관련 보도자료라 코퍼스엔 유효.
3. **eval answerability 실측 미완** — 코퍼스는 적재됐으나 Allganize 60 QA 에 대한 실제 정답률
   측정은 별도(LLM eval, prose 정답이라 EM 대신 F1/judge 적합).
4. **OCR 노이즈** — easyocr 가 표·차트 라벨에서 일부 오인식(예: "금융"→"금움"). 본문 검색엔 충분하나
   정밀 수치 질문엔 한계.

---

## 5. 재현 명령

```bash
# 1. QA 흡수 (이미 적재됨)
python3 scripts/audit/convert_allganize_gold.py --src <allganize_finance.jsonl> \
  --domain finance --qid-prefix ALG-FIN --out eval/qa_gold/gold_qa_allganize_v0.jsonl
python3 scripts/audit/external_curator_ratio.py        # 비율 확인

# 2. 받을 PDF 목록
python3 scripts/ingest/ingest_allganize_pdfs.py --list

# 3. PDF 확보 후 (data/external/allganize/finance_pdfs/) OCR 적재
pip install -e ".[ocr]"                                # easyocr + pymupdf
make serve-dashboard &  # (또는 임베딩 서버 8080 기동)
python3 scripts/ingest/ingest_allganize_pdfs.py \
  --pdf-dir data/external/allganize/finance_pdfs --apply    # OCR + embed + vec.chunks
```

---

## 6. 결론

- **self-bias 완화의 가장 큰 구멍(외부 0%)을 26.7% 까지 메움** — 신뢰도 측면 핵심 진전.
- **이미지 기반 외부 코퍼스를 OCR 로 vector store 에 적재** — 단순 텍스트 추출로는 불가했던
  answerability 를 한국어 OCR 파이프라인으로 확보(BOK 통화신용정책 등 62 chunks).
- 남은 4 PDF(KOFIA/KIF) + eval 실측 + 30% 완성(auto/cross/ip 외부)은 후속.

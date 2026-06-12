# Allganize 외부 벤치 흡수·코퍼스 적재 보고서

> 작성: 2026-06-11 · 관련 PR: #71 (QA 흡수) · #72 (적재 파이프라인) · #79 (OCR fallback) · #80 (적재 완료) · #84 (vector source 필터) · (b·재적재) OCR 표 재구성 + 정확 9건 재적재
> 목적: gold QA self-bias 완화(외부 큐레이터 30% 정책) + 외부 벤치 answerability 확보.

---

## 0. 한 줄 요약

`allganize/RAG-Evaluation-Dataset-KO` finance **60 QA 흡수**(외부 큐레이터 비율 0%→26.7%) +
원문 PDF **정확 9건 확보(selenium 포함) → OCR(표 행/열 재구성) → vec.chunks 418 chunks 적재 완료**. 해당 문서 기반 질문
answerable. (KIF 2건만 레거시 Flash 뷰어로 미확보 — 후속.)

> **갱신(2026-06-11 b)**: 초기 FSC 8건이 2026 오답으로 판명 → WebSearch 로 2024 정확 타깃 재확보(9건).
> OCR 을 `paragraph=True`(표 뭉갬) → `detail=1` bbox 행(y)그룹화 + 열(x)정렬 "셀 \| 셀" 재구성 + `pdfplumber.extract_tables()` 로 교체.
> 재적재 374→**418 chunks**(표 마커 `[표]` 47청크). **vector F1 0.369→0.442 (+7.3pp)**, **hybrid 0.120→0.282 (+16.2pp, source 필터를 agent 경로에도 부여)**.

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
- **KOFIA** ✅(selenium) — `down.do?brd_id=www_default&seq=<N>&data_tp=A&file_seq=1` (selenium 으로 view 페이지 세션 쿠키 획득 후 다운). 증시콘서트 58p·퇴직연금 50p 확보.
- **KIF** ❌ — `flexer/viewer.jsp` 레거시 Flash 뷰어, cid stale("Request Error") + 헤드리스 PDF 미로드. 미확보.
- 결과: **17 PDF 다운로드**(BOK 7 + FSC 8 + KOFIA 2) → 비타깃·거대 제거 후 **12건 유지**(BOK 2 + FSC 8 + KOFIA 2).

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
| 적재 PDF | **정확 9건** (BOK 2 + FSC 5 + KOFIA 2; 초기 8 FSC = 2026 오답 → 2024 타깃 재확보) |
| `vec.chunks` (source='allganize') | **418 chunks** (전부 임베딩 BGE-M3 1024d, 표 마커 `[표]` 47청크) |
| └ BOK 통화신용정책 운영(bok_3) | 23 chunks (**OCR**, 이미지스캔) |
| └ BOK 향후 방향(bok_4) | 40 chunks (**OCR**) |
| └ FSC 지방은행 전환(별첨 포함) | 7 + 17 chunks |
| └ FSC 상생금융 / 핀테크 2건 | 9 + 7 + 7 chunks |
| └ KOFIA 증시콘서트 / 한-호주 퇴직연금 | 257 / 51 chunks (**OCR**, selenium 확보) |
| OCR 품질 | BOK 이미지 PDF서 한국어 정상 추출. 표지·표 페이지는 행(y)그룹화 + 열(x)정렬로 "셀 \| 셀" 복원(예: `지방은행의 \| 시중은행 \| 전환시`) |

---

## 3.5. eval 실측 (2026-06-11, KIF 18문항 제외 → 42문항)

`run_qa_eval --gold gold_qa_allganize_noKIF.jsonl --adapters vector,hybrid`. 프로즈 정답이라
**F1(토큰 overlap)** 이 지표(EM 은 0 — 산문 정답에 exact-match 불가).

| 어댑터 | F1 | EM | faith | cost | 비고 |
|---|---|---|---|---|---|
| vector (전체 코퍼스) | 0.271 | 0.000 | 0.503 | $0.28 | 초기(374 chunk, 희석) |
| vector (source 필터) | 0.369 | 0.048 | 0.497 | $0.29 | 초기(374 chunk, 2026 오답 FSC) |
| hybrid (source 미적용) | 0.120 | 0.000 | 0.000 | $0.34 | 초기 |
| **vector (source 필터, b)** | **0.442** | 0.048 | 0.631 | $0.30 | **정확 9건 + 표 OCR** |
| **hybrid (source 필터, b)** | **0.282** | 0.024 | 0.000 | $0.29 | **agent 경로 source 필터 신규** |

> **(b) 갱신 — 정확 9건 재적재 + OCR 표 재구성 + hybrid source 필터:**
> - **vector 0.369 → 0.442 (+7.3pp, +20% 상대)**: 초기 8 FSC 가 2026 오답이었음을 발견 → 2024 정확
>   타깃 9건 재확보 + OCR `paragraph=True`(표 뭉갬)를 `detail=1` 행/열 재구성으로 교체. 정확한 출처
>   문서 + 표 보존이 답변 overlap 을 끌어올림.
> - **hybrid 0.120 → 0.282 (+16.2pp, 2.3배)**: source 필터를 vector 뿐 아니라 **agent 경로에도** 부여
>   (`run_agent(source=)` → `research_worker` → `search_documents(source=)`, rerank 와 동일 주입 패턴).
>   메인 DART 코퍼스 희석이 제거돼 doc-RAG 질문에서도 의미 있게 상승.
> - **vector > hybrid 여전(0.442 > 0.282)**: 회사·그래프 없는 단일 문서 질문엔 multi-hop agent 라우팅이
>   과잉 — 단순 vector retrieval 이 적합. hybrid faith 0.000 은 agent citation 경로가 외부 코퍼스에
>   evidence_text 를 채우지 않아 구조적(점수 미산정)이며 정답 부재 의미는 아님.
> - 명령: `EVAL_VECTOR_SOURCE=allganize` (vector·hybrid 어댑터 공통 적용).

- **answerability 확인**: vector 가 allganize 코퍼스를 retrieval 해 답함(예: ALG-FIN-002 "은행법…
  금융감독위원회 인가" = 적재한 은행 문서 내용 사용). 코퍼스가 실제로 쓰인다.
- **F1 0.442 의 한계(정직)**: ① easyocr 잔여 오인식(스캔 표 라벨) ② 코퍼스 9건 외 질문은 출처 문서
  부재 시 "정보 없음" ③ F1 은 LLM-judge 보다 과소평가(Allganize 리더보드는 judge 기준 0.6~0.85). 즉
  0.442 는 **하한** — 코퍼스 유효성·source 필터·표 OCR 효과는 입증, 정밀도는 위 요인으로 제한.

---

## 4. 남은 것 (정직)

1. **KIF(2) PDF 미확보** — 레거시 Flash 뷰어(`flexer`)가 PDF 를 페이지이미지로만 서빙(원본 비노출).
   정확 URL param = `cno/fk/ftype=pdf`. 확보하려면 124 페이지이미지 OCR(큰 우회) → 보류. noKIF 42문항으로 측정.
2. ~~**FSC 정확 타깃 매칭 불확실**~~ — **(b) 해소**: 초기 8건이 2026 오답임을 발견 → WebSearch 로 2024
   정확 타깃(지방은행 전환+별첨·상생금융·핀테크) 재확보. 9건 모두 의도 문서와 일치.
3. ~~**eval answerability 실측 미완**~~ — **해소**: §3.5 에 vector F1 0.442 / hybrid 0.282 (noKIF 42문항) 실측.
4. **OCR 잔여 노이즈** — (b) 에서 표는 행/열 재구성으로 구조 보존(`[표]` 47청크). 다만 easyocr 가 스캔
   표·차트 라벨 일부 오인식(예: "금융"→"금움")은 잔존 — 정밀 수치 질문엔 여전히 한계.

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

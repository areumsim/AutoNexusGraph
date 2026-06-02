---
name: 데이터 소스 제안 (Data source)
about: 새 외부 데이터 소스 적재 제안 (적합성 판정 포함)
title: "[data] "
labels: data-source
---

## 소스
- 이름 / 제공처:
- URL / API / 데이터셋 ID:
- 인증: 키 불필요 / `*_API_KEY` 필요 (어떤 키) / 수동 다운로드(CSV 등)

## 적합성 (GraphRAG 3-store 적재 가능?)
<!-- 이미지 CV 학습 파이프라인 아님 — Neo4j 관계 / PG 수치·메타 / pgvector 텍스트 중 무엇에 들어가나 -->
- 대상 스키마·테이블 (`fin.* / auto.* / ip.* / master.* / bridge.*`):
- 매핑 단위: 회사귀속 / 회사무관(taxonomy) / cross bridge

## 출처 등급 (confidence)
- A(0.95, 공식·1차) / B(0.80, 보강) / C(0.50, 합성·후보) — 어느 등급, 근거:
- 회사귀속 엣지면 `PERFORMED_AT` source allowlist hard-check 통과 가능? (A/B만)

## 라이선스
- 재배포/저장 허용 여부 → `ingestion/_license.py::LICENSE_POLICY` 등급:

## 체크
- [ ] 키 부재 시 graceful skip + 멱등 적재 가능
- [ ] 새 소스 → `LICENSE_POLICY` 등록 (`tests/test_license.py` invariant)
- [ ] 7키 엣지 메타 충족 (관계 적재 시)

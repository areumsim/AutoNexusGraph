---
name: 버그 리포트 (Bug report)
about: 재현 가능한 결함 — 잘못된 답변 / 적재 오류 / 크래시 등
title: "[bug] "
labels: bug
---

## 요약
<!-- 한 줄로 무엇이 잘못됐는지 -->

## 재현 절차
1.
2.
3.

## 기대 동작 / 실제 동작
- 기대:
- 실제:

## 환경
- 도메인: finance / auto / ip / cross_domain
- 실행 경로: API(`/chat`) / Streamlit / `make <target>` / 스크립트
- LLM provider·model (해당 시):
- DB 상태: `make health` 결과 (PG/Neo4j ok?)

## 로그 / 출력
<!-- 에러 메시지, trace, cost_log 등. ⚠️ 실제 API 키·시크릿·PII 는 마스킹 -->
```
```

## 체크
- [ ] `make smoke-e2e` 재현 시도함 (mock 게이트)
- [ ] 시크릿/PII 미포함 확인

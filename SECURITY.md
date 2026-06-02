# 보안 정책 (SECURITY)

> **라이선스**: Proprietary. 공개 CVE 프로세스 없음 — **비공개 책임 보고**.

## 취약점 보고

취약점을 발견하면 **공개 이슈로 올리지 말고** 비공개로 보고해 주세요:

1. GitHub **private security advisory** (저장소 → Security → Advisories → Report a vulnerability), 또는
2. 저장소 관리자(maintainer)에게 직접 연락.

보고 시 포함: 재현 절차, 영향 범위, (가능하면) PoC. **보고서에 실제 시크릿·PII·운영 데이터를 붙이지 마세요** — 마스킹/합성값으로.

지원 대상: `main` 브랜치 (현행). 대응은 비공개로 수정 → 패치 후 공유.

---

## 구현된 보안 통제

| 영역 | 통제 | 위치 |
|---|---|---|
| API 인증 | API key 헤더(`X-API-Key`/`Bearer`) + `API_KEYS` env + **thread_id↔user_id 바인딩**(타인 히스토리 403) | `api/auth.py` (O-1) |
| Rate limit | per-identity in-memory sliding-window (`API_RATE_LIMIT_PER_MIN`) | `api/auth.py` |
| Cypher 안전 | READ-ONLY 강제 + APOC write/dynamic-cypher 차단, 템플릿↔파라미터 일치 검증 | `safety/cypher_guard.py` |
| 프롬프트 안전 | high-risk 단발 차단 + low-risk telemetry (단일 rule SSOT) | `safety/prompt_safety.py` |
| 수치 환각 | pre-synth 마스킹 + post-synth validator 검증 | number_guard |
| 시크릿 | `.env.*` gitignore (`!.env.example`만 추적). prod DB 비밀번호 env 필수 주입 | `.gitignore`, `docker-compose.prod.yml` (O-2) |
| 데이터 라이선스 | source 별 라이선스 정책 + invariant test | `ingestion/_license.py`, `tests/test_license.py` |

배포 시 보안 절차(reverse proxy + TLS + DB 포트 미노출 + 시크릿 분리): [docs/operations/production_deploy.md](./docs/operations/production_deploy.md).

---

## 알려진 한계 (정직 표기 — 외부 노출 전 반드시 조치)

- **`API_KEYS` 미설정 시 open 모드** — 모든 요청 `anonymous` 허용 (dev/내부망 편의). 외부 노출 환경은 반드시 `API_KEYS` 설정 (1회 경고 로그 발생).
- **Rate limit 은 in-memory / 프로세스-local** — 멀티 worker·인스턴스에서 실질 한도가 ×N. 하드 글로벌 한도는 reverse proxy / redis 필요 ([§12.3](./README.md), BACKLOG O-3/O-5).
- **PII** — `master.persons`(이름·생년) 의 GDPR-style 삭제권/로그 redaction 정책 미정 (BACKLOG O-6).
- **TLS / secrets 분리** — dev 는 http + `.env` 단일. prod 는 reverse proxy TLS + vault/k8s secret (O-6).
- **LLM 비용** — 세션 hard limit (`LLM_COST_HARD_LIMIT_USD`) 은 프로세스 누적. 글로벌 통제는 provider 측 한도 병행.

---

**관련**: [CONTRIBUTING.md](./CONTRIBUTING.md) · [README §12.2](./README.md) · [BACKLOG.md](./BACKLOG.md) §5 (O-1/O-3/O-5/O-6)

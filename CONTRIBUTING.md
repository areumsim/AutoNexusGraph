# 기여 가이드 (CONTRIBUTING)

> **라이선스**: Proprietary (`pyproject.toml`). 본 문서는 **내부 기여자** 대상 — 개발 환경·게이트·코드 규약·PR 절차. 외부 공개 기여 프로세스 아님.
>
> 설계·요구사항 SSOT 는 [README](./README.md), 미완료 항목은 [BACKLOG.md](./BACKLOG.md).

---

## 1. 개발 환경

```bash
# 의존성 (모든 extras)
pip install -e ".[all]"

# DB 스택 (PG + Neo4j) — dev
docker compose up -d           # 상세: docs/operations/docker_setup.md

# .env 작성 (.env.example 복사 후 키 채움) — 5분 진입: docs/quickstart.md
```

Python ≥ 3.10 (CI 는 3.10 / 3.11 / 3.12 matrix). ruff target / mypy 는 3.11.

---

## 2. 푸시 전 게이트 (필수)

```bash
make smoke-e2e
```

DB·LLM·키 없이 도는 **mock 정합성 일괄 검증** — `pytest` + `audit-ontology`(cypher↔yaml cross-check) + `audit-eval-matrix`(simulation) + `audit-mcp` + `audit-ipgraph` + `audit-trace`(simulation) + `validate-gold-qa`. **이게 통과해야 푸시.** 동일 게이트를 CI(`.github/workflows/ci.yml`, O-4)가 PR/푸시마다 재실행한다.

> `make lint`(ruff)·`mypy` 는 아직 저장소가 clean 하지 않아 **informational** (CI 비차단). 새/수정 코드는 가능한 한 깨끗하게 — 단, 주변 코드의 관용(idiom)에 맞춰라 (예: `tools/_db.py` 패턴).

---

## 3. 코드 규약 (도메인 불변식)

1. **자유 SQL / Cypher 금지.** 사전 정의 tool pool + cypher 템플릿만 사용 (type/range/regex 검증). 새 질의가 필요하면 템플릿/도구를 추가.
2. **모든 관계 엣지는 7키 메타 의무**: `source_type` / `source_id` / `confidence_score` / `validated_status` / `snapshot_year` / `extraction_method` / `schema_version`. (`make audit-edge-meta --strict`로 검증, README §3.7.)
3. **출처 신뢰도 등급**: A=0.95 / B=0.80 / C=0.50 기본 confidence (README §4.0).
4. **키 부재 시 graceful skip** (0 byte, 0 row) + **멱등** (`ON CONFLICT` / `MERGE`). 허위 데이터를 만들지 말고 coverage 를 그대로 표기.
5. **코어 변경 < 5%** (§10.12) — 새 도메인은 plug-in (`AUTONEXUSGRAPH_DOMAIN_PLUGINS`) + `ontology/<domain>/*.yaml` + 도구 + 템플릿 + 화이트리스트 + gold seed 추가로만. 도메인 추가 시 baseline reset 후 재측정.
6. **새 데이터 소스 추가** → `ingestion/_license.py` 의 `LICENSE_POLICY` 등록 필수 (`tests/test_license.py` invariant 가 미등록을 fail 처리).
7. **온톨로지 변경** → `make audit-ontology` PASS (pydantic strict + cypher cross-check).
8. **문서 라벨 컨벤션**: `(예정)` / `(scaffold)` / `(wired)` / `✅`. "곧" 같은 표현 금지 — 코드·테스트에 대응하는 사실만.

---

## 4. 브랜치 · 커밋 · PR

- **커밋 메시지**: `type: 요약` (`feat:` / `fix:` / `docs:` / `refactor:` …). 한국어 본문 OK. 본문에 무엇을·왜.
- **PR 마지막 단계**: 관련 README 상태 표기 + **[BACKLOG.md](./BACKLOG.md) 항목 갱신** (완료 표시 / 신규 P0·P1 추가). `make audit-dod` 로 DoD 트래픽라이트 재측정.
- **자신이 만들지 않은 working-tree 변경은 커밋하지 말 것** (동시 작업 충돌 회피) — 자신이 수정한 파일만 명시적으로 stage.

---

## 5. 테스트

- 단위 테스트는 `tests/` (root) + `src/autograph/tests/`. DB·LLM 없이 도는 mock 테스트가 기본.
- 실제 Neo4j/PG 통합은 `docs/autograph.md §7.5` 수동 절차 (`pytest -m integration` 마커는 아직 0건 — 추가 환영).
- 새 기능엔 테스트 동봉. DB-의존 로직은 thin executor 를 monkeypatch (예: `tests/test_bridge_review.py`).

---

**관련**: [SECURITY.md](./SECURITY.md) · [README §12.7](./README.md) · [BACKLOG.md](./BACKLOG.md) F-1

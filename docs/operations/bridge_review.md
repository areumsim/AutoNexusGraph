# Bridge candidate 검토 SOP (Q-1)

> **목적**: `bridge.corp_entity` 의 자동 매칭 후보(`reviewed_status='candidate'`)가 검토 없이 누적(4,792+)되어 cross-domain 답변 신뢰도를 흐리는 것을 막는다. README §12.4 / BACKLOG Q-1.
>
> **데이터 계층 SSOT**: `src/autonexusgraph/bridge_review.py` (사전 정의 함수, 자유 SQL 금지). UI: `src/autonexusgraph/ui/bridge_review.py`.

---

## 0. 상태 모델

`bridge.corp_entity.reviewed_status` ∈ `candidate` → `reviewed`(✓) / `rejected`(✗).
- 자동 매칭(Wikidata QID / LEI / 사업자번호 / 이름)은 `candidate` 로 적재 (08_bridge.sql).
- 검토 시 `reviewed_at` + `reviewed_by` 기록 (26_bridge_review.sql 추가 컬럼).
- 조회 도구(`tools/bridge.py`)는 `rejected` 를 항상 제외, `candidate` 는 `include_candidate` 플래그로 제어.

---

## 1. 사람 검토 (Streamlit UI)

```bash
streamlit run src/autonexusgraph/ui/bridge_review.py
```

- 상단 KPI: 전체 / 검토 완료율 / 대기 수 / 최장 대기일 + 유형별 분포.
- 후보는 **confidence 낮은 것 → 오래된 것 우선** 정렬 (의심 후보 먼저). `entity_type` / `match_method` 필터.
- 각 행 **✓ 승급 / ✗ 거부** — `reviewed_by` 에 사이드바의 검토자 id 기록.

우선순위 권장: `match_method='name_fuzzy'` + `confidence < 0.8` 부터 (오탐 위험 최고).

---

## 2. 자동 만료 (6개월 미검토 → 거부)

검토되지 않은 채 `DEFAULT_STALE_DAYS`(180일) 넘긴 candidate 는 자동 `rejected`.

```bash
# dry-run (대상 건수만)
make bridge-expire                                   # 기본 180일 dry-run
make bridge-expire ARGS="--days 180"

# 실제 적용 (cron 권장 — 월 1회)
make bridge-expire ARGS="--days 180 --apply"
```

`reviewed_by='auto-expire'` + `notes` 에 사유 기록 → 사후 추적·복구 가능 (id 로 `set_review_status` 재승급).

**cron 예시** (월 1회 02:00):
```cron
0 2 1 * * cd /srv/autonexusgraph && make bridge-expire ARGS="--days 180 --apply" >> /var/log/bridge_expire.log 2>&1
```

---

## 3. 진행률 KPI

```bash
make bridge-kpi
```
```json
{ "total": 4806, "candidate": 4792, "reviewed": 11, "rejected": 3,
  "reviewed_pct": 0.3, "pending": 4792, "oldest_pending_age_days": 210,
  "by_entity_type": [ { "entity_type": "supplier", "pending": 4780, "total": 4790 } ] }
```

`reviewed_pct` = (reviewed + rejected) / total × 100 (percent — 코드 `round(100.0*decided/total, 1)`, `bridge_review.py:203`). 운영 목표: pending 단조 감소 + oldest_pending_age_days 가 `DEFAULT_STALE_DAYS` 이하 유지(자동 만료가 보장).

---

## 4. 프로그램 호출 (배치 라벨링 등)

```python
from autonexusgraph import bridge_review as br
br.list_candidates(entity_type="supplier", match_method="name_fuzzy", limit=50)
br.set_review_status(row_id, "reviewed", reviewer="alice", note="IR 확인")
br.bulk_set_status([1,2,3], "rejected", reviewer="alice")
br.review_progress_kpi()
```

---

**관련**: [../../README.md §12.4](../../README.md) · [../../BACKLOG.md](../../BACKLOG.md) Q-1/Q-3 · `infra/postgres/init/08_bridge.sql` + `26_bridge_review.sql` · `src/autograph/tools/bridge.py` (조회 도구)

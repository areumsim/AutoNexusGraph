# LLM 키 도착 즉시 실행 런북 — 평가 매트릭스 + 에이전트 ablation

> LLM API 키가 발급되면 **이 문서 하나로 바로 실행·검토** 가능하도록 정리.
> 키 발급/만료 현황은 [api_keys_pending.md](./api_keys_pending.md) 참조.

## 0. 전제 — env 에 무엇이 있어야 하나
`.env` (또는 환경변수) 에 **최소 1개 provider 키**가 있으면 즉시 실행 가능:

| 모델 prefix | 필요 키 | tier 변수 |
|---|---|---|
| `gpt-*` | `OPENAI_API_KEY` | `LLM_MODEL_FAST` / `LLM_MODEL_SMART` |
| `claude-*` | `ANTHROPIC_API_KEY` | 〃 |
| `gemini-*` | `GOOGLE_API_KEY` | 〃 |

- 키 1개만 있어도 됨 — `LLM_MODEL_FAST`/`SMART` 를 그 provider 모델로 지정.
- `LLM_ENABLED=true` (기본) 확인. 비용 가드: `LLM_COST_AUTO_APPROVE_USD`(기본 $0.50),
  `LLM_SESSION_HARD_LIMIT_USD`(기본 $5). 매트릭스 1회(~$4–5)는 한도 내.

빠른 점검 (키 유효성 — LLM 1콜):
```bash
make llm-smoke        # 또는: python -c "from autonexusgraph.llm.base import get_llm_client; print(get_llm_client(role='synthesizer').chat([{'role':'user','content':'ping'}], max_tokens=5).content)"
```

## 1. 핵심 한 줄 — 평가 매트릭스 full (10 cells)
```bash
make audit-eval-matrix-full
```
- 10 cells = 8 base(4 어댑터 × rerank on/off) + **축2 hybrid 룰 vs LLM planner 2**.
- 산출: `data/reports/audit_eval_matrix_<ISO>.json` + per-cell `eval/reports/matrix_<ts>/`.
- 콘솔 PASS 라인에 **두 headline** 자동 표시:
  - `thesis: hybrid−vector = +N%p` (PRD §10.7, RAG 우위)
  - `planner(LLM−룰): +N%p (룰=.. / LLM=..)` ✅/⚠️ (축2, LLM 자율 planner 우위 여부)

검토 포인트 (JSON):
```bash
python - <<'PY'
import json, glob
p = sorted(glob.glob("data/reports/audit_eval_matrix_*.json"))[-1]
d = json.load(open(p))
print("thesis:", d["thesis"])
print("planner_ablation:", d["planner_ablation"])   # 축2 — 룰 vs LLM planner
print("dod_13:", d["dod_13"]); print("dod_14:", d["dod_14"])
PY
```

## 2. 축2 LLM planner 판정 → production 반영
- `planner_ablation.llm_better == true` + `diff_pp` 의미있게 양수 → LLM planner 채택 가치.
  `.env` 에 `AGENT_LLM_PLANNER=true` 로 production 활성 (기본 off, 화이트리스트·폴백 그대로).
- 우위 미미/음수 → 룰 planner 유지(기본값). 비용(`rule_cost` vs `llm_cost`)도 함께 비교.
- planner ablation 끄고 base 8 cells 만: `make audit-eval-matrix ARGS="--full --no-planner-ablation"`.

## 3. 키 도착 시 함께 돌릴 P1 (critical path)
| 항목 | 명령 | 산출 |
|---|---|---|
| E-1 12조합(도메인별) | `make eval-full` / `eval-auto` / `eval-cross` | `eval/reports/<run>/summary.md` |
| Q-2 confidence calibration | `make eval-full` → `make audit-calibrate` | Platt + reliability diagram |
| PG-2 공정↔재무 cross 정확도 | `make eval-cross` (구조 ✅, 정확도만) | DoD §10.20 |
| S-2 Langfuse cloud export | `LANGFUSE_*` 키 → `make audit-trace --full` | turn별 token/cost/replan |

## 4. 트러블슈팅
- 전 cell `0.000` + cost `$0` → LLM 키 만료/미설정 (synth_status.error_type 확인). §0 점검.
- `hybrid_*_planner1` cell 만 실패 → LLM planner JSON 스키마 미준수 가능 — 자동 룰 폴백되므로
  답은 나오나 plan 이 룰과 동일해질 수 있음. `safety_signals` 의 `llm_planner_*` 확인.
- 키는 있는데 budget 초과 → `LLM_SESSION_HARD_LIMIT_USD` 상향 또는 `--limit` 축소.

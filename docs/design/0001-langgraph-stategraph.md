# ADR 0001 — LangGraph StateGraph (11 노드) + 함수체인 fallback

**Status**: Accepted

## Context
멀티에이전트 추론(triage→plan→dispatch→synthesize→validate)을 **재현 가능·디버깅 가능**하게 만들어야 했다. 동시에 LangGraph 미설치 환경(테스트/경량 배포)에서도 동작해야 한다.

## Decision
- 한 turn 을 단일 `AgentState`(누적 상태, `src/autonexusgraph/agents/state.py`)로 모델링하고 **LangGraph `StateGraph` 11 노드**로 실행: triage / planner / supervisor / 4 worker(research·graph·sql·calculator) / executor_legacy / synthesizer / validator / finalize.
- LangGraph 가 없으면 **동일 노드 함수를 순차 호출하는 함수체인 fallback** 으로 degrade (같은 state 계약 공유).
- 병렬은 Supervisor 가 LangGraph `Send` API 로 worker fan-out, turn budget circuit breaker 로 가드.

## Consequences
- (+) 노드 단위 trace·재현·replan(MAX_REPLANS=2) 가능. fallback 으로 LangGraph 선택적 의존.
- (+) state 계약이 단일 SSOT → API/UI/Langfuse 가 같은 필드 소비.
- (−) state 가 비대(36 필드)해질 수 있어 reducer 규칙(`_last_wins` 등) 필요.

## Alternatives
- 단일 거대 프롬프트 체인 → 디버깅·부분 재실행 불가로 기각.
- LangGraph 하드 의존 → 경량/테스트 환경 차단으로 기각(fallback 채택).

## References
- `src/autonexusgraph/agents/{state,nodes,supervisor,dag}.py` · [docs/architecture.md](../architecture.md) (노드 토폴로지) · [mental_model §2.2](../mental_model.md)

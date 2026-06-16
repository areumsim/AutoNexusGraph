# (이전) 시스템 심화 가이드 — `docs/LEARNING.md` 로 흡수·대체됨

> 이 문서는 **`docs/LEARNING.md`(통독 세미나 교재)** 로 흡수·재구성되어 폐지됐다.
> 세미나·온보딩·이론 학습은 모두 [docs/LEARNING.md](./LEARNING.md) 를 통독하라.
>
> 구 `learning_guide.md` 의 전체 본문(약 1,977줄)은 **git 히스토리에 보존**된다
> (`git log --follow docs/learning_guide.md`). 비유 기반 설명과 일부 stale 수치를 제거하고,
> 측정값을 정본에 재접지(re-ground)하면서 구조를 선형 척추로 재배열한 것이 LEARNING.md 다.

## 구 섹션 → 현재 위치 매핑 (다른 문서의 cross-link 안내)

| 구 learning_guide 섹션 | 현재 위치 |
|---|---|
| §0.5 5분 직관 / 한 그림 | [LEARNING.md §1 — 한 질문을 끝까지 추적](./LEARNING.md) |
| §1 문제 정의 (4 한계) | [LEARNING.md §2](./LEARNING.md) |
| §2 이론 기초 (GraphRAG·ER·BOM·bridge·deterministic-first) | [LEARNING.md §3 · §7](./LEARNING.md) |
| §3 아키텍처 (3-store·11노드·AgentState·Send·replan·plugin·namespace) | [LEARNING.md §4 · §8](./LEARNING.md) |
| §4 추론 흐름 (triage·planner·worker·synth·validator·HITL) | [LEARNING.md §4](./LEARNING.md) |
| §5 안전·비용 가드 (4 layer) | [LEARNING.md §4.7](./LEARNING.md) |
| §6 LLM provider 추상화 | [LEARNING.md §4.8](./LEARNING.md) |
| §7 데이터 파이프라인 (P1~P4) | [LEARNING.md §3 · §6](./LEARNING.md) |
| §8 평가 전략 / §8.2.1 자기충족 위험 | [LEARNING.md §5 · §6.1 · §10.2](./LEARNING.md) |
| §11.4.0 Platt scaling calibration routine | [LEARNING.md 부록 E](./LEARNING.md) (+ `scripts/audit/calibrate_confidence.py`) |
| §11.x 연구 계보 (GraphRAG·임베딩·리랭커·MCP·judge) | [LEARNING.md 부록 E](./LEARNING.md) |

세부 이론(HippoRAG GDS PageRank, 임베딩 모델 비교, calibration 수식 등)의 원문은 git 히스토리를 참조하라.

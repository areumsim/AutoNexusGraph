"""Domain handler registry — PRD §10.12 의도 충족 인프라.

본 모듈의 목적은 **core (autonexusgraph) 가 외부 도메인 패키지(autograph 등)
를 직접 import 하지 않으면서도** 도메인별 동작을 위임할 수 있게 하는 것.

기존 (B 도입 이전):
    # core 내부에서 autograph 를 알고 분기
    if domain in ("auto", "cross_domain"):
        from autograph.policy import identify_auto_targets
        identify_auto_targets(state, question=q)

이후 (B):
    handler = get_handler(domain)
    if handler:
        handler.identify_targets(state, question=q)

autograph 측에선 자기 자신을 등록:
    # src/autograph/agent_handler.py 에서 (import 시점 1회)
    from autonexusgraph.agents._domain_handler import register_handler
    register_handler(AutoHandler())

이로써 의존 방향이 정상화 (autograph → core, 반대 아님). autograph 미설치 환경
에서도 core 는 finance 만 동작 (handler 등록 안 되어 분기 fall-through).
"""

from __future__ import annotations

from typing import Any, Callable, Protocol, runtime_checkable

from .state import AgentState


# ── DomainHandler Protocol ─────────────────────────────────────────
# Protocol 구현은 명시적 inherit 불필요. 메서드 시그니처만 맞으면 OK.
# 단, 명시적 inherit 을 원하면 본 protocol 을 base class 로 사용 가능.
@runtime_checkable
class DomainHandler(Protocol):
    """도메인별 agent node 동작 후크.

    각 메서드는 *선택적* 으로 구현. core 는 메서드가 없으면 finance 기본 동작
    유지. 구현 안 한 메서드는 hasattr() 또는 명시적 NotImplementedError 로 skip.
    """

    domain: str  # "auto", "cross_domain", 등. 'finance' 는 기본값이라 등록 불필요.

    def identify_targets(self, state: AgentState, *, question: str) -> None:
        """triage_node 에서 호출 — state 에 target_vehicles 등 도메인 entity 채움."""
        ...

    def plan_tasks(self, state: AgentState, *, question: str) -> list[dict]:
        """planner_node 에서 호출 — task DAG 반환. 빈 list 이면 plan 없음."""
        ...

    def toolbox_modules(self) -> list[Any]:
        """workers._toolbox_for 에서 호출 — 도메인의 tool 함수 모듈들."""
        ...

    def allowed_intents(self, kind: str) -> set[str]:
        """workers._allowed_intents — 'graph'|'sql'|'research' 별 화이트리스트."""
        ...

    def fallback_search(
        self, state: AgentState, *, query: str,
    ) -> tuple[str, Callable, dict] | None:
        """executor fallback — (tool_name, callable, kwargs) 또는 None.

        None 이면 core 가 finance 기본 fallback (search_documents) 으로 폴백.
        """
        ...

    def retrieve_module(self) -> Any | None:
        """workers.research_worker — 도메인의 retrieve 모듈 (search_documents 등 보유)."""
        ...


# 도메인 라우터: question → domain 자동 판정용. None 반환 시 다음 라우터 시도.
DomainRouter = Callable[[str, "str | None"], "str | None"]


# ── Registry (모듈 전역 싱글톤) ────────────────────────────────────
_HANDLERS: dict[str, DomainHandler] = {}
_ROUTERS: list[DomainRouter] = []


def register_handler(handler: DomainHandler) -> None:
    """handler.domain 키로 등록. 이미 있으면 덮어쓰기 (테스트·재로드 용이).

    Note: protocol 메서드를 *모두* 구현하지 않아도 OK — call site 에서 hasattr
    체크. 단 attribute ``domain`` 은 필수.
    """
    domain = getattr(handler, "domain", None)
    if not isinstance(domain, str) or not domain:
        raise ValueError(f"handler.domain must be a non-empty str: got {domain!r}")
    _HANDLERS[domain] = handler


def unregister_handler(domain: str) -> None:
    """테스트용 — 등록 해제."""
    _HANDLERS.pop(domain, None)


def get_handler(domain: str) -> DomainHandler | None:
    """domain 키로 핸들러 조회. 미등록 시 None (→ 호출자가 finance 기본 동작 사용)."""
    return _HANDLERS.get(domain)


def list_handlers() -> list[str]:
    """등록된 도메인 키 목록 (디버그용)."""
    return sorted(_HANDLERS.keys())


def register_router(fn: DomainRouter) -> None:
    """질문 → domain 자동 판정 라우터 추가. 등록 순서대로 시도."""
    _ROUTERS.append(fn)


def auto_detect_domain(question: str, hint: str | None = None) -> str:
    """등록된 라우터들에 차례로 질의. 모두 None 이면 'finance'.

    autograph 가 import 되어 있으면 자기 라우터 (route_domain) 등록 → auto/
    cross_domain 자동 판정. 미설치 환경에선 모든 질문이 finance 로 처리.
    """
    for fn in _ROUTERS:
        try:
            result = fn(question, hint)
        except Exception:   # noqa: BLE001 — 라우터 실패는 finance 폴백.
            continue
        if result:
            return result
    return "finance"


__all__ = [
    "DomainHandler",
    "DomainRouter",
    "register_handler",
    "unregister_handler",
    "get_handler",
    "list_handlers",
    "register_router",
    "auto_detect_domain",
]

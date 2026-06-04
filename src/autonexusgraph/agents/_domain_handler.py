"""Domain handler registry — README §10.12 의도 충족 인프라.

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

import importlib
import importlib.util
import logging
import os
import threading
from typing import Any, Callable, Protocol, runtime_checkable

from .state import AgentState

log = logging.getLogger(__name__)


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
# register / unregister / list 가 같은 dict·list 를 만지므로 thread-safe 보장.
# discover_plugins 의 `_DISCOVERY_LOCK` 과 일관성 — 모든 registry mutation 은 락 안.
_HANDLERS: dict[str, DomainHandler] = {}
_ROUTERS: list[DomainRouter] = []
_REGISTRY_LOCK = threading.Lock()

# ── Plugin auto-discovery ──────────────────────────────────────────
# core 는 ``from autograph`` 0건 (§10.12) 을 유지하지만, 런타임에 정작 아무도
# autograph 를 import 하지 않으면 AutoHandler 가 등록되지 않아 도메인 라우팅이
# finance 로만 떨어지는 결손이 있었다 (API/eval/UI 어디서도 explicit import 없음).
#
# 절충: 문자열 모듈명 list 를 ENV (`AUTONEXUSGRAPH_DOMAIN_PLUGINS`, csv) 로 받아
# importlib 로 soft-import. 모듈이 존재하지 않으면 graceful skip — autograph 가
# 설치되지 않은 finance-only 환경도 그대로 작동.
#
# core 의 import graph 에는 여전히 `from autograph` 가 0건 — `find_spec` /
# `import_module` 는 동적 lookup 이라 정적 분석 도구가 의존성으로 잡지 않는다.
_DISCOVERY_DONE = False
_DISCOVERY_LOCK = threading.Lock()

DEFAULT_DOMAIN_PLUGINS = "autograph"


def discover_plugins(*, force: bool = False) -> list[str]:
    """ENV 기반 도메인 플러그인 자동 import — idempotent (한 번만 실행).

    Returns:
        실제 import 성공한 모듈 이름 목록.

    동작:
        1. ``AUTONEXUSGRAPH_DOMAIN_PLUGINS`` (csv) 또는 ``DEFAULT_DOMAIN_PLUGINS`` 파싱
        2. 각 모듈에 대해 ``importlib.util.find_spec`` 으로 존재 확인
        3. 존재하면 ``importlib.import_module`` — 모듈 import 시점에 자기
           ``register_handler`` / ``register_router`` 가 실행됨 (autograph
           는 ``src/autograph/__init__.py`` 가 ``agent_handler`` 를 import 함)
        4. 실패는 warn 로그만 — 호출자 정상 진행

    ``force=True`` 이면 idempotent 가드 무시 (테스트용).
    """
    global _DISCOVERY_DONE
    with _DISCOVERY_LOCK:
        if _DISCOVERY_DONE and not force:
            return []
        _DISCOVERY_DONE = True

        names = os.getenv("AUTONEXUSGRAPH_DOMAIN_PLUGINS", DEFAULT_DOMAIN_PLUGINS)
        loaded: list[str] = []
        for raw in names.split(","):
            name = raw.strip()
            if not name:
                continue
            try:
                if importlib.util.find_spec(name) is None:
                    log.debug("[domain] plugin %r not installed — skip", name)
                    continue
            except (ImportError, ValueError):
                continue
            try:
                importlib.import_module(name)
                loaded.append(name)
                log.info("[domain] plugin %r loaded", name)
            except Exception as exc:   # noqa: BLE001
                log.warning("[domain] plugin %r import failed: %s", name, exc)
        return loaded


def _reset_discovery_for_test() -> None:
    """테스트 픽스처 전용 — discovery 게이트 리셋."""
    global _DISCOVERY_DONE
    with _DISCOVERY_LOCK:
        _DISCOVERY_DONE = False


def register_handler(handler: DomainHandler) -> None:
    """handler.domain 키로 등록. 이미 있으면 덮어쓰기 (테스트·재로드 용이).

    Note: protocol 메서드를 *모두* 구현하지 않아도 OK — call site 에서 hasattr
    체크. 단 attribute ``domain`` 은 필수.
    """
    domain = getattr(handler, "domain", None)
    if not isinstance(domain, str) or not domain:
        raise ValueError(f"handler.domain must be a non-empty str: got {domain!r}")
    with _REGISTRY_LOCK:
        _HANDLERS[domain] = handler


def unregister_handler(domain: str) -> None:
    """테스트용 — 등록 해제."""
    with _REGISTRY_LOCK:
        _HANDLERS.pop(domain, None)


def get_handler(domain: str) -> DomainHandler | None:
    """domain 키로 핸들러 조회. 미등록 시 None (→ 호출자가 finance 기본 동작 사용).

    첫 호출 시 ``discover_plugins()`` 가 실행돼 ENV/기본 플러그인을 자동 로드한다.
    이후 호출은 idempotent (no-op).
    """
    if not _DISCOVERY_DONE:
        discover_plugins()
    with _REGISTRY_LOCK:
        return _HANDLERS.get(domain)


def list_handlers() -> list[str]:
    """등록된 도메인 키 목록 (디버그용)."""
    with _REGISTRY_LOCK:
        return sorted(_HANDLERS.keys())


def register_router(fn: DomainRouter) -> None:
    """질문 → domain 자동 판정 라우터 추가. 등록 순서대로 시도."""
    with _REGISTRY_LOCK:
        _ROUTERS.append(fn)


def call_handler_method(
    state: AgentState,
    handler: Any,
    method_name: str,
    *args: Any,
    signal_extra: str | None = None,
    **kwargs: Any,
) -> Any:
    """``handler.<method_name>(*args, **kwargs)`` 안전 호출 — 호출 패턴 SSOT.

    handler 가 ``None`` 또는 메서드 미존재 → ``None`` 반환 (호출처가 자기
    fallback 적용). 호출 실패 → ``log.warning`` + ``state['safety_signals']``
    에 한 줄 적재 + ``None`` 반환. 호출처는 ``None`` 일 때 자기 fallback 분기.

    safety_signals 형식 (handler 호출 6 사이트 통일):
        ``f"{domain}_{method_name}_failed:[{signal_extra}:]{type(exc).__name__}"``

    Args:
        state: AgentState (실패 시 safety_signals append 대상)
        handler: DomainHandler 또는 None
        method_name: 호출할 메서드 이름
        signal_extra: 신호 키에 포함할 부가 정보 (예: allowed_intents 의 kind)
        *args / **kwargs: 메서드에 전달할 인자

    Returns:
        method 반환값 또는 None (handler/method 없거나 예외 발생).
    """
    if handler is None or not hasattr(handler, method_name):
        return None
    d = getattr(handler, "domain", "unknown")
    try:
        return getattr(handler, method_name)(*args, **kwargs)
    except Exception as exc:   # noqa: BLE001 — finance/기본 폴백.
        log.warning("[handler:%s] %s failed: %s", d, method_name, exc)
        signal = f"{d}_{method_name}_failed:"
        if signal_extra:
            signal += f"{signal_extra}:"
        signal += type(exc).__name__
        state.setdefault("safety_signals", []).append(signal)
        return None


def auto_detect_domain(question: str, hint: str | None = None) -> str:
    """등록된 라우터들에 차례로 질의. 모두 None 이면 'finance'.

    autograph 가 import 되어 있으면 자기 라우터 (route_domain) 등록 → auto/
    cross_domain 자동 판정. 미설치 환경에선 모든 질문이 finance 로 처리.

    첫 호출 시 ``discover_plugins()`` 가 실행돼 ENV/기본 플러그인을 자동 로드한다.
    """
    if not _DISCOVERY_DONE:
        discover_plugins()
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
    "DEFAULT_DOMAIN_PLUGINS",
    "register_handler",
    "unregister_handler",
    "get_handler",
    "list_handlers",
    "register_router",
    "auto_detect_domain",
    "discover_plugins",
    "call_handler_method",
]

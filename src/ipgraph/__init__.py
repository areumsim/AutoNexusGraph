"""IPGraph (도메인3) — 특허·기술혁신 도메인 어댑터.

PRD v2.2 §12.5 + docs/ipgraph.md SSOT. ``autograph`` 와 동일 plug-in 패턴:
``register_handler`` 부작용 + ``register_router`` + ``ontology/ip/*.yaml`` +
typed tool pool + ``ip_*`` Cypher 템플릿 + gold QA seed.

import 시점 부작용:
- ``agent_handler`` 의 ``register_handler(IPGraphHandler())`` 자동 실행
- ``policy`` 의 ``register_router(route_domain_ip)`` 자동 실행 (agent_handler 가 호출)
- ``ip_*`` Cypher 템플릿 자동 병합 (tools/__init__.py 가 처리)

본 패키지는 ``core (autonexusgraph) → ip`` 의존을 보유하지 않는다 (반대 방향).
core 의 ``_domain_handler.discover_plugins()`` 가 ENV ``AUTONEXUSGRAPH_DOMAIN_PLUGINS``
(csv) 기반으로 본 패키지를 import — 그 부작용으로 핸들러·라우터 등록.

ingestion / loaders 의 OpenAlex 적재는 별도 (기존 코드 보존).
"""

# import 부작용으로 핸들러·라우터·템플릿 등록.
from . import agent_handler   # noqa: F401  부작용: register_handler + register_router
# tools 패키지 import 시 ip_* Cypher 템플릿 자동 병합 (autograph 패턴 동일).
# tools 내부 PG/Neo4j 의존이라 lazy import — 호출 시점에 등록.

__all__ = ["agent_handler"]

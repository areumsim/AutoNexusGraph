# AutoNexusGraph 앱 이미지 (api / web / ingestion-worker 공용) — O-2 production 배포.
#
# dev 는 컨테이너 안에서 `make serve-api` (--reload) 로 직접 실행. 본 이미지는
# **production 용** — --reload 없음, non-root, 멀티 worker.
#
# 빌드:   docker build -f infra/Dockerfile -t autonexusgraph:<tag> .
# 실행:   docker-compose.prod.yml 의 api/web/ingestion-worker 서비스가 사용.
#
# RUNTIME_EXTRAS — 설치할 optional-dependencies (pyproject [project.optional-dependencies]).
# 기본 agent,llm,db,ui (런타임 필수). 데이터 적재 worker 는 ingest 추가.
ARG PYTHON_VERSION=3.12

# ── builder: 의존성 + 패키지 wheel 설치 ──────────────────────────────
FROM python:${PYTHON_VERSION}-slim AS builder

ARG RUNTIME_EXTRAS=agent,llm,db,ui

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# 빌드 의존성 (psycopg/lxml 등 일부 C 확장). slim 에는 컴파일러 없음.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

# venv 에 설치 → runtime 스테이지로 복사 (빌드 툴체인 제외, 이미지 슬림).
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app
# 메타데이터 먼저 복사 → 의존성 레이어 캐시 (소스 변경 시 재설치 회피).
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install ".[${RUNTIME_EXTRAS}]"

# ── runtime: 슬림 실행 이미지 ────────────────────────────────────────
FROM python:${PYTHON_VERSION}-slim AS runtime

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    APP_ENV=production

# curl — compose/k8s healthcheck 의 /health probe 용.
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
# 런타임에 필요한 파일만 (소스 + 마이그레이션 + 스크립트). data/ .env 는 마운트/주입.
COPY src ./src
COPY scripts ./scripts
COPY infra/postgres/init ./infra/postgres/init
COPY ontology ./ontology
COPY eval ./eval

# non-root 실행 (보안).
RUN useradd --create-home --uid 10001 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
# 기본 진입점 = API. web/ingestion-worker 는 compose/k8s 에서 command override.
# --reload 없음. worker 수는 API_WORKERS (기본 2). in-memory rate limit·langfuse
# ContextVar 는 worker-local 이므로 글로벌 한도 필요 시 reverse proxy (README §12.3).
CMD ["sh", "-c", "uvicorn autonexusgraph.api.main:app --host 0.0.0.0 --port 8000 --workers ${API_WORKERS:-2}"]

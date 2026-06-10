"""중앙 설정 — .env 자동 로드, Pydantic 타입 검증."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import ClassVar, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # === LLM Provider ===
    # 'auto' — 모델명 prefix 로 provider 자동 결정 (gpt-* / claude-* / gemini-* / local-).
    # 명시 ('openai' 등) 는 그 provider 만 사용. 권장: 'auto' 로 두고 모델만 갈아끼우기.
    llm_provider: Literal["auto", "openai", "anthropic", "google", "local"] = "auto"
    llm_model: str = "gpt-4o"
    llm_timeout: float = 120.0

    # Kill-switch — False 면 get_llm_client() 가 LLMError 로 모든 LLM 호출 차단.
    # llm_guard.py on/off (또는 .env LLM_ENABLED) 로 토글. (실행 중 프로세스는
    # get_settings lru_cache 때문에 재시작해야 반영 — 배치/CLI 는 즉시 반영.)
    llm_enabled: bool = True

    # Provider-specific 키 — 모델명 prefix 로 알맞은 키 자동 선택.
    # OPENAI    : gpt-* 모델
    # ANTHROPIC : claude-* 모델
    # GOOGLE    : gemini-* 모델 (ai.google.dev/apikey)
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    google_api_key: str = ""

    # Tier 단축 — 모든 role 의 기본 모델을 2개 변수로 일괄 제어.
    # provider 변경 시 LLM_MODEL_FAST/SMART 2개만 바꾸면 모든 role 동시 전환.
    # 개별 LLM_MODEL_<role> 명시 시 그것이 우선.
    llm_model_fast: str = "gemini-2.5-flash"     # triage/research/sql 등 가벼운 호출
    llm_model_smart: str = "gemini-2.5-pro"      # planner/synthesizer 등 추론·생성

    # Provider fallback — 1차 provider 호출이 LLMError(auth/quota/429/5xx/timeout) 로
    # 실패하면 자동 전환할 보조 provider. 빈 값 = 비활성(단일 provider, 기존 동작).
    # get_llm_client 가 [primary, fallback] 를 FallbackLLMClient 로 묶어
    # BudgetAware/Logging 안쪽(innermost)에 둔다 → 비용 가드·기록은 어느 쪽이 응답해도 1회.
    # llm_fallback_model 비우면 fallback provider 의 기본 FAST 모델 사용(base._DEFAULT_FAST_MODEL).
    llm_fallback_provider: Literal["", "openai", "anthropic", "google", "local"] = ""
    llm_fallback_model: str = ""

    # 개별 role override — 비워두면 tier 기본값 자동 적용 (model_validator 가 보강).
    llm_model_triage: str = ""
    llm_model_planner: str = ""
    llm_model_supervisor: str = ""
    llm_model_research: str = ""
    llm_model_graph: str = ""
    llm_model_sql: str = ""
    llm_model_calculator: str = ""
    llm_model_validator: str = ""
    llm_model_synthesizer: str = ""
    llm_model_judge: str = ""
    # Titler 는 ui/storage 의 1회 호출 — 비용 최소화 → 항상 FAST.
    llm_model_titler: str = ""

    local_llm_base_url: str = "http://localhost:8000/v1"

    # === 세션 비용 한도 (영속 누적 가드 — cost_log.jsonl 기반) ===
    # turn/프로세스 리셋과 무관하게, llm_cost_window_hours 시간창 안의 모든 LLM
    # 호출 누적이 이 값에 도달하면 BudgetExceeded 로 후속 호출 차단. (per-turn
    # 한도는 agent_turn_budget_*_usd, per-batch 기본 한도는 llm_cost_hard_limit_usd)
    llm_session_hard_limit_usd: float = 5.00
    llm_session_warn_at_usd: float = 2.50
    # 영속 누적 한도 집계 시간창(시간). 0 이하 → 전체 기간(all-time). 기본 24h.
    llm_cost_window_hours: float = 24.0

    # === 임베딩 ===
    embedding_url: str = "http://localhost:8080"
    reranker_url: str = "http://localhost:8081"
    embedding_dim: int = 1024
    # ↑ pydantic 파싱이 실패하는 dirty env 값 ("1024ll" 등) 도 숫자만 추출해 복구.

    @field_validator("embedding_dim", mode="before")
    @classmethod
    def _coerce_embedding_dim(cls, v):
        """dirty env 값에서 앞쪽 숫자만 추출 — 잘못된 문자가 섞여도 robust."""
        if isinstance(v, int):
            return v
        if isinstance(v, str):
            import re
            m = re.match(r"^\s*(\d+)", v)
            if m:
                return int(m.group(1))
        return 1024

    # === 공유 DB 멀티테넌시 namespace ===
    # 기존 Neo4j/Qdrant/PG 서버를 다른 프로젝트와 공유하므로, 프로젝트별 데이터가
    # 충돌하지 않도록 namespace 를 단일 토큰에서 파생한다. PG database 명 (DSN 의
    # `autonexusgraph`) 으로 1차 격리되지만, 그 위에 스키마/라벨/컬렉션 프리픽스로 방어.
    # 토큰 한 곳만 바꾸면 전체 일관 — pg_schema()/neo4j_label()/qdrant_collection 헬퍼 참조.
    app_namespace: str = "anxg"

    # === DB ===
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = ""
    # Neo4j 격리 database. 빈 값 = 드라이버 기본 db (community 단일 db / 로컬 dev).
    # 공유 서버가 Enterprise 면 `autonexusgraph` 로 두어 named-database 격리 (라벨 프리픽스와 병행).
    neo4j_database: str = ""

    postgres_dsn: str = "postgresql://autonexusgraph:autonexusgraph_dev@localhost:5432/autonexusgraph"

    # Qdrant — minimal 스택에선 미사용 (pgvector 통합). 활성화 시 .env 에 값 채움.
    qdrant_url: str = ""
    qdrant_api_key: str = ""
    # Qdrant 컬렉션 namespace — 공유 Qdrant 에서 프로젝트별 분리.
    qdrant_collection: str = "anxg_chunks"

    def pg_schema(self, name: str) -> str:
        """논리 스키마명 → 물리 스키마명 (프로젝트 namespace 프리픽스).

        예: pg_schema("master") → "anxg_master". 공유 PG database 안에서 타 프로젝트
        스키마와 충돌 방지. raw SQL 은 정적 프리픽스를 직접 쓰지만, 동적 조립 지점은
        본 헬퍼로 일관 유지.
        """
        return f"{self.app_namespace}_{name}"

    def neo4j_label(self, label: str) -> str:
        """논리 라벨 → namespace 프리픽스 라벨. 예: neo4j_label("Company") → "Anxg_Company"."""
        return f"{self.app_namespace.capitalize()}_{label}"

    # === 데이터 소스 ===
    dart_api_key: str = ""
    dart_base_url: str = "https://opendart.fss.or.kr/api"

    ecos_api_key: str = ""
    ecos_base_url: str = "https://ecos.bok.or.kr/api"

    krx_base_url: str = "http://data.krx.co.kr"

    # 공공데이터포털 (data.go.kr) — FTC 기업집단·통계청·환경부 등 공통 키
    data_go_kr_api_key: str = ""

    # 통계청 KOSIS — kosis.kr/openapi 무료 키
    kosis_api_key: str = ""

    # 특허청 KIPRIS — kipris.or.kr/kipo-api/ 무료 키
    kipris_api_key: str = ""

    # 한국ESG기준원 (KCGS) — 공개 CSV 다운로드 URL 또는 manual_path
    kcgs_csv_dir: str = "data/raw/kcgs"

    # 빅카인즈 — bigkinds.or.kr 키 (미보유 시 skeleton 만)
    bigkinds_api_key: str = ""

    # LAW.go.kr — 무료 키 (open.law.go.kr/LSO/openApi)
    law_api_key: str = ""

    # SEC EDGAR — 키 불필요 (User-Agent 만 필요)
    sec_user_agent: str = "AutoNexusGraph-Research/0.1 (ifkbn@kolon.com)"

    # === 수집 ===
    ingest_tickers: str = "KOSPI200,KOSDAQ100"
    ingest_years_back: int = 3
    ingest_rate_limit_per_sec: float = 10.0
    ingest_raw_dir: Path = Field(default=PROJECT_ROOT / "data" / "raw")
    ingest_processed_dir: Path = Field(default=PROJECT_ROOT / "data" / "processed")

    # === 에이전트 ===
    agent_max_replan: int = 2
    agent_query_budget_sec: int = 40
    agent_max_answer_len: int = 5000
    # 대화형 interrupt(HITL) 허용 여부. True=API/UI(clarification·cost 승인 가능).
    # False=batch/eval/cron(재개 불가) → request_interrupt 가 InterruptUnavailable 로
    # 다운그레이드 → 호출부가 1순위 자동선택 등 폴백. (eval 에서 모호 회사명 질문이
    # langgraph interrupt 로 멈춰 빈 답 나가던 버그 차단 — AGENT_ALLOW_INTERRUPTS=false.)
    agent_allow_interrupts: bool = True
    # 축2: LLM 자율 planner (plan-and-execute). True 면 planner 가 LLM 으로 task DAG 를
    # 제안하고 화이트리스트 검증 후 사용 — 실패/빈결과 시 기존 룰·handler 로 폴백.
    # 기본 False (opt-in) — 룰 planner 가 검증된 안전 기본값.
    agent_llm_planner: bool = False
    agent_turn_budget_usd: float = 0.20    # 한 대화 turn 의 최대 LLM 비용 (도메인 기본값)
    # 도메인별 override — 0.0 이면 agent_turn_budget_usd 상속.
    # auto 도메인은 LLM 추출 (P3) 이 cross 분야 보다 무거울 수 있어 별도 한도 권장.
    agent_turn_budget_finance_usd: float = 0.0
    agent_turn_budget_auto_usd: float = 0.0
    agent_turn_budget_cross_domain_usd: float = 0.0
    agent_turn_budget_ip_usd: float = 0.0        # ip 보조축 — 정형 위주라 낮은 한도 권장 (.env: AGENT_TURN_BUDGET_IP_USD)
    # 임의 도메인 (legal/safety 등) 의 turn 한도는 env 로 직접 지정:
    #   AGENT_TURN_BUDGET_<DOMAIN>_USD=0.30
    # → turn_budget_for_domain("legal") 가 동적으로 그것을 읽음.

    # === LangGraph checkpoint (PRD §7.5.8) ===
    # auto = PG 시도 → memory 폴백, memory/in_memory = 강제 in-memory, none = 비활성
    langgraph_checkpoint_backend: Literal["auto", "memory", "in_memory", "none"] = "auto"
    langgraph_checkpoint_schema: str = "anxg_chat"  # PG schema (search_path 주입). namespace 프리픽스 = <app_namespace>_chat
    langgraph_checkpoint_dsn: str = ""             # 빈 값이면 postgres_dsn 사용

    # === LLM 비용 가드 (사용자 명시) ===
    # 모든 LLM 호출은 dry-run estimator + 누적 한도 + circuit breaker 통과해야 함.
    # llm_cost_hard_limit_usd = 단일 tracker(한 turn 또는 한 배치)의 기본 hard
    # limit. 영속/시간창 누적 한도는 위 llm_session_hard_limit_usd 가 담당.
    llm_cost_hard_limit_usd: float = 5.00    # 단일 tracker 누적 도달 시 abort
    llm_cost_auto_approve_usd: float = 0.50  # 추정 이 이하면 자동 통과, 초과면 --approve-cost 필요
    llm_cost_report_every: int = 10          # 매 N 호출마다 누적 로그
    llm_cost_log_calls: bool = False          # True 면 anxg_ops.llm_calls 에 호출별 상세 적재
    # 영속 JSONL 로그 — 모든 LLM 호출 1줄씩 append. 누락 없는 누계 추적용.
    # cost_history CLI 가 본 파일을 읽어 일/caller/모델 별 집계.
    llm_cost_log_path: Path = Field(
        default=PROJECT_ROOT / "data" / "cost_log.jsonl",
    )

    # === Tracing ===
    trace_backend: Literal["langfuse", "langsmith", ""] = ""
    langfuse_host: str = ""
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langsmith_api_key: str = ""
    langsmith_project: str = "autonexusgraph"

    # === 운영 ===
    app_env: Literal["local", "server", "production"] = "local"
    log_level: str = "INFO"

    # === API 보안 (O-1 — BACKLOG §5, README §12.2) ===
    # API key 인증. comma-separated 토큰 목록. 항목은 ``token:user_id`` 또는 bare
    # ``token`` (bare 면 user_id 는 토큰 해시로 자동 도출). **비워두면 open 모드**
    # (dev Quickstart 보존, 첫 요청에서 1회 경고). production 은 반드시 설정.
    api_keys: str = ""
    # per-identity (인증 시 user_id / open 모드는 client IP) 분당 요청 한도.
    # 0 = 비활성. **in-memory** — 단일 인스턴스 한정, multi-instance 는 reverse
    # proxy / redis 필요 (README §12.3).
    api_rate_limit_per_min: int = 0

    @field_validator("ingest_raw_dir", "ingest_processed_dir", mode="before")
    @classmethod
    def _resolve_path(cls, v: str | Path) -> Path:
        p = Path(v)
        return p if p.is_absolute() else PROJECT_ROOT / p

    # 각 role 의 tier 분류 — FAST 는 가벼운 호출, SMART 는 추론·생성 무게 있음.
    # 새 role 추가 시 본 dict 에만 등록하면 자동 fill 동작. ClassVar 로 명시해
    # pydantic 이 model field 가 아닌 클래스 속성으로 인식하게 한다.
    _ROLE_TIER: ClassVar[dict[str, str]] = {
        "triage":      "fast",
        "supervisor":  "fast",
        "research":    "fast",
        "sql":         "fast",
        "calculator":  "fast",
        "validator":   "fast",
        "titler":      "fast",
        "planner":     "smart",
        "graph":       "smart",
        "synthesizer": "smart",
        "judge":       "smart",
    }

    @model_validator(mode="after")
    def _fill_role_models(self):
        """비어있는 llm_model_<role> 을 tier 기본값으로 자동 보강.

        provider 전환 = LLM_MODEL_FAST/SMART 2개만 바꾸면 모든 role 동시 전환.
        개별 override 는 그대로 우선.
        """
        for role, tier in self._ROLE_TIER.items():
            attr = f"llm_model_{role}"
            current = (getattr(self, attr, "") or "").strip()
            if current:
                continue
            fallback = self.llm_model_smart if tier == "smart" else self.llm_model_fast
            object.__setattr__(self, attr, fallback)
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """프로세스 단위 싱글톤. 테스트에서 override 하려면 cache_clear() 호출."""
    return Settings()


def turn_budget_for_domain(domain: str | None) -> float:
    """state["domain"] 에 맞는 turn budget — 3 단계 우선순위로 결정.

    1. Settings 의 declared field ``agent_turn_budget_<domain>_usd`` (auto/
       cross_domain/finance) 가 > 0 이면 그것.
    2. env 의 ``AGENT_TURN_BUDGET_<DOMAIN>_USD`` (임의 도메인 동적 지원 —
       legal/safety 등 새 도메인도 코드 수정 없이 한도 설정 가능).
    3. 위 둘 다 없으면 ``agent_turn_budget_usd`` 도메인 무관 기본값.

    예시 — legal 도메인에 0.30 USD/turn 한도:
        AGENT_TURN_BUDGET_LEGAL_USD=0.30 python -m ...
    """
    import os
    s = get_settings()
    d = str(domain or "finance").lower()

    # 1. declared field 우선
    attr = f"agent_turn_budget_{d}_usd"
    declared = float(getattr(s, attr, 0.0) or 0.0)
    if declared > 0:
        return declared

    # 2. env 동적 lookup — 임의 도메인 지원
    env_key = f"AGENT_TURN_BUDGET_{d.upper()}_USD"
    raw = os.environ.get(env_key, "").strip()
    if raw:
        try:
            v = float(raw)
            if v > 0:
                return v
        except ValueError:
            pass

    # 3. 도메인 무관 기본값
    return float(s.agent_turn_budget_usd)

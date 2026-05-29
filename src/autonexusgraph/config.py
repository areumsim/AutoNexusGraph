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

    # === 세션 비용 한도 (전역 가드 — 모든 LLM 호출 합산 한도) ===
    # 도달 시 BudgetExceeded 로 모든 후속 호출 차단. 코드 기본값을 안전선으로,
    # env 로 상향/하향 조정 가능.
    llm_session_hard_limit_usd: float = 5.00
    llm_session_warn_at_usd: float = 2.50

    # === 임베딩 ===
    embedding_url: str = "http://localhost:8080"
    reranker_url: str = "http://localhost:8081"
    embedding_dim: int = 1024

    # === DB ===
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = ""

    postgres_dsn: str = "postgresql://autonexusgraph:autonexusgraph_dev@localhost:5432/autonexusgraph"

    # Qdrant — minimal 스택에선 미사용 (pgvector 통합). 활성화 시 .env 에 값 채움.
    qdrant_url: str = ""
    qdrant_api_key: str = ""

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
    agent_turn_budget_usd: float = 0.20    # 한 대화 turn 의 최대 LLM 비용 (도메인 기본값)
    # 도메인별 override — 0.0 이면 agent_turn_budget_usd 상속.
    # auto 도메인은 LLM 추출 (P3) 이 cross 분야 보다 무거울 수 있어 별도 한도 권장.
    agent_turn_budget_auto_usd: float = 0.0
    agent_turn_budget_cross_domain_usd: float = 0.0

    # === LangGraph checkpoint (PRD §7.5.8) ===
    # auto = PG 시도 → memory 폴백, memory/in_memory = 강제 in-memory, none = 비활성
    langgraph_checkpoint_backend: Literal["auto", "memory", "in_memory", "none"] = "auto"
    langgraph_checkpoint_schema: str = "chat"     # PG schema (search_path 주입)
    langgraph_checkpoint_dsn: str = ""             # 빈 값이면 postgres_dsn 사용

    # === LLM 비용 가드 (사용자 명시) ===
    # 모든 LLM 호출은 dry-run estimator + 누적 한도 + circuit breaker 통과해야 함.
    llm_cost_hard_limit_usd: float = 5.00    # 누적 이 한도 도달 시 즉시 abort
    llm_cost_auto_approve_usd: float = 0.50  # 추정 이 이하면 자동 통과, 초과면 --approve-cost 필요
    llm_cost_report_every: int = 10          # 매 N 호출마다 누적 로그
    llm_cost_log_calls: bool = False          # True 면 ops.llm_calls 에 호출별 상세 적재

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
    """state["domain"] 에 맞는 turn budget — 0.0 override 면 기본값 상속.

    finance / 미지정 → agent_turn_budget_usd
    auto              → agent_turn_budget_auto_usd or agent_turn_budget_usd
    cross_domain      → agent_turn_budget_cross_domain_usd or agent_turn_budget_usd
    """
    s = get_settings()
    d = str(domain or "finance").lower()
    if d == "auto":
        v = float(s.agent_turn_budget_auto_usd or 0.0)
        return v if v > 0 else float(s.agent_turn_budget_usd)
    if d == "cross_domain":
        v = float(s.agent_turn_budget_cross_domain_usd or 0.0)
        return v if v > 0 else float(s.agent_turn_budget_usd)
    return float(s.agent_turn_budget_usd)

"""Application configuration loaded from environment variables."""

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Global application settings."""

    # LLM
    gemini_api_key: str = ""
    openai_api_key: str = ""
    llm_provider: str = Field(
        default="local",
        validation_alias=AliasChoices("LLM_PROVIDER", "LOCAL_LLM_PROVIDER"),
    )  # gemini | local
    local_llm_base_url: str = "http://127.0.0.1:8080/v1"
    local_llm_model: str = "finance_decision_model"
    local_agent_llm_base_url: str = ""
    local_agent_llm_model: str = "agentic_capital_react_model"
    local_agent_llm_timeout_seconds: float = 90.0
    local_agent_llm_max_tokens: int = 512
    local_embedding_model: str = "finance_embedding_model"
    local_llm_api_key: str = ""
    local_llm_timeout_seconds: float = 30.0
    local_llm_temperature: float = 0.2
    local_llm_send_native_tools: bool = False
    local_llm_readiness_required: bool = True
    local_llm_expected_health_model: str = ""
    local_llm_health_timeout_seconds: float = 5.0
    local_finance_smoke_enabled: bool = True
    local_finance_smoke_timeout_seconds: float = 30.0
    local_finance_pipeline_enabled: bool = True
    local_finance_paper_order_execution_enabled: bool = True
    local_finance_paper_probe_on_model_loop: bool = True
    local_finance_default_symbol: str = "005930"
    local_finance_default_symbols: str = "005930,AAPL"
    local_finance_default_market: str = "kr_stock"
    local_finance_risk_per_trade_pct: float = 0.05
    local_finance_rag_query_base_url: str = ""
    local_finance_tool_planner_base_url: str = ""
    local_finance_decision_base_url: str = ""
    local_finance_risk_guard_base_url: str = ""
    local_psychology_base_url: str = "http://127.0.0.1:19400/v1"
    local_psychology_model: str = "psychology_model_suite"
    local_psychology_expected_health_model: str = ""
    local_psychology_api_key: str = ""
    local_psychology_readiness_required: bool = False
    local_psychology_smoke_enabled: bool = True
    local_psychology_timeout_seconds: float = 30.0

    # Database
    database_url: str = "postgresql+asyncpg://agent:agent_dev_password@localhost:5432/agentic_capital"
    redis_url: str = "redis://localhost:6379/0"
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = ""

    # Exchange — Crypto
    binance_api_key: str = ""
    binance_secret_key: str = ""
    upbit_access_key: str = ""
    upbit_secret_key: str = ""

    # Exchange — US Stock
    alpaca_api_key: str = ""
    alpaca_secret_key: str = ""
    alpaca_base_url: str = "https://paper-api.alpaca.markets"

    # Exchange — KR Stock (실전투자)
    kis_app_key: str = ""
    kis_app_secret: str = ""
    kis_account_no: str = ""
    kis_is_paper: bool = True

    # Exchange — KR Stock (모의투자 전용 — is_paper=True 시 자동 사용)
    kis_paper_app_key: str = ""
    kis_paper_app_secret: str = ""
    kis_paper_account_no: str = ""

    @property
    def effective_kis_app_key(self) -> str:
        return self.kis_paper_app_key if self.kis_is_paper and self.kis_paper_app_key else self.kis_app_key

    @property
    def effective_kis_app_secret(self) -> str:
        return self.kis_paper_app_secret if self.kis_is_paper and self.kis_paper_app_secret else self.kis_app_secret

    @property
    def effective_kis_account_no(self) -> str:
        return self.kis_paper_account_no if self.kis_is_paper and self.kis_paper_account_no else self.kis_account_no

    # Simulation
    simulation_seed: int = 42
    initial_capital: int = 1_000_000
    log_level: str = "INFO"
    simulation_zero_decision_max_cycles: int = 5
    simulation_min_cycle_seconds: int = 60
    simulation_stop_when_market_closed: bool = False

    # Cost-aware evaluation
    ai_daily_op_cost_krw: float = 10_000.0
    ai_cost_per_cycle_krw: float = 0.0
    ai_cost_per_tool_call_krw: float = 0.0

    # Futures risk management
    futures_max_contracts: int = 3          # hard cap per open order
    futures_daily_loss_pct: float = 0.05    # halt trading if daily loss >= 5% of capital
    futures_stop_loss_pct: float = 0.02     # auto-close position at 2% loss (isolated stop-loss)
    futures_max_leverage: float = 5.0       # max leverage: notional / available_capital
    futures_position_size_pct: float = 0.05 # max 5% of total capital per open trade
    futures_virtual_paper_fallback: bool = True  # simulate mini futures when KIS paper rejects them
    futures_live_orders_enabled: bool = False  # explicit opt-in required before live futures orders
    futures_volatility_threshold_pct: float = 2.0  # skip cycle if KOSPI200 moves >2% from open
    futures_deadman_max_errors: int = 5     # consecutive errors before deadman triggers
    futures_deadman_cooldown_secs: int = 300  # cooldown seconds after deadman trigger

    # LangSmith
    langchain_tracing_v2: bool = False
    langchain_api_key: str = ""
    langchain_project: str = "agentic-capital"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()

"""Application configuration loaded from environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Global application settings."""

    # LLM
    gemini_api_key: str = ""
    openai_api_key: str = ""

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

    # Futures risk management
    futures_max_contracts: int = 3          # hard cap per open order
    futures_daily_loss_pct: float = 0.05    # halt trading if daily loss >= 5% of capital
    futures_stop_loss_pct: float = 0.02     # auto-close position at 2% loss (isolated stop-loss)
    futures_max_leverage: float = 5.0       # max leverage: notional / available_capital
    futures_position_size_pct: float = 0.05 # max 5% of total capital per open trade
    futures_volatility_threshold_pct: float = 2.0  # skip cycle if KOSPI200 moves >2% from open
    futures_deadman_max_errors: int = 5     # consecutive errors before deadman triggers
    futures_deadman_cooldown_secs: int = 300  # cooldown seconds after deadman trigger

    # LangSmith
    langchain_tracing_v2: bool = False
    langchain_api_key: str = ""
    langchain_project: str = "agentic-capital"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()

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

    # Exchange — KR Stock
    kis_app_key: str = ""
    kis_app_secret: str = ""
    kis_account_no: str = ""
    kis_is_paper: bool = True

    # Simulation
    simulation_seed: int = 42
    initial_capital: int = 1_000_000
    log_level: str = "INFO"

    # LangSmith
    langchain_tracing_v2: bool = False
    langchain_api_key: str = ""
    langchain_project: str = "agentic-capital"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()

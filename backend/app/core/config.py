from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # App
    APP_NAME: str = "QQQQ Agents"
    DEBUG: bool = False

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@db:5432/qqqq_agents"

    # Redis
    REDIS_URL: str = "redis://redis:6379/0"

    # Interactive Brokers Settings
    IB_HOST: str = "127.0.0.1"
    IB_PORT: int = 7497  # 7497=TWS paper, 7496=TWS live, 4001=Gateway paper, 4002=Gateway live
    IB_CLIENT_ID: int = 1
    IB_READONLY: bool = False
    BROKER_ACCOUNT_ID: Optional[str] = None

    # Market Data API (optional backup - IB provides market data)
    MARKET_DATA_API_KEY: Optional[str] = None

    # Robinhood Crypto API
    ROBINHOOD_API_KEY: Optional[str] = None
    ROBINHOOD_PRIVATE_KEY: Optional[str] = None  # Base64-encoded ED25519 private key

    # Trading Settings
    DRY_RUN: bool = True  # When True, agents recommend but don't execute trades
    MAX_POSITION_PCT: float = 0.25  # 25% max deployment
    MAX_DRAWDOWN_PCT: float = 0.15  # 15% drawdown trigger
    VIX_SHUTDOWN_THRESHOLD: float = 45.0
    SPREAD_WIDTH: int = 25  # 25-wide put spread
    TARGET_CREDIT_MIN: float = 0.55
    TARGET_CREDIT_MAX: float = 0.70
    MAX_DELTA: float = 0.12

    # Orchestrator Settings
    EXECUTION_HOUR: int = 15  # 3 PM ET
    EXECUTION_MINUTE: int = 45

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()

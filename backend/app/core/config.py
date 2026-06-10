from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "CryptoQuant"
    database_url: str = "postgresql+asyncpg://cryptoquant:cryptoquant@localhost:5432/cryptoquant"
    redis_url: str = "redis://localhost:6379/0"
    watchlist: str = (
        "BTCUSDT,ETHUSDT,BNBUSDT,SOLUSDT,XRPUSDT,ADAUSDT,DOGEUSDT,AVAXUSDT,LINKUSDT,DOTUSDT"
    )
    trading_mode: str = "testnet"
    cors_origins: str = "http://localhost:5173"

    @property
    def watchlist_symbols(self) -> list[str]:
        return [s.strip().upper() for s in self.watchlist.split(",") if s.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()

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
    whale_threshold_usd: float = 250_000.0
    orderbook_symbols: str = "BTCUSDT,ETHUSDT"
    orderbook_depth_levels: int = 20

    @property
    def orderbook_symbol_list(self) -> list[str]:
        return [s.strip().upper() for s in self.orderbook_symbols.split(",") if s.strip()]

    @property
    def watchlist_symbols(self) -> list[str]:
        return [s.strip().upper() for s in self.watchlist.split(",") if s.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()

from datetime import datetime

from sqlalchemy import JSON, TIMESTAMP, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.market import Base


class Backtest(Base):
    __tablename__ = "backtests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    strategy: Mapped[str] = mapped_column(String(40))
    symbol: Mapped[str] = mapped_column(String(20))
    interval: Mapped[str] = mapped_column(String(4))
    start: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    end: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(10), default="pending")  # pending|running|done|error
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    params_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # type: ignore[type-arg]
    metrics_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # type: ignore[type-arg]
    equity_json: Mapped[list | None] = mapped_column(JSON, nullable=True)  # type: ignore[type-arg]
    trades_json: Mapped[list | None] = mapped_column(JSON, nullable=True)  # type: ignore[type-arg]
    walkforward_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # type: ignore[type-arg]

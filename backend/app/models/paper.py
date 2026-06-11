from datetime import datetime

from sqlalchemy import JSON, TIMESTAMP, Float, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.market import Base


class PaperInstance(Base):
    __tablename__ = "paper_instances"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    name: Mapped[str] = mapped_column(String(60))
    strategy: Mapped[str] = mapped_column(String(40))
    symbol: Mapped[str] = mapped_column(String(20))
    interval: Mapped[str] = mapped_column(String(4))
    qty_usd: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(10), default="running")  # running|stopped
    params_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # type: ignore[type-arg]
    guards_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # type: ignore[type-arg]
    state_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # type: ignore[type-arg]


class PaperOrder(Base):
    __tablename__ = "paper_orders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    instance_id: Mapped[str] = mapped_column(String(36), index=True)
    ts: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())
    symbol: Mapped[str] = mapped_column(String(20))
    side: Mapped[str] = mapped_column(String(4))
    type: Mapped[str] = mapped_column(String(10), default="MARKET")
    qty: Mapped[float] = mapped_column(Float)
    price: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(10), default="filled")
    signal: Mapped[str | None] = mapped_column(String(200), nullable=True)
    testnet_order_id: Mapped[str | None] = mapped_column(String(40), nullable=True)


class PaperEquity(Base):
    __tablename__ = "paper_equity"

    instance_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    ts: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), primary_key=True)
    equity_usd: Mapped[float] = mapped_column(Float)
    position_qty: Mapped[float] = mapped_column(Float)
    price: Mapped[float] = mapped_column(Float)

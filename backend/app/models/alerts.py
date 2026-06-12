from datetime import datetime

from sqlalchemy import JSON, TIMESTAMP, Boolean, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.market import Base


class AlertRule(Base):
    __tablename__ = "alert_rules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    name: Mapped[str] = mapped_column(String(80))
    kind: Mapped[str] = mapped_column(String(20))
    symbol: Mapped[str | None] = mapped_column(String(20), nullable=True)
    params_json: Mapped[dict] = mapped_column(JSON)  # type: ignore[type-arg]
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    cooldown_s: Mapped[int] = mapped_column(Integer, default=300)
    state_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # type: ignore[type-arg]


class AlertEvent(Base):
    __tablename__ = "alert_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    rule_id: Mapped[str] = mapped_column(String(36), index=True)
    ts: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())
    message: Mapped[str] = mapped_column(String(300))
    payload_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # type: ignore[type-arg]

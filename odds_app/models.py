from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Index, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from odds_app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class OddsSnapshot(Base):
    __tablename__ = "odds_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(32), index=True)
    sport: Mapped[str] = mapped_column(String(32), index=True, default="soccer")
    league: Mapped[str | None] = mapped_column(String(128), nullable=True)
    external_event_id: Mapped[str] = mapped_column(String(128), index=True)
    home_team: Mapped[str] = mapped_column(String(128))
    away_team: Mapped[str] = mapped_column(String(128))
    kickoff_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    market_type: Mapped[str] = mapped_column(String(64), index=True)
    selection: Mapped[str] = mapped_column(String(128), index=True)
    odds_decimal: Mapped[Decimal] = mapped_column(Numeric(8, 3))
    scraped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    __table_args__ = (
        Index(
            "idx_odds_lookup",
            "source",
            "external_event_id",
            "market_type",
            "selection",
            "scraped_at",
        ),
    )


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    alert_type: Mapped[str] = mapped_column(String(32), index=True)
    source: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    sport: Mapped[str] = mapped_column(String(32), default="soccer")
    market_type: Mapped[str] = mapped_column(String(64), index=True)
    selection: Mapped[str] = mapped_column(String(128), index=True)
    home_team: Mapped[str] = mapped_column(String(128))
    away_team: Mapped[str] = mapped_column(String(128))
    kickoff_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    message: Mapped[str] = mapped_column(Text)
    details: Mapped[dict] = mapped_column(JSONB, default=dict)
    is_sent: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

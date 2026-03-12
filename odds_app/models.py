from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from odds_app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CanonicalMatch(Base):
    __tablename__ = "canonical_matches"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    sport: Mapped[str] = mapped_column(String(32), index=True, default="soccer")
    canonical_key: Mapped[str] = mapped_column(String(512), unique=True, index=True)
    home_team_norm: Mapped[str] = mapped_column(String(128), index=True)
    away_team_norm: Mapped[str] = mapped_column(String(128), index=True)
    display_home_team: Mapped[str] = mapped_column(String(128))
    display_away_team: Mapped[str] = mapped_column(String(128))
    kickoff_bucket_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class SourceEvent(Base):
    __tablename__ = "source_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    canonical_match_id: Mapped[int] = mapped_column(
        ForeignKey("canonical_matches.id", ondelete="CASCADE"), index=True
    )
    source: Mapped[str] = mapped_column(String(32), index=True)
    external_event_id: Mapped[str] = mapped_column(String(128), index=True)
    sport: Mapped[str] = mapped_column(String(32), index=True, default="soccer")
    league: Mapped[str | None] = mapped_column(String(128), nullable=True)
    home_team: Mapped[str] = mapped_column(String(128))
    away_team: Mapped[str] = mapped_column(String(128))
    kickoff_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    __table_args__ = (
        UniqueConstraint("source", "external_event_id", name="uq_source_event"),
        Index("idx_source_event_freshness", "source", "sport", "last_seen_at"),
        Index("idx_source_event_kickoff", "source", "sport", "kickoff_utc"),
    )


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
        Index("idx_odds_source_sport_scraped", "source", "sport", "scraped_at"),
        Index(
            "idx_odds_market_selection_scraped",
            "source",
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
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    is_sent: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("idx_alert_type_source_created", "alert_type", "source", "created_at"),
        Index("idx_alert_unsent_created", "is_sent", "created_at"),
    )


class ScrapeRun(Base):
    __tablename__ = "scrape_runs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(32), index=True)
    sport: Mapped[str] = mapped_column(String(32), index=True, default="soccer")
    trigger: Mapped[str] = mapped_column(String(16), default="scheduled")
    mode: Mapped[str] = mapped_column(String(16), default="primary")
    success: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    quotes_count: Mapped[int] = mapped_column(default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    duration_ms: Mapped[int] = mapped_column(default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        Index("idx_scrape_run_source_sport_started", "source", "sport", "started_at"),
        Index("idx_scrape_run_success_started", "success", "started_at"),
    )

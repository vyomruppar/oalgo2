"""SQLite persistence (SQLAlchemy 2.0; schema kept portable to PostgreSQL)."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, Text, UniqueConstraint, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from .config import get_settings


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Security(Base):
    __tablename__ = "securities"
    symbol: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(256))
    exchange: Mapped[str] = mapped_column(String(16))  # NASDAQ | NYSE (verified from Nasdaq Trader)
    listing_source: Mapped[str] = mapped_column(String(64))
    listing_as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    security_type: Mapped[str] = mapped_column(String(32))  # common | adr | excluded:<reason>
    eligible: Mapped[bool] = mapped_column(Boolean, default=False)
    exclusion_reason: Mapped[str | None] = mapped_column(String(128), nullable=True)
    cik: Mapped[str | None] = mapped_column(String(10), nullable=True)
    sic: Mapped[str | None] = mapped_column(String(8), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(128), nullable=True)
    sector: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_dollar_volume: Mapped[float | None] = mapped_column(Float, nullable=True)
    liquidity_as_of: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ScanRun(Base):
    __tablename__ = "scan_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="running")  # running | ok | failed
    stage: Mapped[str] = mapped_column(String(64), default="starting")
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    stats: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class StockResult(Base):
    """Latest research result per symbol (screen outcome, score, signal, full explanation payload)."""
    __tablename__ = "stock_results"
    symbol: Mapped[str] = mapped_column(String(16), primary_key=True)
    scan_id: Mapped[int] = mapped_column(Integer)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    price_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    screen_pass: Mapped[bool] = mapped_column(Boolean, default=False)
    screen_detail: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    signal: Mapped[str | None] = mapped_column(String(16), nullable=True)
    data_quality: Mapped[str | None] = mapped_column(String(8), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class ScoreHistory(Base):
    __tablename__ = "score_history"
    __table_args__ = (UniqueConstraint("symbol", "scan_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    scan_id: Mapped[int] = mapped_column(Integer)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    signal: Mapped[str | None] = mapped_column(String(16), nullable=True)


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    kind: Mapped[str] = mapped_column(String(32))
    severity: Mapped[str] = mapped_column(String(16), default="info")
    symbol: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(256))
    message: Mapped[str] = mapped_column(Text)
    dedup_key: Mapped[str] = mapped_column(String(128), index=True)
    state_hash: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    read: Mapped[bool] = mapped_column(Boolean, default=False)


class KV(Base):
    """Small JSON documents: settings, regime snapshot, ML report, backtest reports, breadth, etc."""
    __tablename__ = "kv"
    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class ProviderHealth(Base):
    __tablename__ = "provider_health"
    provider: Mapped[str] = mapped_column(String(32), primary_key=True)
    last_success: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_failure: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    success_count: Mapped[int] = mapped_column(Integer, default=0)
    failure_count: Mapped[int] = mapped_column(Integer, default=0)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)


class PaperTrade(Base):
    __tablename__ = "paper_trades"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    side: Mapped[str] = mapped_column(String(4))  # BUY | SELL
    quantity: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending | filled | rejected | cancelled
    requested_price_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    fill_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    fill_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    cost: Mapped[float] = mapped_column(Float, default=0.0)
    realized_pnl: Mapped[float | None] = mapped_column(Float, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class PaperPosition(Base):
    __tablename__ = "paper_positions"
    symbol: Mapped[str] = mapped_column(String(16), primary_key=True)
    quantity: Mapped[float] = mapped_column(Float)
    avg_cost: Mapped[float] = mapped_column(Float)
    opened_at: Mapped[str] = mapped_column(String(10))
    last_action_date: Mapped[str] = mapped_column(String(10))


class PaperEquity(Base):
    __tablename__ = "paper_equity"
    date: Mapped[str] = mapped_column(String(10), primary_key=True)
    cash: Mapped[float] = mapped_column(Float)
    positions_value: Mapped[float] = mapped_column(Float)
    equity: Mapped[float] = mapped_column(Float)
    benchmark_close: Mapped[float | None] = mapped_column(Float, nullable=True)


class Holding(Base):
    """A lot of a security the user actually owns. TRACKING ONLY: recording a holding never creates an order."""
    __tablename__ = "holdings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    shares: Mapped[float] = mapped_column(Float)
    cost: Mapped[float] = mapped_column(Float)            # price paid per share, as of the purchase date
    purchase_date: Mapped[str] = mapped_column(String(10))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class NewsItem(Base):
    __tablename__ = "news_items"
    __table_args__ = (UniqueConstraint("uuid", "symbol"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    uuid: Mapped[str] = mapped_column(String(64), index=True)
    symbol: Mapped[str] = mapped_column(String(16), index=True)   # the stock this headline was retrieved for
    title: Mapped[str] = mapped_column(Text)
    publisher: Mapped[str | None] = mapped_column(String(128), nullable=True)
    link: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    related: Mapped[list[str]] = mapped_column(JSON, default=list)
    relevance: Mapped[float] = mapped_column(Float, default=1.0)
    sentiment: Mapped[float | None] = mapped_column(Float, nullable=True)        # -1 (negative) .. +1 (positive)
    sentiment_label: Mapped[str | None] = mapped_column(String(16), nullable=True)
    engine: Mapped[str | None] = mapped_column(String(32), nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


_engine = None
_Session: sessionmaker[Session] | None = None


def init_db(url: str | None = None) -> None:
    global _engine, _Session
    url = url or get_settings().db_url
    _engine = create_engine(url, connect_args={"check_same_thread": False, "timeout": 30} if url.startswith("sqlite") else {})
    if url.startswith("sqlite") and ":memory:" not in url:
        with _engine.connect() as c:
            c.exec_driver_sql("PRAGMA journal_mode=WAL")
    Base.metadata.create_all(_engine)
    _Session = sessionmaker(_engine, expire_on_commit=False)


@contextmanager
def session() -> Iterator[Session]:
    if _Session is None:
        init_db()
    assert _Session is not None
    s = _Session()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


def kv_get(key: str, default: Any = None) -> Any:
    with session() as s:
        row = s.get(KV, key)
        return row.value if row is not None else default


def kv_set(key: str, value: Any) -> None:
    with session() as s:
        row = s.get(KV, key)
        if row is None:
            s.add(KV(key=key, value=value))
        else:
            row.value = value
            row.updated_at = utcnow()

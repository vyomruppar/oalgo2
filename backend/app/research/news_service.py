"""Fetch, score and store headlines; read them back with per-stock sentiment."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from sqlalchemy import select

from ..data.http import ProviderError
from ..data.news import YahooNews
from ..db import NewsItem, session, utcnow
from . import sentiment

log = logging.getLogger(__name__)
KEEP_DAYS = 21


def refresh(symbols: dict[str, str | None], ttl_seconds: float = 1800.0) -> dict[str, int]:
    """symbols: ticker -> company name. Fetch headlines, score the ones not seen before, store them."""
    provider = YahooNews()
    new_rows: list[dict[str, Any]] = []
    failed = 0
    for sym, company in symbols.items():
        try:
            items = provider.fetch(sym, company, ttl_seconds=ttl_seconds)
        except ProviderError as e:
            log.warning("news fetch failed for %s: %s", sym, e)
            failed += 1
            continue
        if not items:
            continue
        with session() as s:
            have = set(s.scalars(select(NewsItem.uuid).where(NewsItem.symbol == sym, NewsItem.uuid.in_([i["uuid"] for i in items]))).all())
        new_rows += [i for i in items if i["uuid"] not in have]
    if new_rows:
        engine = sentiment.get_engine()
        scores = engine.score([r["title"] for r in new_rows])
        with session() as s:
            for r, (sc, lab) in zip(new_rows, scores):
                s.add(NewsItem(**r, sentiment=sc, sentiment_label=lab, engine=engine.name))
    with session() as s:
        cutoff = utcnow() - timedelta(days=KEEP_DAYS)
        for old in s.scalars(select(NewsItem).where(NewsItem.published_at < cutoff)).all():
            s.delete(old)
    return {"new": len(new_rows), "failed": failed, "symbols": len(symbols)}


def _dict(n: NewsItem) -> dict[str, Any]:
    return {"uuid": n.uuid, "symbol": n.symbol, "title": n.title, "publisher": n.publisher, "link": n.link,
            "published_at": n.published_at, "related": n.related, "relevance": n.relevance, "sentiment": n.sentiment,
            "sentiment_label": n.sentiment_label, "engine": n.engine}


def items_for(symbols: list[str] | None = None, limit: int = 100, min_relevance: float = 0.0) -> list[dict[str, Any]]:
    with session() as s:
        stmt = select(NewsItem).where(NewsItem.relevance >= min_relevance)
        if symbols is not None:
            stmt = stmt.where(NewsItem.symbol.in_(symbols))
        return [_dict(n) for n in s.scalars(stmt.order_by(NewsItem.published_at.desc()).limit(limit)).all()]


def sentiment_by_symbol(symbols: list[str] | None = None) -> dict[str, dict[str, Any]]:
    by: dict[str, list[dict[str, Any]]] = {}
    for it in items_for(symbols, limit=5000):
        by.setdefault(it["symbol"], []).append(it)
    return {sym: sentiment.aggregate(items) for sym, items in by.items()}


def public(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    seen: dict[str, dict[str, Any]] = {}
    for it in items:       # the same story retrieved for several stocks is shown once, tagged with each
        if it["uuid"] in seen:
            seen[it["uuid"]]["symbols"].append(it["symbol"])
            continue
        row = {**it, "published_at": it["published_at"].isoformat(), "symbols": [it["symbol"]]}
        row.pop("symbol")
        seen[it["uuid"]] = row
        out.append(row)
    return out

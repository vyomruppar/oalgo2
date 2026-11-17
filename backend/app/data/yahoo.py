"""Daily OHLCV, dividends and splits from Yahoo's chart endpoint.

IMPORTANT LIMITATIONS (shown in the UI and documented in docs/data-providers.md):
  * unofficial endpoint, personal/research use only, may be rate limited or change without notice
  * end-of-day history; the latest bar during market hours is delayed and incomplete
  * no delisted securities -> any backtest on this data carries survivorship bias
"""
from __future__ import annotations

import json
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from ..config import get_settings
from .http import HttpProvider, ProviderError

CHART_URL = "https://query2.finance.yahoo.com/v8/finance/chart/{sym}?period1={p1}&period2={p2}&interval=1d&events=div%2Csplits"
SPARK_URL = "https://query2.finance.yahoo.com/v7/finance/spark?symbols={syms}&range=1mo&interval=1d"
NY = ZoneInfo("America/New_York")

INDEX_SYMBOLS = {"SP500": "^GSPC", "NASDAQ_COMPOSITE": "^IXIC", "NASDAQ_100": "^NDX", "VIX": "^VIX"}


def yahoo_symbol(symbol: str) -> str:
    return symbol.replace(".", "-")


def parse_chart(raw: bytes, now: datetime | None = None) -> tuple[pd.DataFrame, dict]:
    """Return (frame indexed by New York trading date with open/high/low/close/adj_close/volume/dividend/split, meta).

    Prices are split-adjusted by Yahoo; adj_close additionally adjusts for dividends (total-return series).
    Rows with missing or non-positive prices are dropped, never filled. The bar of a session that is
    still open (or closed less than 20 minutes ago) is dropped so that only completed days are stored.
    """
    d = json.loads(raw)
    err = d.get("chart", {}).get("error")
    if err:
        raise ProviderError("yahoo", f"chart error: {err}")
    res = d["chart"]["result"][0]
    meta = res.get("meta", {})
    ts = res.get("timestamp") or []
    if not ts:
        return pd.DataFrame(columns=["open", "high", "low", "close", "adj_close", "volume", "dividend", "split"]), meta
    q = res["indicators"]["quote"][0]
    adj = (res["indicators"].get("adjclose") or [{}])[0].get("adjclose") or q["close"]
    dates = [datetime.fromtimestamp(t, NY).date() for t in ts]
    df = pd.DataFrame({"open": q["open"], "high": q["high"], "low": q["low"], "close": q["close"],
                       "adj_close": adj, "volume": q["volume"]}, index=pd.to_datetime(dates))
    df = df.astype(float)
    df = df[~df.index.duplicated(keep="last")]
    df = df.dropna(subset=["open", "high", "low", "close"])
    df = df[(df[["open", "high", "low", "close"]] > 0).all(axis=1)]
    df["volume"] = df["volume"].fillna(0.0)
    df["dividend"] = 0.0
    df["split"] = 1.0
    ev = res.get("events", {})
    for e in (ev.get("dividends") or {}).values():
        dt = pd.Timestamp(datetime.fromtimestamp(e["date"], NY).date())
        if dt in df.index:
            df.loc[dt, "dividend"] = float(e["amount"])
    for e in (ev.get("splits") or {}).values():
        dt = pd.Timestamp(datetime.fromtimestamp(e["date"], NY).date())
        if dt in df.index and e.get("denominator"):
            df.loc[dt, "split"] = float(e["numerator"]) / float(e["denominator"])
    df.index.name = "date"
    df = df.sort_index()
    # Drop the bar of a session that has not closed yet: an in-progress bar has partial volume and a
    # "close" that is only the latest trade, so using it would mix intraday data into daily research.
    now = now or datetime.now(timezone.utc)
    reg_end = ((meta.get("currentTradingPeriod") or {}).get("regular") or {}).get("end")
    today_ny = now.astimezone(NY).date()
    if len(df) and df.index[-1].date() == today_ny:
        session_closed = reg_end is not None and now.timestamp() >= float(reg_end) + 20 * 60
        if not session_closed:
            df = df.iloc[:-1]
    return df, meta


def parse_spark(raw: bytes) -> dict[str, dict[str, float]]:
    """symbol -> {price, avg_volume, avg_dollar_volume} over the last month (liquidity pre-ranking)."""
    d = json.loads(raw)
    out: dict[str, dict[str, float]] = {}
    for item in d.get("spark", {}).get("result") or []:
        try:
            resp = item["response"][0]
            q = resp["indicators"]["quote"][0]
            close = np.array([c for c in q["close"] if c is not None], dtype=float)
            if close.size == 0:
                continue
            meta = resp["meta"]
            vol = float(meta.get("regularMarketVolume") or 0.0)
            out[item["symbol"]] = {"price": float(close[-1]), "avg_volume": vol,
                                   "avg_dollar_volume": float(close[-1]) * vol,
                                   "exchange_name": meta.get("fullExchangeName", "")}
        except (KeyError, IndexError, TypeError):
            continue
    return out


class YahooPrices:
    def __init__(self) -> None:
        st = get_settings()
        self.st = st
        self.http = HttpProvider("yahoo", rps=st.yahoo_rps, user_agent=st.http_user_agent)

    def path(self, symbol: str) -> Path:
        return self.st.prices_dir / f"{symbol.replace('^', '_IDX_')}.parquet"

    def load(self, symbol: str) -> pd.DataFrame | None:
        p = self.path(symbol)
        if not p.exists():
            return None
        return pd.read_parquet(p)

    def fetch(self, symbol: str, max_age_hours: float = 18.0) -> pd.DataFrame:
        """Fetch full daily history (re-downloaded whole so split/dividend adjustments stay consistent)."""
        p = self.path(symbol)
        if p.exists():
            age = time.time() - p.stat().st_mtime
            cached = pd.read_parquet(p)
            # Reuse the file only if it already holds the latest completed session. File age alone is
            # not enough: a file written this morning does not contain this afternoon's close.
            # The one-hour floor stops refetch loops on market holidays, when no new bar will appear.
            has_latest = len(cached) > 0 and cached.index[-1].date() >= last_completed_session()
            if age < max_age_hours * 3600 and (has_latest or age < 3600):
                return cached
        now = int(time.time())
        p1 = now - int(self.st.price_history_years * 365.25 * 86400)
        url = CHART_URL.format(sym=yahoo_symbol(symbol).replace("^", "%5E"), p1=p1, p2=now + 86400)
        df, _meta = parse_chart(self.http.get(url, ttl_seconds=0, allow_stale_on_error=False).content)
        if df.empty:
            raise ProviderError("yahoo", f"no price rows for {symbol}")
        df.to_parquet(p)
        return df

    def liquidity_snapshot(self, symbols: list[str], batch: int = 20, progress=None) -> dict[str, dict[str, float]]:
        out: dict[str, dict[str, float]] = {}
        back = {yahoo_symbol(s): s for s in symbols}
        ys = list(back)
        for i in range(0, len(ys), batch):
            chunk = ys[i:i + batch]
            if progress is not None and (i // batch) % 10 == 0:
                progress(i / max(len(ys), 1))
            try:
                raw = self.http.get(SPARK_URL.format(syms=",".join(chunk)), ttl_seconds=20 * 3600).content
            except ProviderError:
                continue
            for k, v in parse_spark(raw).items():
                if k in back:
                    out[back[k]] = v
        return out


def last_completed_session(now: datetime | None = None) -> "date":
    """Most recent weekday whose regular session (16:00 New York) ended at least 20 minutes ago.
    Exchange holidays are not modelled, so on a holiday this returns a date with no bar."""
    now_ny = (now or datetime.now(timezone.utc)).astimezone(NY)
    d = now_ny.date()
    if now_ny.hour * 60 + now_ny.minute < 16 * 60 + 20:
        d -= timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def last_bar_age_days(df: pd.DataFrame, now: datetime | None = None) -> int:
    now = now or datetime.now(timezone.utc)
    return int(np.busday_count(df.index[-1].date(), now.astimezone(NY).date()))

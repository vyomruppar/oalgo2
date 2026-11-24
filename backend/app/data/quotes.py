"""Live (delayed) quotes from Yahoo's batch spark endpoint.

Free quotes are delayed about 15 minutes. They are used for the price and today's change shown
on holdings and stock pages; scores, signals and backtests keep using stored end-of-day bars.
"""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from typing import Any

from ..config import get_settings
from .http import HttpProvider, ProviderError
from .yahoo import yahoo_symbol

URL = "https://query2.finance.yahoo.com/v7/finance/spark?symbols={syms}&range=1d&interval=1d"
BATCH = 20


def parse_quotes(raw: bytes) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for item in json.loads(raw).get("spark", {}).get("result") or []:
        try:
            m = item["response"][0]["meta"]
            price, prev, ts = m.get("regularMarketPrice"), m.get("chartPreviousClose"), m.get("regularMarketTime")
            if not price or not prev or not ts or price <= 0 or prev <= 0:
                continue
            reg = (m.get("currentTradingPeriod") or {}).get("regular") or {}
            open_now = bool(reg.get("start") and reg.get("end") and reg["start"] <= ts <= reg["end"]
                            and datetime.now(timezone.utc).timestamp() - ts < 20 * 60)
            out[item["symbol"]] = {"price": float(price), "prev_close": float(prev), "change": float(price - prev),
                                   "change_pct": float(price / prev - 1), "time": datetime.fromtimestamp(ts, timezone.utc).isoformat(),
                                   "volume": m.get("regularMarketVolume"), "market_open": open_now}
        except (KeyError, IndexError, TypeError):
            continue
    return out


# Last good quote per symbol, kept in memory. Yahoo throttles now and then (HTTP 429); a quote up to
# 15 minutes old is still a better answer than none, and its own timestamp tells the truth about its age.
_last_good: dict[str, tuple[float, dict[str, Any]]] = {}
_lock = threading.Lock()
KEEP_SECONDS = 15 * 60


class Quotes:
    def __init__(self) -> None:
        st = get_settings()
        self.http = HttpProvider("yahoo_quotes", rps=st.yahoo_rps, user_agent=st.http_user_agent, max_retries=4)

    def get(self, symbols: list[str], ttl_seconds: float = 20.0) -> dict[str, dict[str, Any]]:
        back = {yahoo_symbol(s): s for s in symbols}
        out: dict[str, dict[str, Any]] = {}
        ys = list(back)
        for i in range(0, len(ys), BATCH):
            chunk = ys[i:i + BATCH]
            try:
                raw = self.http.get(URL.format(syms=",".join(chunk)), ttl_seconds=ttl_seconds, allow_stale_on_error=False).content
            except ProviderError:
                continue
            for k, v in parse_quotes(raw).items():
                if k in back:
                    out[back[k]] = v
                    with _lock:
                        _last_good[back[k]] = (time.time(), v)
        with _lock:
            for sym in symbols:
                if sym not in out and sym in _last_good and time.time() - _last_good[sym][0] < KEEP_SECONDS:
                    out[sym] = _last_good[sym][1]
        return out

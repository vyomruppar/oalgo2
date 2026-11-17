"""Company news headlines from Yahoo Finance's search endpoint (unofficial, same host as prices).

Headlines only: title, publisher, time and link. Article text is not retrieved, so sentiment is a
reading of the headline, not of the article. A search for a ticker also returns market round-ups that
merely mention it, so every item carries a relevance weight.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from ..config import get_settings
from .http import HttpProvider
from .yahoo import yahoo_symbol

SEARCH_URL = "https://query2.finance.yahoo.com/v1/finance/search?q={sym}&newsCount={n}&quotesCount=0"
_STOP = {"inc", "corp", "corporation", "company", "co", "ltd", "limited", "plc", "holdings", "group", "the", "class", "common",
         "stock", "ordinary", "shares", "new", "sa", "nv", "ag", "american", "depositary", "and"}


def name_tokens(company: str | None) -> list[str]:
    """Distinctive words of a company name ('Micron Technology, Inc. - Common Stock' -> ['micron', 'technology'])."""
    if not company:
        return []
    words = re.findall(r"[a-z0-9&']+", company.lower().split(" - ")[0])
    return [w for w in words if w not in _STOP and len(w) > 2][:3]


def relevance(title: str, symbol: str, company: str | None, related: list[str]) -> float:
    """1.0 when the headline names the company or ticker; otherwise diluted by how many tickers it tags."""
    t = title.lower()
    toks = name_tokens(company)
    if (toks and toks[0] in t) or re.search(rf"\b{re.escape(symbol.lower())}\b", t):
        return 1.0
    n = max(len(related), 1)
    return round(max(0.15, min(0.6, 1.5 / n)), 3)


def parse_search(raw: bytes, symbol: str, company: str | None = None) -> list[dict[str, Any]]:
    d = json.loads(raw)
    out: list[dict[str, Any]] = []
    for x in d.get("news") or []:
        title, uuid, ts = x.get("title"), x.get("uuid"), x.get("providerPublishTime")
        if not title or not uuid or not ts:
            continue
        related = [str(r) for r in (x.get("relatedTickers") or [])]
        out.append({"uuid": str(uuid), "symbol": symbol, "title": str(title).strip(), "publisher": x.get("publisher"),
                    "link": x.get("link"), "published_at": datetime.fromtimestamp(int(ts), timezone.utc),
                    "related": related, "relevance": relevance(str(title), symbol, company, related)})
    return out


class YahooNews:
    def __init__(self) -> None:
        st = get_settings()
        self.http = HttpProvider("yahoo_news", rps=st.yahoo_rps, user_agent=st.http_user_agent)

    def fetch(self, symbol: str, company: str | None = None, count: int = 12, ttl_seconds: float = 1800.0) -> list[dict[str, Any]]:
        url = SEARCH_URL.format(sym=yahoo_symbol(symbol), n=count)
        return parse_search(self.http.get(url, ttl_seconds).content, symbol, company)

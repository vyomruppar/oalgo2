"""SEC EDGAR provider: ticker->CIK map, company submissions (SIC, filings) and XBRL company facts.

All fundamentals are kept point-in-time: every fact carries the date it was `filed`, and research code may
only use facts filed on or before the analysis date.

Fair access: SEC asks for <=10 requests/second and a declared User-Agent. www.sec.gov rejects clients
without a contact string, so the ticker map has a fallback that uses only data.sec.gov.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from ..config import get_settings
from .http import HttpProvider, ProviderError

log = logging.getLogger(__name__)

TICKERS_URL = "https://www.sec.gov/files/company_tickers_exchange.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
FRAME_URL = "https://data.sec.gov/api/xbrl/frames/us-gaap/Assets/USD/{period}.json"

DAY = 86400.0


@dataclass(frozen=True)
class CompanyProfile:
    cik: str
    name: str
    sic: str | None
    industry: str | None
    tickers: list[str]
    exchanges: list[str]
    filings: list[dict[str, Any]]  # recent filings: form, filingDate, reportDate, accession, primaryDocument, url


def norm_ticker(t: str) -> str:
    """SEC uses BRK-B, Nasdaq Trader uses BRK.B; normalise to the dash form."""
    return t.upper().replace(".", "-").replace("/", "-")


def parse_tickers_exchange(raw: bytes) -> dict[str, str]:
    d = json.loads(raw)
    fields = d["fields"]
    ci, ti = fields.index("cik"), fields.index("ticker")
    return {norm_ticker(row[ti]): f"{int(row[ci]):010d}" for row in d["data"] if row[ti]}


def parse_submissions(raw: bytes) -> CompanyProfile:
    d = json.loads(raw)
    cik = f"{int(d['cik']):010d}"
    rec = d.get("filings", {}).get("recent", {})
    filings = []
    n = len(rec.get("form", []))
    for i in range(n):
        acc = rec["accessionNumber"][i]
        doc = rec["primaryDocument"][i]
        filings.append({
            "form": rec["form"][i],
            "filing_date": rec["filingDate"][i],
            "report_date": rec["reportDate"][i] or None,
            "accession": acc,
            "description": rec.get("primaryDocDescription", [""] * n)[i],
            "url": f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace('-', '')}/{doc}" if doc else None,
        })
    return CompanyProfile(
        cik=cik, name=d.get("name", ""), sic=d.get("sic") or None, industry=d.get("sicDescription") or None,
        tickers=[norm_ticker(t) for t in d.get("tickers", [])], exchanges=list(d.get("exchanges", [])), filings=filings,
    )


class SecEdgar:
    def __init__(self) -> None:
        st = get_settings()
        self.http = HttpProvider("sec_edgar", rps=st.sec_rps, user_agent=st.sec_user_agent, timeout=90.0)

    def ticker_map(self) -> dict[str, str]:
        """ticker -> zero-padded CIK. Primary: www.sec.gov file. Fallback: crawl data.sec.gov."""
        try:
            return parse_tickers_exchange(self.http.get(TICKERS_URL, 7 * DAY).content)
        except ProviderError as e:
            log.warning("www.sec.gov ticker file unavailable (%s); using data.sec.gov fallback. "
                        "Set OALGO_SEC_USER_AGENT to a contact string to enable the direct file.", e)
            return self._ticker_map_fallback()

    def _ticker_map_fallback(self) -> dict[str, str]:
        cache = self.http.cache_dir / "ticker_map_fallback.json"
        import time
        if cache.exists() and time.time() - cache.stat().st_mtime < 14 * DAY:
            return json.loads(cache.read_text())
        ciks: set[str] = set()
        from datetime import date
        today = date.today()
        y, q = today.year, (today.month - 1) // 3 + 1
        got = 0
        for _ in range(6):  # walk back through recent quarters and union the filers
            q -= 1
            if q == 0:
                y, q = y - 1, 4
            try:
                d = json.loads(self.http.get(FRAME_URL.format(period=f"CY{y}Q{q}I"), 7 * DAY).content)
            except ProviderError:
                continue
            ciks.update(f"{int(r['cik']):010d}" for r in d.get("data", []))
            got += 1
            if got >= 3:
                break
        out: dict[str, str] = {}
        for cik in sorted(ciks):
            try:
                prof = self.profile(cik)
            except ProviderError:
                continue
            for t in prof.tickers:
                out.setdefault(t, cik)
        if out:
            cache.write_text(json.dumps(out))
        return out

    def profile(self, cik: str) -> CompanyProfile:
        return parse_submissions(self.http.get(SUBMISSIONS_URL.format(cik=cik), 3 * DAY).content)

    def company_facts(self, cik: str, ttl_seconds: float = 3 * DAY) -> dict[str, Any]:
        return json.loads(self.http.get(FACTS_URL.format(cik=cik), ttl_seconds).content)


# --- SIC -> broad sector (SIC-based grouping, not GICS; documented in docs/limitations.md) -----------------
def sic_to_sector(sic: str | None) -> str:
    if not sic or not sic.isdigit():
        return "Unknown"
    c = int(sic)
    if c in (2833, 2834, 2835, 2836, 3826, 3841, 3842, 3843, 3844, 3845, 3851, 8731) or 8000 <= c <= 8099:
        return "Health Care"
    if 3570 <= c <= 3579 or 3660 <= c <= 3679 or c in (3559, 3825, 3827, 3829) or 7370 <= c <= 7379:
        return "Technology"
    if 4800 <= c <= 4899 or c in (2711, 2721, 2731, 2741, 7812, 7819, 7822, 7829, 7830, 7841):
        return "Communication Services"
    if 4900 <= c <= 4999:
        return "Utilities"
    if c == 6798 or 6500 <= c <= 6599:
        return "Real Estate"
    if 6000 <= c <= 6799:
        return "Financials"
    if 1000 <= c <= 1499 and not (1300 <= c <= 1399) or 2600 <= c <= 2699 or 2800 <= c <= 2899 or 3300 <= c <= 3399:
        return "Materials"
    if 1300 <= c <= 1399 or 2900 <= c <= 2999 or 4600 <= c <= 4699:
        return "Energy"
    if 100 <= c <= 999 or 2000 <= c <= 2199 or 5400 <= c <= 5499 or c in (2840, 2842, 2844, 5140, 5141, 5150, 5912):
        return "Consumer Staples"
    if 5000 <= c <= 5999 or 2200 <= c <= 2399 or 2500 <= c <= 2599 or 3700 <= c <= 3716 or 7000 <= c <= 7299 or 7800 <= c <= 7999 or 3900 <= c <= 3999 or 5800 <= c <= 5899:
        return "Consumer Discretionary"
    if 1500 <= c <= 1799 or 3400 <= c <= 3599 or 3600 <= c <= 3659 or 3720 <= c <= 3799 or 4000 <= c <= 4599 or 4700 <= c <= 4799 or 7300 <= c <= 7399 or 8700 <= c <= 8799:
        return "Industrials"
    return "Other"

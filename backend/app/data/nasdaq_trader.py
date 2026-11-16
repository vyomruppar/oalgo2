"""Exchange-listing verification from the Nasdaq Trader symbol directory.

Sources (public, refreshed nightly by Nasdaq):
  nasdaqlisted.txt - all Nasdaq-listed securities
  otherlisted.txt  - securities listed on other exchanges (NYSE = 'N', NYSE American = 'A',
                     NYSE Arca = 'P', Cboe BZX = 'Z', IEX = 'V')
Only Nasdaq and NYSE ('N') listings are eligible. OTC securities never appear in these files.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from ..config import get_settings
from .http import HttpProvider

NASDAQ_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
OTHER_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"

_EXCLUDE_NAME_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("warrant", re.compile(r"\bwarrants?\b", re.I)),
    ("unit", re.compile(r"\bunits?\b", re.I)),
    ("right", re.compile(r"\brights?\b", re.I)),
    ("preferred", re.compile(r"\bpreferred\b|\bpreference\b|\bdepositary shares? .*(preferred|interest in)", re.I)),
    ("note_or_debt", re.compile(r"\bnotes?\b due|\bdebentures?\b|\bsenior notes?\b|\bsubordinated\b|% notes|\bbonds?\b|\bdue \d{4}\b|\bseries due\b", re.I)),
    ("blank_check_spac", re.compile(r"\bacquisition (corp|corporation|company|co)\b|\bblank check\b", re.I)),
    ("fund_or_trust", re.compile(r"\bETN\b|\bETF\b|\bclosed[- ]end\b|\bfund\b|\btrust units\b|beneficial interest", re.I)),
    ("when_issued", re.compile(r"when[- ]issued", re.I)),
]


@dataclass(frozen=True)
class Listing:
    symbol: str
    name: str
    exchange: str  # NASDAQ | NYSE
    security_type: str  # common | adr | excluded
    eligible: bool
    exclusion_reason: str | None
    source: str
    as_of: datetime


def _file_time(lines: list[str]) -> datetime:
    for line in reversed(lines):
        m = re.match(r"File Creation Time:\s*(\d{8})(\d{2}):(\d{2})", line)
        if m:
            return datetime.strptime(m.group(1) + m.group(2) + m.group(3), "%m%d%Y%H%M").replace(tzinfo=ZoneInfo("America/New_York")).astimezone(timezone.utc)
    return datetime.now(timezone.utc)


def classify(symbol: str, name: str, is_etf: bool, is_test: bool, financial_status: str | None = None) -> tuple[str, bool, str | None]:
    """Return (security_type, eligible, exclusion_reason) for an exchange-listed security."""
    if is_test:
        return "excluded", False, "test issue"
    if is_etf:
        return "excluded", False, "exchange-traded fund"
    if not re.fullmatch(r"[A-Z]{1,5}([.\-][A-Z])?", symbol):
        return "excluded", False, "non-standard symbol (warrant/unit/preferred suffix)"
    for reason, pat in _EXCLUDE_NAME_PATTERNS:
        if pat.search(name):
            return "excluded", False, f"security type: {reason}"
    if financial_status and financial_status not in ("N", ""):
        # D=deficient, E=delinquent, Q=bankrupt, G/H/J/K combos
        return "excluded", False, f"Nasdaq financial status flag '{financial_status}' (deficient/delinquent/bankrupt)"
    if re.search(r"american depositary|\bADS\b|\bADR\b", name, re.I):
        return "adr", True, None
    return "common", True, None


def parse_nasdaq_listed(text: str) -> list[Listing]:
    lines = [ln for ln in text.splitlines() if ln.strip()]
    as_of = _file_time(lines)
    header = lines[0].split("|")
    idx = {h: i for i, h in enumerate(header)}
    out: list[Listing] = []
    for ln in lines[1:]:
        if ln.startswith("File Creation Time"):
            continue
        f = ln.split("|")
        if len(f) < len(header):
            continue
        sym, name = f[idx["Symbol"]].strip(), f[idx["Security Name"]].strip()
        stype, ok, why = classify(sym, name, f[idx["ETF"]] == "Y", f[idx["Test Issue"]] == "Y", f[idx["Financial Status"]])
        out.append(Listing(sym, name, "NASDAQ", stype, ok, why, "nasdaqtrader.com/nasdaqlisted.txt", as_of))
    return out


def parse_other_listed(text: str) -> list[Listing]:
    """Keep only NYSE ('N'). Other venues in this file are reported as excluded with a reason."""
    lines = [ln for ln in text.splitlines() if ln.strip()]
    as_of = _file_time(lines)
    header = lines[0].split("|")
    idx = {h: i for i, h in enumerate(header)}
    out: list[Listing] = []
    for ln in lines[1:]:
        if ln.startswith("File Creation Time"):
            continue
        f = ln.split("|")
        if len(f) < len(header):
            continue
        sym, name, exch = f[idx["ACT Symbol"]].strip(), f[idx["Security Name"]].strip(), f[idx["Exchange"]].strip()
        if exch != "N":
            continue  # not NYSE: out of scope by requirement, never enters the universe table
        stype, ok, why = classify(sym, name, f[idx["ETF"]] == "Y", f[idx["Test Issue"]] == "Y")
        out.append(Listing(sym, name, "NYSE", stype, ok, why, "nasdaqtrader.com/otherlisted.txt", as_of))
    return out


class NasdaqTrader:
    def __init__(self) -> None:
        self.http = HttpProvider("nasdaq_trader", rps=1.0, user_agent=get_settings().http_user_agent)

    def listings(self, ttl_seconds: float = 12 * 3600) -> list[Listing]:
        a = self.http.get(NASDAQ_LISTED_URL, ttl_seconds).content.decode("utf-8", "replace")
        b = self.http.get(OTHER_LISTED_URL, ttl_seconds).content.decode("utf-8", "replace")
        return parse_nasdaq_listed(a) + parse_other_listed(b)

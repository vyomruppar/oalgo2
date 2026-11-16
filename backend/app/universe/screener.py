"""Configurable stock screener. Every rule records pass/fail, the observed value and the threshold."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field


class ScreenConfig(BaseModel):
    min_price: float = Field(5.0, ge=0, description="Minimum share price (USD)")
    min_market_cap: float = Field(300e6, ge=0, description="Minimum market capitalisation (USD)")
    min_adv_dollar: float = Field(5e6, ge=0, description="Minimum 63-day average daily dollar volume (USD)")
    min_history_bars: int = Field(252, ge=1, description="Minimum daily bars of trading history")
    max_volatility: float = Field(1.0, gt=0, description="Maximum 1-year annualised volatility")
    require_fundamentals: bool = Field(True, description="Require SEC XBRL fundamentals filed in the last 200 days")
    excluded_sectors: list[str] = Field(default_factory=list)
    max_stale_bars: int = Field(4, ge=0, description="Maximum age of the last price bar in business days")


def _rule(name: str, passed: bool, value: Any, threshold: Any, detail: str) -> dict[str, Any]:
    if isinstance(value, (float, np.floating)):
        value = None if not np.isfinite(value) else float(value)
    return {"rule": name, "passed": bool(passed), "value": value, "threshold": threshold, "detail": detail}


def screen_row(row: pd.Series, cfg: ScreenConfig, price_issues: list[dict] | None = None, bar_age: int | None = None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []

    def num(k: str) -> float:
        v = row.get(k)
        return float(v) if v is not None and np.isfinite(v) else float("nan")

    def ge(name: str, key: str, thr: float, label: str, fmt: str = "{:,.2f}") -> None:
        v = num(key)
        if not np.isfinite(v):
            out.append(_rule(name, False, None, thr, f"{label} unavailable"))
        else:
            ok = v >= thr
            out.append(_rule(name, ok, v, thr, f"{label} {fmt.format(v)} {'>=' if ok else '<'} minimum {fmt.format(thr)}"))

    ge("min_price", "price", cfg.min_price, "price")
    if bool(row.get("share_count_unreliable", False)):
        out.append(_rule("min_market_cap", False, None, cfg.min_market_cap,
                         "market cap unavailable: reported share count is not usable (multi-class share structure)"))
    else:
        ge("min_market_cap", "market_cap", cfg.min_market_cap, "market cap", "{:,.0f}")
    ge("min_adv_dollar", "adv_dollar_63", cfg.min_adv_dollar, "63-day avg dollar volume", "{:,.0f}")
    ge("min_history", "n_bars", cfg.min_history_bars, "bars of history", "{:,.0f}")
    v = num("vol_252")
    if not np.isfinite(v):
        out.append(_rule("max_volatility", False, None, cfg.max_volatility, "1-year volatility unavailable (insufficient history)"))
    else:
        ok = v <= cfg.max_volatility
        out.append(_rule("max_volatility", ok, v, cfg.max_volatility, f"1-year volatility {v:.0%} {'<=' if ok else '>'} maximum {cfg.max_volatility:.0%}"))
    if cfg.require_fundamentals:
        has = np.isfinite(num("assets")) and np.isfinite(num("net_income_ttm"))
        out.append(_rule("fundamentals_available", has, None, None,
                         "recent SEC XBRL fundamentals available" if has else
                         "no usable us-gaap fundamentals filed in the last 200 days (IFRS filer, new listing, or late filer)"))
    sector = row.get("sector") or "Unknown"
    ok = sector not in cfg.excluded_sectors
    out.append(_rule("sector", ok, sector, cfg.excluded_sectors, f"sector {sector} {'allowed' if ok else 'excluded by configuration'}"))
    errs = [i for i in (price_issues or []) if i.get("severity") == "error" and i.get("code") != "stale"]
    out.append(_rule("price_data_quality", not errs, None, None,
                     "price data passed validation" if not errs else "; ".join(i["detail"] for i in errs)))
    if bar_age is not None:
        ok = bar_age <= cfg.max_stale_bars
        out.append(_rule("fresh_prices", ok, bar_age, cfg.max_stale_bars,
                         f"last price bar is {bar_age} business days old" + ("" if ok else " (stale)")))
    return out


def passes(detail: list[dict[str, Any]]) -> bool:
    return all(r["passed"] for r in detail)


def eligibility_mask(panel: pd.DataFrame, cfg: ScreenConfig) -> pd.Series:
    """Vectorised point-in-time version of the screen for backtests (same thresholds, no freshness rule)."""
    m = ((panel["price"] >= cfg.min_price) & (panel["market_cap"] >= cfg.min_market_cap)
         & (panel["adv_dollar_63"] >= cfg.min_adv_dollar) & (panel["n_bars"] >= cfg.min_history_bars)
         & (panel["vol_252"] <= cfg.max_volatility))
    if cfg.require_fundamentals:
        m &= panel["assets"].notna() & panel["net_income_ttm"].notna()
    if cfg.excluded_sectors:
        m &= ~panel["sector"].isin(cfg.excluded_sectors)
    return m.fillna(False)

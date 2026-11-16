"""Explainable signal classification. Deterministic rules on top of the score; the rules can return
NO_ACTION when the evidence is insufficient. Nothing here places or routes an order."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .scoring import ScoreConfig, contributions

SIGNALS = ["STRONG BUY", "BUY", "HOLD", "SELL", "WATCHLIST", "NO_ACTION"]
HOLDING_PERIOD = "1-3 months (the factor composite is re-ranked monthly)"
HOLD_DAYS = 63


def ordinal(x: float) -> str:
    n = int(round(x))
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _f(row: pd.Series, k: str) -> float:
    v = row.get(k)
    try:
        return float(v) if v is not None and np.isfinite(v) else float("nan")
    except (TypeError, ValueError):
        return float("nan")


def red_flags(row: pd.Series, price_issues: list[dict] | None = None) -> list[dict[str, Any]]:
    """Diagnostic warnings. These are screens, not proof of distress or manipulation."""
    flags: list[dict[str, Any]] = []

    def add(code: str, severity: str, text: str) -> None:
        flags.append({"code": code, "severity": severity, "text": text})

    z = _f(row, "altman_z")
    if np.isfinite(z) and z < 1.81:
        add("altman_distress", "severe", f"Altman Z-score {z:.2f} is in the distress zone (< 1.81)")
    p, pn = _f(row, "piotroski"), _f(row, "piotroski_n")
    if np.isfinite(p) and pn >= 6 and p <= 2:
        add("piotroski_weak", "severe", f"Piotroski F-score {p:.0f} of {pn:.0f} evaluated signals")
    a = _f(row, "accruals")
    if np.isfinite(a) and a > 0.10:
        add("high_accruals", "warn", f"Accruals are {a:.0%} of assets: earnings are not backed by operating cash flow")
    nd = _f(row, "net_debt_to_ebitda")
    if np.isfinite(nd) and nd > 5 and row.get("sector") not in ("Financials", "Real Estate", "Utilities"):
        add("high_leverage", "warn", f"Net debt is {nd:.1f}x EBITDA")
    ic = _f(row, "interest_coverage")
    if np.isfinite(ic) and ic < 1.5:
        add("weak_coverage", "severe", f"Operating income covers interest only {ic:.1f}x")
    ni, fcf = _f(row, "net_income_ttm"), _f(row, "fcf_ttm")
    if np.isfinite(ni) and np.isfinite(fcf) and ni < 0 and fcf < 0:
        add("burning_cash", "warn", "Negative trailing net income and negative free cash flow")
    sbc = _f(row, "sbc_to_revenue")
    if np.isfinite(sbc) and sbc > 0.20:
        add("heavy_sbc", "warn", f"Stock-based compensation is {sbc:.0%} of revenue (dilution risk)")
    dsf = _f(row, "days_since_filing")
    if np.isfinite(dsf) and dsf > 150:
        add("stale_fundamentals", "warn", f"Latest periodic filing is {dsf:.0f} days old")
    vol = _f(row, "vol_252")
    if np.isfinite(vol) and vol > 0.70:
        add("high_volatility", "warn", f"1-year annualised volatility {vol:.0%}")
    for i in price_issues or []:
        add(f"price_{i['code']}", "severe" if i["severity"] == "error" else "warn", f"Price data: {i['detail']}")
    return flags


def classify(row: pd.Series, cfg: ScoreConfig, regime: str, flags: list[dict[str, Any]]) -> tuple[str, list[str]]:
    """Return (signal, gates) where gates lists the reasons a stronger signal was withheld."""
    score, dq = _f(row, "score"), row.get("data_quality", "D")
    gates: list[str] = []
    if not np.isfinite(score) or dq == "D":
        return "NO_ACTION", ["insufficient data to form a view (data quality D)"]
    severe = [f for f in flags if f["severity"] == "severe"]
    above_200 = bool(_f(row, "price") > _f(row, "sma_200")) if np.isfinite(_f(row, "sma_200")) else False
    if score <= cfg.sell or (severe and score < 45):
        return "SELL", gates
    if score >= cfg.buy:
        if severe:
            gates.append("severe financial red flag: " + severe[0]["text"])
        if not above_200:
            gates.append("price is below its 200-day average (trend not confirmed)")
        if dq == "C":
            gates.append("data quality C: several score components are missing")
        if regime == "risk_off":
            gates.append("market regime is risk-off")
        if gates:
            return "WATCHLIST", gates
        if score >= cfg.strong_buy and dq == "A" and regime == "risk_on" and not flags:
            return "STRONG BUY", gates
        if score >= cfg.strong_buy:
            gates.append("STRONG BUY withheld: requires data quality A, risk-on regime and no warnings")
        return "BUY", gates
    return "HOLD", gates


def build_payload(symbol: str, sec: dict[str, Any], row: pd.Series, cfg: ScoreConfig, regime: dict[str, Any],
                  flags: list[dict[str, Any]], signal: str, gates: list[str], atr: float | None,
                  strategy_perf: dict[str, Any] | None, next_report: dict[str, Any] | None,
                  price_date: str, sources: list[dict[str, Any]]) -> dict[str, Any]:
    price = _f(row, "price")
    vol = _f(row, "vol_252")
    contrib = contributions(row, cfg)
    ranked = sorted([c for c in contrib if c["component_score"] is not None], key=lambda c: c["component_score"], reverse=True)
    reasons = [f"{c['label']}: {ordinal(c['component_score'])} percentile" for c in ranked if c["component_score"] >= 65][:4]
    weak = [f"{c['label']}: {ordinal(c['component_score'])} percentile" for c in ranked[::-1] if c["component_score"] <= 35][:4]
    stop = price - 2.5 * atr if atr and np.isfinite(atr) else None
    sma50, sma200 = _f(row, "sma_50"), _f(row, "sma_200")
    entry, exit_, invalid = [], [], []
    if signal in ("STRONG BUY", "BUY"):
        entry.append(f"Research entry reference: next session open after {price_date} (paper trades fill at that open plus modelled costs)")
        if np.isfinite(sma50):
            entry.append(f"Prefer entries while price holds above the 50-day average ({sma50:.2f})")
    elif signal == "WATCHLIST":
        entry += [f"Becomes actionable if: {g}" + " is resolved" for g in gates]
    if stop is not None:
        exit_.append(f"Volatility stop reference: {stop:.2f} (2.5 x 14-day ATR of {atr:.2f} below {price:.2f})")
    exit_.append(f"Score falls below 50 at a monthly re-rank (now {_f(row, 'score'):.0f})")
    if np.isfinite(sma200):
        exit_.append(f"Daily close below the 200-day average ({sma200:.2f})")
    invalid.append("A new severe financial red flag (distress-zone Altman Z, interest coverage below 1.5x, Piotroski <= 2)")
    invalid.append("Market regime turns risk-off")
    invalid.append("The next periodic filing materially changes trailing earnings or cash flow")
    scen = None
    if np.isfinite(vol) and np.isfinite(price):
        s = vol * np.sqrt(HOLD_DAYS / 252)
        scen = {
            "basis": f"Historical 1-year volatility of {vol:.0%} scaled to {HOLD_DAYS} trading days. A dispersion range, not a forecast or a probability of profit.",
            "one_sigma_down": price * float(np.exp(-s)), "one_sigma_up": price * float(np.exp(s)),
            "two_sigma_down": price * float(np.exp(-2 * s)), "two_sigma_up": price * float(np.exp(2 * s)),
            "worst_drawdown_1y": _f(row, "max_dd_252") if np.isfinite(_f(row, "max_dd_252")) else None,
        }

    def g(k: str) -> float | None:
        v = _f(row, k)
        return v if np.isfinite(v) else None

    return {
        "symbol": symbol, "company": sec.get("name"), "exchange": sec.get("exchange"),
        "exchange_verification": {"source": sec.get("listing_source"), "as_of": sec.get("listing_as_of")},
        "sector": row.get("sector"), "industry": sec.get("industry"),
        "price": price, "price_date": price_date, "price_freshness": "end_of_day (delayed; not real-time)",
        "score": g("score"), "data_quality": row.get("data_quality"), "coverage": g("coverage"),
        "signal": signal, "gates": gates,
        "score_note": "The score ranks stocks on evidence-backed characteristics. It is not a probability of profit.",
        "components": contrib,
        "technical_checks": row.get("technical_checks", []),
        "reasons": reasons or ["No component stands out; the score reflects average readings"],
        "weaknesses": weak,
        "red_flags": flags,
        "entry_conditions": entry, "exit_conditions": exit_, "invalidation": invalid,
        "holding_period": HOLDING_PERIOD,
        "scenarios": scen,
        "risk": {"volatility_1y": g("vol_252"), "volatility_3m": g("vol_63"), "max_drawdown_1y": g("max_dd_252"),
                 "atr_14": atr if atr and np.isfinite(atr) else None, "adv_dollar_63": g("adv_dollar_63"),
                 "stop_reference": stop, "stop_distance_pct": (stop / price - 1) if stop else None},
        "market_regime": regime.get("regime"),
        "strategy_performance": strategy_perf,
        "upcoming_events": [next_report] if next_report else [],
        "fundamentals": {k: g(k) for k in [
            "market_cap", "enterprise_value", "pe", "pb", "ps", "ev_ebitda", "earnings_yield", "ebit_ev", "fcf_yield",
            "book_to_market", "shareholder_yield", "revenue_ttm", "net_income_ttm", "operating_income_ttm", "fcf_ttm",
            "ocf_ttm", "gross_margin", "operating_margin", "net_margin", "roe", "roa", "roic", "gross_profitability",
            "accruals", "asset_growth", "revenue_growth", "revenue_growth_q", "earnings_growth", "current_ratio",
            "debt_to_equity", "net_debt_to_ebitda", "interest_coverage", "piotroski", "piotroski_n", "altman_z", "sue",
            "mom_12_1", "mom_6_1", "ret_1m", "dist_52w_high", "days_since_filing"]},
        "factor_z": {k: g(f"{k}_z") for k in ["value", "quality", "momentum", "earnings", "low_vol", "investment", "financial_strength", "size", "reversal"]},
        "sources": sources,
    }


def estimate_next_report(filings: list[dict[str, Any]], today: str) -> dict[str, Any] | None:
    """Estimate the next 10-Q/10-K date from the same filing one year earlier. Labelled as an estimate:
    the free data sources carry no confirmed earnings calendar."""
    periodic = sorted([f for f in filings if f["form"] in ("10-Q", "10-K")], key=lambda f: f["filing_date"])
    if len(periodic) < 5:
        return None
    t = pd.Timestamp(today)
    for f in periodic:
        cand = pd.Timestamp(f["filing_date"]) + pd.Timedelta(days=364)
        if cand > t and (cand - t).days <= 120:
            return {"type": f"{f['form']} filing (estimated)", "date": cand.date().isoformat(), "confirmed": False,
                    "basis": f"Same report was filed on {f['filing_date']} last year (SEC EDGAR). Not a confirmed date."}
    return None

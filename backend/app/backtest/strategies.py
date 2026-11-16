"""Strategy definitions. Each strategy carries a documented hypothesis and turns the point-in-time
factor panel into target weights at monthly rebalance dates. Parameters are fixed a priori (not
optimised on the test data); the classification says what the literature supports."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd

MULTIFACTOR_WEIGHTS = {"value": 20, "quality": 15, "momentum": 20, "earnings": 10, "low_vol": 10, "investment": 5, "financial_strength": 5}


@dataclass(frozen=True)
class Strategy:
    key: str
    name: str
    family: str
    evidence: str       # evidence-backed | needs validation | benchmark
    hypothesis: str
    definition: str
    ranker: Callable[[pd.DataFrame], pd.Series]  # cross-section -> score (higher = more attractive); NaN = not eligible
    risk_filter: bool = False                    # move to cash when the market index is below its 200-day average


def _col(name: str) -> Callable[[pd.DataFrame], pd.Series]:
    return lambda c: c[name]


def _multifactor(c: pd.DataFrame) -> pd.Series:
    w = pd.Series(MULTIFACTOR_WEIGHTS, dtype=float)
    vals = c[w.index]
    used = vals.notna().mul(w, axis=1).sum(axis=1)
    score = vals.fillna(0).mul(w, axis=1).sum(axis=1) / used.where(used >= 0.6 * w.sum())
    return score


def _trend(c: pd.DataFrame) -> pd.Series:
    return c["mom_12_1"].where((c["price"] > c["sma_200"]) & (c["mom_12_1"] > 0))


def _ma_cross(c: pd.DataFrame) -> pd.Series:
    return c["adv_dollar_63"].where(c["sma_50"] > c["sma_200"])


def _breakout(c: pd.DataFrame) -> pd.Series:
    return c["dist_52w_high"].where(c["dist_52w_high"] >= -0.03)


STRATEGIES: list[Strategy] = [
    Strategy("multifactor", "Multifactor composite", "Factor investing", "evidence-backed",
             "Combining value, quality, momentum, earnings momentum, low volatility and conservative investment diversifies across independently documented premia.",
             "Top-N by weighted average of sector-neutral factor z-scores (weights 20/15/20/10/10/5/5), equal-weighted, monthly.", _multifactor),
    Strategy("value", "Value", "Factor investing", "evidence-backed",
             "Stocks that are cheap relative to earnings, cash flow and book value have earned higher average returns (Fama-French 1992; Lakonishok et al. 1994).",
             "Top-N by composite of earnings yield, EBIT/EV, book-to-market and FCF yield (sector-neutral).", _col("value")),
    Strategy("momentum", "Cross-sectional momentum", "Momentum and trend", "evidence-backed",
             "Past 6-12 month winners continue to outperform over the next months (Jegadeesh-Titman 1993).",
             "Top-N by 12-1 and 6-1 month total return.", _col("momentum")),
    Strategy("quality", "Quality / profitability", "Factor investing", "evidence-backed",
             "Profitable firms with cash-backed earnings outperform (Novy-Marx 2013; Sloan 1996; Piotroski 2000).",
             "Top-N by composite of gross profitability, ROIC, low accruals and Piotroski score.", _col("quality")),
    Strategy("low_vol", "Low volatility", "Factor investing", "evidence-backed",
             "Low-risk stocks have earned higher risk-adjusted returns than high-risk stocks (Ang et al. 2006; Frazzini-Pedersen 2014).",
             "Top-N by lowest 1-year realised volatility.", _col("low_vol")),
    Strategy("investment", "Conservative investment", "Factor investing", "evidence-backed",
             "Firms that grow assets slowly outperform aggressive investors (Cooper et al. 2008; Fama-French CMA).",
             "Top-N by lowest year-on-year asset growth.", _col("investment")),
    Strategy("earnings", "Earnings momentum (PEAD)", "Momentum and trend", "evidence-backed",
             "Prices drift in the direction of earnings surprises for weeks after the announcement (Bernard-Thomas 1989).",
             "Top-N by standardised unexpected earnings (seasonal random walk) and quarterly revenue growth.", _col("earnings")),
    Strategy("reversal", "Short-term reversal", "Mean reversion", "needs validation",
             "Last month's losers rebound (Jegadeesh 1990); the effect is small in liquid stocks and very sensitive to costs.",
             "Top-N by lowest prior 1-month return.", _col("reversal")),
    Strategy("trend", "Trend following with market filter", "Momentum and trend", "evidence-backed",
             "Assets in an uptrend tend to stay in an uptrend; stepping aside in downtrends cuts drawdowns (Moskowitz et al. 2012).",
             "Top-N 12-1 momentum among stocks above their 200-day average with positive momentum; cash when the index is below its 200-day average.",
             _trend, risk_filter=True),
    Strategy("ma_cross", "50/200 moving-average crossover", "Momentum and trend", "needs validation",
             "A 50-day average above the 200-day average marks an uptrend.",
             "N most liquid stocks whose 50-day average is above the 200-day average, equal-weighted.", _ma_cross),
    Strategy("breakout", "52-week-high breakout", "Momentum and trend", "needs validation",
             "Stocks trading near their 52-week high continue higher (George-Hwang 2004).",
             "Top-N closest to (within 3% of) the 52-week high.", _breakout),
]
STRATEGY_BY_KEY = {s.key: s for s in STRATEGIES}


def build_targets(strategy: Strategy, panel: pd.DataFrame, factors: pd.DataFrame, top_n: int = 30,
                  index_above_200: pd.Series | None = None, max_weight: float = 0.10) -> dict[pd.Timestamp, pd.Series]:
    """Equal-weight the top-N ranked eligible names on each rebalance date. `factors` is indexed like
    `panel` restricted to eligible rows; rows absent from `factors` are not eligible."""
    data = factors.join(panel[["price", "sma_50", "sma_200", "mom_12_1", "adv_dollar_63", "dist_52w_high"]], how="left")
    out: dict[pd.Timestamp, pd.Series] = {}
    for dt, cross in data.groupby(level="date"):
        c = cross.droplevel("date")
        if strategy.risk_filter and index_above_200 is not None:
            flag = index_above_200.reindex([dt]).iloc[0] if dt in index_above_200.index else np.nan
            if flag is False or flag == 0:
                out[dt] = pd.Series(dtype=float)
                continue
        score = strategy.ranker(c).dropna()
        pick = score.nlargest(top_n)
        if pick.empty:
            out[dt] = pd.Series(dtype=float)
            continue
        w = min(1.0 / top_n, max_weight)   # fewer than N qualifiers -> remainder stays in cash
        out[dt] = pd.Series(w, index=pick.index)
    return out


def equal_weight_universe(factors: pd.DataFrame) -> dict[pd.Timestamp, pd.Series]:
    out = {}
    for dt, cross in factors.groupby(level="date"):
        syms = cross.droplevel("date").index
        out[dt] = pd.Series(1.0 / len(syms), index=syms)
    return out

"""Rule-based market regime (risk-on / neutral / risk-off) from index trend, realised volatility,
implied volatility (VIX) and universe breadth. Transparent by design; HMM/GARCH regimes are deferred."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def regime_series(index_close: pd.Series, vix: pd.Series | None = None) -> pd.DataFrame:
    """Historical regime from index data only (causal; usable in backtests)."""
    c = index_close.dropna()
    sma200 = c.rolling(200, min_periods=200).mean()
    sma50 = c.rolling(50, min_periods=50).mean()
    rv = np.log(c).diff().rolling(21, min_periods=21).std() * np.sqrt(252)
    rv_pct = rv.rolling(1260, min_periods=252).rank(pct=True)
    score = pd.Series(0.0, index=c.index)
    score += np.where(c > sma200, 1.0, -1.0)
    score += np.where(sma50 > sma200, 0.5, -0.5)
    score += np.where(rv_pct > 0.8, -1.0, np.where(rv_pct < 0.5, 0.5, 0.0))
    if vix is not None:
        v = vix.reindex(c.index).ffill()
        score += np.where(v > 30, -1.0, np.where(v < 18, 0.5, 0.0))
    score = score.where(sma200.notna())
    label = pd.Series(np.where(score >= 1.0, "risk_on", np.where(score <= -1.0, "risk_off", "neutral")), index=c.index).where(score.notna())
    return pd.DataFrame({"close": c, "sma_50": sma50, "sma_200": sma200, "realized_vol_21": rv, "realized_vol_pct": rv_pct,
                         "score": score, "regime": label})


def breadth_series(close: pd.DataFrame, adj: pd.DataFrame) -> pd.DataFrame:
    """Universe breadth: % of stocks above their 50/200-day SMA, advancers minus decliners, new highs/lows."""
    valid = close.notna()
    n = valid.sum(axis=1).replace(0, np.nan)
    sma50, sma200 = close.rolling(50, min_periods=50).mean(), close.rolling(200, min_periods=200).mean()
    ret = adj.pct_change(fill_method=None)
    adv, dec = (ret > 0).sum(axis=1), (ret < 0).sum(axis=1)
    hi = (close >= close.rolling(252, min_periods=200).max()).sum(axis=1)
    lo = (close <= close.rolling(252, min_periods=200).min()).sum(axis=1)
    return pd.DataFrame({
        "pct_above_50": (close > sma50).sum(axis=1) / sma50.notna().sum(axis=1).replace(0, np.nan) * 100,
        "pct_above_200": (close > sma200).sum(axis=1) / sma200.notna().sum(axis=1).replace(0, np.nan) * 100,
        "advancers": adv, "decliners": dec, "ad_line": (adv - dec).cumsum(),
        "new_highs": hi, "new_lows": lo, "n": n,
    })


def current_regime(index_close: pd.Series, vix: pd.Series | None, breadth: pd.DataFrame | None) -> dict[str, Any]:
    rs = regime_series(index_close, vix).dropna(subset=["score"])
    if rs.empty:
        return {"regime": "unknown", "score": None, "components": [], "as_of": None}
    last = rs.iloc[-1]
    score = float(last["score"])
    comps = [
        {"name": "Index vs 200-day average", "value": float(last["close"] / last["sma_200"] - 1), "reading": "above" if last["close"] > last["sma_200"] else "below"},
        {"name": "50-day vs 200-day average", "value": float(last["sma_50"] / last["sma_200"] - 1), "reading": "above" if last["sma_50"] > last["sma_200"] else "below"},
        {"name": "21-day realised volatility (annualised)", "value": float(last["realized_vol_21"]),
         "reading": f"{float(last['realized_vol_pct']):.0%} percentile of the last 5 years" if np.isfinite(last["realized_vol_pct"]) else "n/a"},
    ]
    if vix is not None and not vix.dropna().empty:
        comps.append({"name": "VIX", "value": float(vix.dropna().iloc[-1]), "reading": "implied volatility index level"})
    if breadth is not None and not breadth.dropna(subset=["pct_above_200"]).empty:
        b = float(breadth["pct_above_200"].dropna().iloc[-1])
        comps.append({"name": "Stocks above 200-day average", "value": b / 100.0, "reading": "universe breadth"})
        score += 0.5 if b > 60 else (-0.5 if b < 40 else 0.0)
    regime = "risk_on" if score >= 1.0 else ("risk_off" if score <= -1.0 else "neutral")
    return {"regime": regime, "score": score, "components": comps, "as_of": rs.index[-1].date().isoformat(),
            "method": "rule-based: trend, volatility percentile, VIX level, breadth"}


REGIME_COMPONENT_SCORE = {"risk_on": 70.0, "neutral": 50.0, "risk_off": 25.0, "unknown": 50.0}

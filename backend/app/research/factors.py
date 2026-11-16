"""Factor construction: winsorised, sector-neutral z-scores combined into composites.

Each composite averages z-scores of related metrics so that correlated inputs are counted once.
Definitions follow the literature where possible (references in research-wiki/quantitative-factors.md).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# composite -> list of (column, sign). sign=+1: higher is better.
FACTOR_DEFS: dict[str, list[tuple[str, int]]] = {
    "value": [("earnings_yield", 1), ("ebit_ev", 1), ("book_to_market", 1), ("fcf_yield", 1)],
    "momentum": [("mom_12_1", 1), ("mom_6_1", 1)],
    "quality": [("gross_profitability", 1), ("roic", 1), ("accruals", -1), ("piotroski", 1)],
    "investment": [("asset_growth", -1)],
    "low_vol": [("vol_252", -1)],
    "earnings": [("sue", 1), ("revenue_growth_q", 1)],
    "size": [("log_mcap", -1)],
    "reversal": [("ret_1m", -1)],
    "financial_strength": [("interest_coverage", 1), ("net_debt_to_ebitda", -1), ("current_ratio", 1)],
}
# factors computed within sector (accounting ratios differ structurally by industry)
SECTOR_NEUTRAL = {"value", "quality", "investment", "financial_strength", "earnings"}
MIN_GROUP = 5


def winsorize(s: pd.Series, lo: float = 0.02, hi: float = 0.98) -> pd.Series:
    v = s.dropna()
    if v.empty:
        return s
    a, b = v.quantile(lo), v.quantile(hi)
    return s.clip(a, b)


def zscore(s: pd.Series) -> pd.Series:
    s = winsorize(s.replace([np.inf, -np.inf], np.nan))
    sd = s.std(ddof=0)
    if not np.isfinite(sd) or sd == 0:
        return pd.Series(np.nan, index=s.index).where(s.isna(), 0.0)
    return (s - s.mean()) / sd


def sector_zscore(s: pd.Series, sector: pd.Series) -> pd.Series:
    """z-score within sector; sectors with fewer than MIN_GROUP valid names fall back to the whole universe."""
    overall = zscore(s)
    out = overall.copy()
    for _, idx in sector.groupby(sector).groups.items():
        grp = s.loc[idx]
        if grp.notna().sum() >= MIN_GROUP:
            out.loc[idx] = zscore(grp)
    return out


def factor_scores(cross: pd.DataFrame) -> pd.DataFrame:
    """Composite factor z-scores for one cross-section (index = symbol). Adds `<factor>` and
    `<factor>_n` (number of non-missing inputs) columns."""
    out = pd.DataFrame(index=cross.index)
    sector = cross["sector"] if "sector" in cross.columns else pd.Series("Unknown", index=cross.index)
    for name, parts in FACTOR_DEFS.items():
        zs = []
        for col, sign in parts:
            if col not in cross.columns:
                continue
            x = cross[col].astype(float)
            z = sector_zscore(x, sector) if name in SECTOR_NEUTRAL else zscore(x)
            zs.append(sign * z)
        if not zs:
            out[name], out[f"{name}_n"] = np.nan, 0
            continue
        zdf = pd.concat(zs, axis=1)
        out[name] = zdf.mean(axis=1, skipna=True)
        out[f"{name}_n"] = zdf.notna().sum(axis=1)
    return out


def percentile(s: pd.Series) -> pd.Series:
    """Cross-sectional percentile rank 0-100 (NaN stays NaN)."""
    return s.rank(pct=True, method="average") * 100.0


def panel_factor_scores(panel: pd.DataFrame, eligible: pd.Series | None = None) -> pd.DataFrame:
    """Apply factor_scores date by date over a [date, symbol] panel, restricted to `eligible` rows."""
    frames = []
    for dt, cross in panel.groupby(level="date"):
        c = cross.droplevel("date")
        if eligible is not None:
            c = c[eligible.loc[dt].reindex(c.index).fillna(False).to_numpy()]
        if len(c) < 10:
            continue
        fs = factor_scores(c)
        fs.index = pd.MultiIndex.from_product([[dt], fs.index], names=["date", "symbol"])
        frames.append(fs)
    return pd.concat(frames) if frames else pd.DataFrame()


def greenblatt_rank(cross: pd.DataFrame) -> pd.Series:
    """Magic-formula combined rank (lower = better): rank(EBIT/EV) + rank(return on capital).
    Return on capital uses ROIC here (Greenblatt uses EBIT / (net working capital + net fixed assets));
    financials and utilities are excluded as in the original."""
    ok = ~cross["sector"].isin(["Financials", "Utilities", "Real Estate"])
    ey = cross["ebit_ev"].where(ok).rank(ascending=False)
    roc = cross["roic"].where(ok).rank(ascending=False)
    return (ey + roc).rank()

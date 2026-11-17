"""Portfolio risk analytics for a set of positions (paper portfolio or a hypothetical basket)."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.covariance import LedoitWolf

from ..backtest import metrics as M


def ledoit_wolf_cov(returns: pd.DataFrame) -> pd.DataFrame:
    """Ledoit-Wolf shrinkage covariance of daily returns (rows with any missing value are dropped)."""
    x = returns.dropna()
    if len(x) < 30 or x.shape[1] == 0:
        return pd.DataFrame(np.nan, index=returns.columns, columns=returns.columns)
    lw = LedoitWolf().fit(x.to_numpy())
    return pd.DataFrame(lw.covariance_, index=returns.columns, columns=returns.columns)


def risk_contributions(weights: pd.Series, cov: pd.DataFrame) -> pd.DataFrame:
    """Component risk: RC_i = w_i (Sigma w)_i / sigma_p; percentages sum to 1."""
    w = weights.reindex(cov.index).fillna(0.0).to_numpy()
    sigma = cov.to_numpy()
    port_var = float(w @ sigma @ w)
    if port_var <= 0 or not np.isfinite(port_var):
        return pd.DataFrame({"weight": weights, "risk_contribution": np.nan, "risk_pct": np.nan})
    mrc = sigma @ w / np.sqrt(port_var)
    rc = w * mrc
    return pd.DataFrame({"weight": w, "risk_contribution": rc * np.sqrt(252), "risk_pct": rc / np.sqrt(port_var)}, index=cov.index)


def vol_scaled_size(vol: float, equity: float, price: float, risk_budget: float = 0.01, max_weight: float = 0.10,
                    adv_dollar: float | None = None, max_adv_pct: float = 0.05) -> dict[str, Any]:
    """Position size such that a one-standard-deviation monthly move costs `risk_budget` of equity,
    capped by max weight and by a share of average daily dollar volume."""
    if not (np.isfinite(vol) and vol > 0 and price > 0 and equity > 0):
        return {"weight": 0.0, "shares": 0, "binding": "insufficient data"}
    monthly = vol * np.sqrt(21 / 252)
    w = risk_budget / monthly
    binding = "risk budget"
    if w > max_weight:
        w, binding = max_weight, "maximum position weight"
    if adv_dollar and np.isfinite(adv_dollar) and w * equity > max_adv_pct * adv_dollar:
        w, binding = max_adv_pct * adv_dollar / equity, "liquidity (share of average daily volume)"
    return {"weight": float(w), "shares": int(w * equity / price), "notional": float(w * equity), "binding": binding,
            "monthly_vol": float(monthly)}


def analyze(positions: pd.DataFrame, adj: pd.DataFrame, bench: pd.Series | None, sectors: dict[str, str],
            atr: dict[str, float] | None = None, adv_dollar: dict[str, float] | None = None, cash: float = 0.0,
            lookback: int = 252) -> dict[str, Any]:
    """`positions`: index symbol, columns quantity, price. Returns exposures, VaR/CVaR, risk contributions,
    correlation, stop-loss and gap scenarios, liquidity. Empty portfolios return an explicit empty report."""
    if positions is None or positions.empty:
        return {"empty": True, "message": "No open positions."}
    val = positions["quantity"] * positions["price"]
    equity = float(val.sum() + cash)
    w = val / equity
    rets = adj[w.index.intersection(adj.columns)].pct_change(fill_method=None).tail(lookback)
    w_in = w.reindex(rets.columns).fillna(0.0)
    port = (rets.fillna(0.0) * w_in).sum(axis=1)
    cov = ledoit_wolf_cov(rets)
    rc = risk_contributions(w_in, cov)
    corr = rets.corr()
    pairs = []
    cols = list(corr.columns)
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            c = corr.iloc[i, j]
            if np.isfinite(c) and c >= 0.7:
                pairs.append({"a": cols[i], "b": cols[j], "correlation": float(c)})
    sector_w = w.groupby(pd.Series({s: sectors.get(s, "Unknown") for s in w.index})).sum().sort_values(ascending=False)
    out: dict[str, Any] = {
        "empty": False, "equity": equity, "cash": cash, "cash_weight": cash / equity if equity else None,
        "n_positions": int(len(w)), "gross_exposure": float(w.sum()),
        "concentration": {"largest_weight": float(w.max()), "top5_weight": float(w.nlargest(5).sum()), "hhi": float(((w / w.sum()) ** 2).sum()),
                          # concentration among invested positions (weights renormalised to exclude cash)
                          "effective_positions": float(1.0 / ((w / w.sum()) ** 2).sum()) if w.sum() > 0 else None},
        "sector_exposure": [{"sector": k, "weight": float(v)} for k, v in sector_w.items()],
        "volatility": M.ann_vol(port), "max_drawdown": M.max_drawdown(port), "calmar": M.calmar(port),
        "var_95": M.var_cvar(port, 0.95), "var_99": M.var_cvar(port, 0.99),
        "risk_contributions": [{"symbol": s, "weight": float(r.weight), "risk_pct": None if not np.isfinite(r.risk_pct) else float(r.risk_pct)}
                               for s, r in rc.sort_values("risk_pct", ascending=False).iterrows()],
        "correlation": {"symbols": cols, "matrix": corr.round(3).where(corr.notna(), None).values.tolist()},
        "correlated_pairs": sorted(pairs, key=lambda p: -p["correlation"])[:20],
        "basis": f"Positions held at current weights over the last {len(port)} trading days (historical simulation, not a forecast).",
    }
    if bench is not None:
        b = bench.pct_change().reindex(port.index)
        out.update({k: v for k, v in M.alpha_beta(port, b).items() if k in ("alpha", "beta", "r2")})
    scen = []
    for s in w.index:
        px, q = float(positions.loc[s, "price"]), float(positions.loc[s, "quantity"])
        a = (atr or {}).get(s)
        r = rets[s].dropna() if s in rets else pd.Series(dtype=float)
        worst = float(r.min()) if len(r) else None
        adv = (adv_dollar or {}).get(s)
        scen.append({"symbol": s, "weight": float(w[s]),
                     "stop_loss_pct_of_equity": float(-2.5 * a * q / equity) if a and np.isfinite(a) else None,
                     "worst_day_1y": worst, "gap_loss_pct_of_equity": float(worst * w[s]) if worst is not None else None,
                     "days_to_liquidate": float(px * q / (0.1 * adv)) if adv and adv > 0 else None})
    out["position_scenarios"] = scen
    stops = [x["stop_loss_pct_of_equity"] for x in scen if x["stop_loss_pct_of_equity"] is not None]
    out["all_stops_hit_pct_of_equity"] = float(sum(stops)) if stops else None
    warnings = []
    if w.max() > 0.15:
        warnings.append(f"Largest position is {w.max():.0%} of equity")
    if len(sector_w) and sector_w.iloc[0] > 0.35:
        warnings.append(f"{sector_w.index[0]} is {sector_w.iloc[0]:.0%} of equity")
    if pairs:
        warnings.append(f"{len(pairs)} position pairs have correlation above 0.70")
    out["warnings"] = warnings
    return {k: (None if isinstance(v, float) and not np.isfinite(v) else v) for k, v in out.items()}

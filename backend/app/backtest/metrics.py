"""Performance and risk metrics on daily return series. Formulas are documented in
research-wiki/portfolio-and-risk.md; every function is unit-tested against hand calculations."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

TD = 252


def total_return(r: pd.Series) -> float:
    return float((1 + r).prod() - 1)


def cagr(r: pd.Series, periods: int = TD) -> float:
    n = len(r)
    if n == 0:
        return float("nan")
    growth = float((1 + r).prod())
    return growth ** (periods / n) - 1 if growth > 0 else -1.0


def ann_vol(r: pd.Series, periods: int = TD) -> float:
    return float(r.std(ddof=1) * np.sqrt(periods)) if len(r) > 1 else float("nan")


def sharpe(r: pd.Series, rf: pd.Series | float = 0.0, periods: int = TD) -> float:
    """Annualised Sharpe = mean(excess) / std(excess) * sqrt(periods)."""
    ex = r - rf
    sd = ex.std(ddof=1)
    return float(ex.mean() / sd * np.sqrt(periods)) if sd and np.isfinite(sd) and sd > 0 else float("nan")


def downside_deviation(r: pd.Series, mar: float = 0.0, periods: int = TD) -> float:
    d = np.minimum(r - mar, 0.0)
    return float(np.sqrt((d ** 2).mean()) * np.sqrt(periods)) if len(r) else float("nan")


def sortino(r: pd.Series, rf: pd.Series | float = 0.0, periods: int = TD) -> float:
    ex = r - rf
    dd = downside_deviation(ex, 0.0, periods)
    return float(ex.mean() * periods / dd) if dd and dd > 0 else float("nan")


def drawdown_series(r: pd.Series) -> pd.Series:
    eq = (1 + r).cumprod()
    return eq / eq.cummax().clip(lower=1.0) - 1


def max_drawdown(r: pd.Series) -> float:
    return float(drawdown_series(r).min()) if len(r) else float("nan")


def calmar(r: pd.Series) -> float:
    mdd = max_drawdown(r)
    return float(cagr(r) / abs(mdd)) if mdd < 0 else float("nan")


def var_cvar(r: pd.Series, level: float = 0.95) -> dict[str, float]:
    """One-day historical and parametric (normal) VaR/CVaR, reported as positive loss fractions."""
    x = r.dropna().to_numpy()
    if x.size < 30:
        return {"hist_var": float("nan"), "hist_cvar": float("nan"), "param_var": float("nan"), "param_cvar": float("nan")}
    q = np.quantile(x, 1 - level)
    tail = x[x <= q]
    mu, sd = x.mean(), x.std(ddof=1)
    z = stats.norm.ppf(1 - level)
    return {"hist_var": float(-q), "hist_cvar": float(-tail.mean()),
            "param_var": float(-(mu + z * sd)), "param_cvar": float(-(mu - sd * stats.norm.pdf(z) / (1 - level)))}


def alpha_beta(r: pd.Series, bench: pd.Series, rf: pd.Series | float = 0.0, periods: int = TD) -> dict[str, float]:
    """CAPM regression of excess returns: r - rf = alpha + beta (b - rf) + e. Alpha is annualised."""
    df = pd.concat([r - rf, bench - rf], axis=1).dropna()
    if len(df) < 30 or df.iloc[:, 1].var() == 0:
        return {"alpha": float("nan"), "beta": float("nan"), "alpha_t": float("nan"), "r2": float("nan")}
    y, x = df.iloc[:, 0].to_numpy(), df.iloc[:, 1].to_numpy()
    X = np.column_stack([np.ones_like(x), x])
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ coef
    s2 = resid @ resid / (len(y) - 2)
    cov = s2 * np.linalg.inv(X.T @ X)
    r2 = 1 - (resid @ resid) / ((y - y.mean()) @ (y - y.mean()))
    return {"alpha": float(coef[0] * periods), "beta": float(coef[1]), "alpha_t": float(coef[0] / np.sqrt(cov[0, 0])), "r2": float(r2)}


def information_ratio(r: pd.Series, bench: pd.Series, periods: int = TD) -> dict[str, float]:
    act = (r - bench).dropna()
    te = act.std(ddof=1) * np.sqrt(periods)
    return {"tracking_error": float(te), "information_ratio": float(act.mean() * periods / te) if te > 0 else float("nan"),
            "active_return": float(act.mean() * periods)}


def trade_stats(trades: pd.DataFrame) -> dict[str, Any]:
    """Round-trip statistics from a frame with a `pnl_pct` column (one row per closed position)."""
    if trades is None or trades.empty:
        return {"n_trades": 0, "win_rate": None, "avg_win": None, "avg_loss": None, "profit_factor": None, "avg_hold_days": None}
    p = trades["pnl_pct"]
    wins, losses = p[p > 0], p[p <= 0]
    gross_w = float((trades.loc[p > 0, "pnl"]).sum()) if "pnl" in trades else float(wins.sum())
    gross_l = float(-(trades.loc[p <= 0, "pnl"]).sum()) if "pnl" in trades else float(-losses.sum())
    return {"n_trades": int(len(p)), "win_rate": float((p > 0).mean()),
            "avg_win": float(wins.mean()) if len(wins) else None, "avg_loss": float(losses.mean()) if len(losses) else None,
            "profit_factor": float(gross_w / gross_l) if gross_l > 0 else None,
            "avg_hold_days": float(trades["hold_days"].mean()) if "hold_days" in trades else None}


def summarize(r: pd.Series, bench: pd.Series | None = None, rf: pd.Series | float = 0.0) -> dict[str, Any]:
    r = r.dropna()
    if isinstance(rf, pd.Series):
        rf = rf.reindex(r.index).fillna(0.0)
    out: dict[str, Any] = {
        "start": r.index[0].date().isoformat() if len(r) else None, "end": r.index[-1].date().isoformat() if len(r) else None,
        "days": int(len(r)), "total_return": total_return(r), "cagr": cagr(r), "volatility": ann_vol(r),
        "sharpe": sharpe(r, rf), "sortino": sortino(r, rf), "max_drawdown": max_drawdown(r), "calmar": calmar(r),
        **{f"{k}_95": v for k, v in var_cvar(r, 0.95).items()},
    }
    if bench is not None:
        b = bench.reindex(r.index)
        out.update(alpha_beta(r, b, rf))
        out.update(information_ratio(r, b))
        out["benchmark_total_return"] = total_return(b.dropna())
        out["benchmark_cagr"] = cagr(b.dropna())
        out["excess_cagr"] = out["cagr"] - out["benchmark_cagr"]
    return {k: (None if isinstance(v, float) and not np.isfinite(v) else v) for k, v in out.items()}

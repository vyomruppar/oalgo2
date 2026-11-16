"""Statistical validation: block-bootstrap confidence intervals, Deflated Sharpe Ratio,
Benjamini-Hochberg false-discovery control. References in research-wiki/statistical-validation.md."""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

EULER_GAMMA = 0.5772156649015329


def stationary_bootstrap_indices(n: int, mean_block: float, rng: np.random.Generator) -> np.ndarray:
    """Politis-Romano stationary bootstrap: blocks of geometric length with mean `mean_block`."""
    idx = np.empty(n, dtype=np.int64)
    p = 1.0 / mean_block
    idx[0] = rng.integers(n)
    jumps = rng.random(n) < p
    starts = rng.integers(n, size=n)
    for i in range(1, n):
        idx[i] = starts[i] if jumps[i] else (idx[i - 1] + 1) % n
    return idx


def bootstrap_sharpe_ci(r: pd.Series, n_boot: int = 1000, mean_block: float = 21.0, level: float = 0.95,
                        periods: int = 252, seed: int = 7) -> dict[str, float]:
    x = r.dropna().to_numpy()
    if x.size < 60:
        return {"lo": float("nan"), "hi": float("nan"), "p_le_zero": float("nan")}
    rng = np.random.default_rng(seed)
    out = np.empty(n_boot)
    for b in range(n_boot):
        s = x[stationary_bootstrap_indices(x.size, mean_block, rng)]
        sd = s.std(ddof=1)
        out[b] = s.mean() / sd * np.sqrt(periods) if sd > 0 else 0.0
    a = (1 - level) / 2
    return {"lo": float(np.quantile(out, a)), "hi": float(np.quantile(out, 1 - a)), "p_le_zero": float((out <= 0).mean())}


def probabilistic_sharpe(sr: float, n: int, skew: float, kurt: float, sr_benchmark: float = 0.0) -> float:
    """PSR (Bailey & Lopez de Prado 2012). `sr` and `sr_benchmark` are per-period (not annualised);
    `kurt` is the non-excess kurtosis (3 for a normal distribution)."""
    denom = np.sqrt(max(1e-12, 1 - skew * sr + (kurt - 1) / 4.0 * sr ** 2))
    return float(stats.norm.cdf((sr - sr_benchmark) * np.sqrt(n - 1) / denom))


def expected_max_sharpe(var_trials: float, n_trials: int) -> float:
    """Expected maximum Sharpe ratio among `n_trials` unskilled strategies (Bailey & Lopez de Prado 2014)."""
    if n_trials <= 1 or var_trials <= 0:
        return 0.0
    return float(np.sqrt(var_trials) * ((1 - EULER_GAMMA) * stats.norm.ppf(1 - 1.0 / n_trials)
                                        + EULER_GAMMA * stats.norm.ppf(1 - 1.0 / (n_trials * np.e))))


def deflated_sharpe(r: pd.Series, trial_sharpes_per_period: list[float]) -> dict[str, float]:
    """DSR = PSR evaluated against the expected best Sharpe of the strategies that were tried."""
    x = r.dropna().to_numpy()
    if x.size < 60 or x.std(ddof=1) == 0:
        return {"dsr": float("nan"), "sr0_annual": float("nan"), "n_trials": len(trial_sharpes_per_period)}
    sr = x.mean() / x.std(ddof=1)
    sr0 = expected_max_sharpe(float(np.var(trial_sharpes_per_period, ddof=1)) if len(trial_sharpes_per_period) > 1 else 0.0,
                              len(trial_sharpes_per_period))
    return {"dsr": probabilistic_sharpe(sr, x.size, float(stats.skew(x)), float(stats.kurtosis(x, fisher=False)), sr0),
            "sr0_annual": float(sr0 * np.sqrt(252)), "n_trials": len(trial_sharpes_per_period)}


def benjamini_hochberg(pvalues: dict[str, float], q: float = 0.10) -> dict[str, dict[str, float | bool]]:
    """BH step-up procedure. Returns adjusted p-values and rejection flags at FDR level q."""
    items = [(k, p) for k, p in pvalues.items() if p is not None and np.isfinite(p)]
    m = len(items)
    out: dict[str, dict[str, float | bool]] = {k: {"p": float("nan"), "p_adj": float("nan"), "significant": False} for k in pvalues}
    if m == 0:
        return out
    items.sort(key=lambda kv: kv[1])
    adj = [min(1.0, p * m / (i + 1)) for i, (_, p) in enumerate(items)]
    for i in range(m - 2, -1, -1):
        adj[i] = min(adj[i], adj[i + 1])
    for (k, p), a in zip(items, adj):
        out[k] = {"p": float(p), "p_adj": float(a), "significant": bool(a <= q)}
    return out


def mean_pvalue(x: pd.Series) -> float:
    """Two-sided p-value that the mean of `x` is zero, with a Newey-West (lag 5) standard error."""
    v = x.dropna().to_numpy()
    n = v.size
    if n < 60:
        return float("nan")
    e = v - v.mean()
    lrv = e @ e / n
    for lag in range(1, 6):
        w = 1 - lag / 6.0
        lrv += 2 * w * (e[lag:] @ e[:-lag]) / n
    se = np.sqrt(max(lrv, 1e-18) / n)
    return float(2 * (1 - stats.norm.cdf(abs(v.mean() / se))))

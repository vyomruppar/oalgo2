"""Runs every strategy through the backtester and assembles the research report stored for the dashboard."""
from __future__ import annotations

from typing import Any, Callable

import numpy as np
import pandas as pd

from ..research.factors import panel_factor_scores
from ..research.panel import PriceMatrices
from ..research.regime import regime_series
from ..universe.screener import ScreenConfig, eligibility_mask
from . import metrics as M
from .engine import CostModel, buy_and_hold, run_backtest, segment_bounds
from .strategies import STRATEGIES, build_targets, equal_weight_universe
from .validation import benjamini_hochberg, bootstrap_sharpe_ci, deflated_sharpe, mean_pvalue

DISCLOSURES = [
    "BACKTESTED, hypothetical results. Not observed or paper-traded performance.",
    "Survivorship bias: the free price source has no delisted companies, and the universe is today's most liquid listed stocks. Historical returns are overstated, most strongly for momentum-type strategies.",
    "Fundamentals are point-in-time by SEC filing date; prices are end-of-day; trades fill at the next session's open.",
    "Strategy parameters are fixed in advance, so train/validation/out-of-sample are sub-period stability checks, not a fitted-parameter test.",
    "Benchmarks: SPY and QQQ total return (ETF proxies for the S&P 500 and NASDAQ-100), and an equal-weight portfolio of the eligible universe.",
    "Validation status is judged against the equal-weight eligible universe, which shares the same survivorship bias, not against SPY.",
]


def _curve(s: pd.Series, max_points: int = 1500) -> list[list[Any]]:
    if len(s) > max_points:
        step = int(np.ceil(len(s) / max_points))
        s = pd.concat([s.iloc[::step], s.iloc[[-1]]])
        s = s[~s.index.duplicated()]
    return [[d.date().isoformat(), None if not np.isfinite(v) else round(float(v), 6)] for d, v in s.items()]


def run_all(pm: PriceMatrices, panel: pd.DataFrame, screen_cfg: ScreenConfig, benchmarks: dict[str, pd.Series],
            index_close: pd.Series, vix: pd.Series | None, rf_daily: pd.Series | None, top_n: int = 30,
            cost: CostModel | None = None, progress: Callable[[str, float], None] | None = None) -> dict[str, Any]:
    cost = cost or CostModel()
    elig = eligibility_mask(panel, screen_cfg)
    factors = panel_factor_scores(panel, elig)
    if factors.empty:
        raise ValueError("no eligible cross-sections for backtesting")
    # require a minimum breadth so that early, thin cross-sections do not dominate
    counts = factors.groupby(level="date").size()
    ok_dates = counts[counts >= max(40, 2 * top_n)].index
    factors = factors[factors.index.get_level_values("date").isin(ok_dates)]
    if factors.empty:
        raise ValueError("eligible universe too small for backtesting")
    reg = regime_series(index_close, vix)
    above = (reg["close"] > reg["sma_200"]).where(reg["sma_200"].notna())
    rf = rf_daily if rf_daily is not None else 0.0
    spy = buy_and_hold(benchmarks["SPY"]) if "SPY" in benchmarks else None
    results: dict[str, Any] = {}
    returns: dict[str, pd.Series] = {}
    all_targets = {"universe_ew": equal_weight_universe(factors)}
    all_targets.update({s.key: build_targets(s, panel, factors, top_n, above) for s in STRATEGIES})
    n = len(all_targets)
    for k, (key, tg) in enumerate(all_targets.items()):
        if progress:
            progress(f"backtest:{key}", k / n)
        res = run_backtest(pm, tg, cost)
        r = res.returns.dropna()
        returns[key] = r
        seg = {}
        for name, (a, b) in segment_bounds(r.index).items():
            rr = r.loc[a:b]
            seg[name] = M.summarize(rr, spy.reindex(rr.index) if spy is not None else None, rf)
        roll = (r.rolling(252).mean() / r.rolling(252).std() * np.sqrt(252)).dropna()
        by_regime = {}
        lab = reg["regime"].shift(1).reindex(r.index)
        for g in ("risk_on", "neutral", "risk_off"):
            rr = r[lab == g]
            if len(rr) > 20:
                by_regime[g] = {"days": int(len(rr)), "ann_return": float(rr.mean() * 252), "volatility": M.ann_vol(rr), "sharpe": M.sharpe(rr)}
        sens = {}
        if key != "universe_ew":
            for bps in (0, 10, 25, 50):
                rs = run_backtest(pm, tg, CostModel(0.0, float(bps))).returns.dropna()
                sens[str(bps)] = {"cagr": M.cagr(rs), "sharpe": M.sharpe(rs, rf.reindex(rs.index).fillna(0) if isinstance(rf, pd.Series) else rf)}
        vs_uni = None
        if key != "universe_ew":
            u = returns["universe_ew"].reindex(r.index)
            vs_uni = {"excess_cagr": M.cagr(r) - M.cagr(u.dropna()), **M.information_ratio(r, u), "segments": {}}
            for name, (a, b) in segment_bounds(r.index).items():
                vs_uni["segments"][name] = M.cagr(r.loc[a:b]) - M.cagr(u.loc[a:b].dropna())
        results[key] = {
            "vs_universe": vs_uni,
            "metrics": M.summarize(r, spy.reindex(r.index) if spy is not None else None, rf),
            "segments": seg, "trade_stats": M.trade_stats(res.trades), "turnover_annual": res.turnover_annual,
            "exposure_avg": res.exposure_avg, "holdings_avg": res.holdings_avg, "costs_total": res.costs_total,
            "equity": _curve((1 + r).cumprod()), "drawdown": _curve(M.drawdown_series(r)),
            "rolling_sharpe": _curve(roll), "by_regime": by_regime, "cost_sensitivity": sens,
            "current_holdings": [{"symbol": s, "weight": float(w)} for s, w in res.weights_last.head(60).items()],
            "bootstrap_sharpe": bootstrap_sharpe_ci(r, n_boot=400),
        }
    strat_keys = [s.key for s in STRATEGIES]
    sr_pp = [float(returns[k].mean() / returns[k].std(ddof=1)) for k in strat_keys if returns[k].std(ddof=1) > 0]
    pvals = {}
    for k in strat_keys:
        results[k]["deflated_sharpe"] = deflated_sharpe(returns[k], sr_pp)
        pvals[k] = mean_pvalue(returns[k] - returns["universe_ew"].reindex(returns[k].index))
    bh = benjamini_hochberg(pvals, q=0.10) if pvals else {}
    for k in strat_keys:
        results[k]["excess_vs_universe_test"] = bh.get(k)
        results[k]["validation_status"] = _status(results[k])
    bench_out = {}
    start = min(r.index[0] for r in returns.values())
    for name, s in benchmarks.items():
        b = buy_and_hold(s).loc[start:]
        bench_out[name] = {"metrics": M.summarize(b, None, rf), "equity": _curve((1 + b).cumprod()), "drawdown": _curve(M.drawdown_series(b))}
    corr = pd.DataFrame({k: returns[k] for k in strat_keys}).corr().round(3)
    meta = [{"key": s.key, "name": s.name, "family": s.family, "evidence": s.evidence, "hypothesis": s.hypothesis,
             "definition": s.definition, "benchmark": "SPY total return", "assumptions": f"top {top_n}, equal weight, monthly, {cost.commission_bps + cost.slippage_bps:.0f} bps one-way cost"}
            for s in STRATEGIES]
    meta.append({"key": "universe_ew", "name": "Equal-weight eligible universe", "family": "Benchmark", "evidence": "benchmark",
                 "hypothesis": "Reference: what holding every eligible stock would have returned.", "definition": "All eligible stocks, equal-weighted, monthly.",
                 "benchmark": "SPY total return", "assumptions": "same costs"})
    return {
        "label": "backtested", "generated_at": pd.Timestamp.now(tz="UTC").isoformat(), "disclosures": DISCLOSURES,
        "config": {"top_n": top_n, "rebalance": "monthly", "cost_bps_one_way": cost.commission_bps + cost.slippage_bps,
                   "universe_size_last": int(counts.iloc[-1]), "first_date": str(ok_dates[0].date()), "last_date": str(ok_dates[-1].date())},
        "strategies": meta, "results": results, "benchmarks": bench_out,
        "correlation": {"keys": strat_keys, "matrix": corr.values.tolist()},
        "universe_count": [[d.date().isoformat(), int(v)] for d, v in counts.items()],
    }


def _status(res: dict[str, Any]) -> dict[str, Any]:
    """Downgrade strategies that do not show incremental value after costs.

    The yardstick is the equal-weight ELIGIBLE UNIVERSE, not SPY: the universe is built from today's
    liquid survivors, so every strategy on it beats SPY for reasons unrelated to skill. Measuring
    against the same biased universe removes most of that selection effect."""
    vu = res.get("vs_universe") or {}
    reasons = []
    ex = vu.get("excess_cagr")
    if ex is not None and ex <= 0:
        reasons.append("no excess return over the equal-weight universe after costs in the full sample")
    oos = (vu.get("segments") or {}).get("out_of_sample")
    if oos is not None and oos <= 0:
        reasons.append("no excess return over the equal-weight universe in the out-of-sample segment")
    t = res.get("excess_vs_universe_test") or {}
    if not t.get("significant"):
        reasons.append("excess return is not statistically significant after multiple-testing correction (FDR 10%)")
    d = (res.get("deflated_sharpe") or {}).get("dsr")
    if d is not None and np.isfinite(d) and d < 0.95:
        reasons.append(f"Deflated Sharpe Ratio {d:.2f} is below 0.95")
    c50 = (res.get("cost_sensitivity") or {}).get("50", {}).get("cagr")
    status = "supported" if not reasons else ("mixed" if len(reasons) <= 2 and (ex or 0) > 0 else "not supported")
    return {"status": status, "reasons": reasons, "cagr_at_50bps": c50, "yardstick": "equal-weight eligible universe"}

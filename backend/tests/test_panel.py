"""Look-ahead and point-in-time tests on the research panel (shared by scoring, backtests and ML)."""
import numpy as np
import pandas as pd
import pytest

from app.research.factors import factor_scores, percentile, sector_zscore, winsorize, zscore
from app.research.panel import build_matrices, build_panel, forward_returns, future_split_factor, month_end_dates
from tests.conftest import make_prices, make_snapshots

SYMS = [f"S{i:02d}" for i in range(14)]


def make_world(n=700):
    prices = {s: make_prices(n, seed=i, drift=0.0002 * (i % 5), vol=0.01 + 0.002 * (i % 4)) for i, s in enumerate(SYMS)}
    cal = prices[SYMS[0]].index
    filed = pd.date_range(cal[0] - pd.Timedelta(days=30), cal[-1], freq="91D")
    snaps = {s: make_snapshots(filed + pd.Timedelta(days=i), seed=i, scale=1e9 * (1 + i)) for i, s in enumerate(SYMS)}
    sectors = {s: ["Technology", "Financials", "Energy"][i % 3] for i, s in enumerate(SYMS)}
    return prices, snaps, sectors, cal


def test_panel_has_no_lookahead():
    prices, snaps, sectors, cal = make_world()
    dates = month_end_dates(cal)
    full = build_panel(build_matrices(prices, cal), snaps, dates, sectors)
    cut = dates[len(dates) // 2]
    prices_cut = {s: df.loc[:cut] for s, df in prices.items()}
    snaps_cut = {s: df[df.index <= cut] for s, df in snaps.items()}
    part = build_panel(build_matrices(prices_cut, cal[cal <= cut]), snaps_cut, dates[dates <= cut], sectors)
    num = [c for c in part.columns if pd.api.types.is_numeric_dtype(part[c])]
    a, b = full.loc[part.index, num].astype(float), part[num].astype(float)
    pd.testing.assert_frame_equal(a, b, check_exact=False, rtol=1e-9, check_dtype=False)


def test_fundamentals_enter_strictly_after_filing():
    prices, snaps, sectors, cal = make_world()
    d = cal[400]
    snaps["S00"] = snaps["S00"].copy()
    snaps["S00"].loc[d, :] = snaps["S00"].iloc[-1]
    snaps["S00"] = snaps["S00"].sort_index()
    snaps["S00"].loc[d, "revenue_ttm"] = 7.77e12
    pm = build_matrices(prices, cal)
    p = build_panel(pm, snaps, pd.DatetimeIndex([d, cal[401]]), sectors)
    assert p.loc[(d, "S00"), "revenue_ttm"] != 7.77e12            # filed on d: not usable at the close of d
    assert p.loc[(cal[401], "S00"), "revenue_ttm"] == 7.77e12     # usable from the next session


def test_stale_fundamentals_become_missing():
    prices, snaps, sectors, cal = make_world()
    snaps["S01"] = snaps["S01"][snaps["S01"].index < cal[100]]
    p = build_panel(build_matrices(prices, cal), snaps, pd.DatetimeIndex([cal[-1]]), sectors)
    assert np.isnan(p.loc[(cal[-1], "S01"), "revenue_ttm"])
    assert np.isnan(p.loc[(cal[-1], "S01"), "market_cap"])


def test_market_cap_is_continuous_across_a_split():
    prices, snaps, sectors, cal = make_world()
    split_day = cal[500]
    df = prices["S02"].copy()
    df.loc[split_day, "split"] = 4.0            # prices are already split-adjusted by the provider
    prices["S02"] = df
    snap = snaps["S02"].copy()
    post = snap["shares_cover_date"] > split_day
    snap.loc[post, ["shares_cover", "shares_diluted", "shares_bs"]] *= 4.0     # filings after the split report 4x shares
    snaps["S02"] = snap
    pm = build_matrices(prices, cal)
    p = build_panel(pm, snaps, pd.DatetimeIndex([cal[490], cal[640]]), sectors)
    before, after = p.loc[(cal[490], "S02")], p.loc[(cal[640], "S02")]
    assert before["shares"] == pytest.approx(4e8) and after["shares"] == pytest.approx(4e8)
    assert before["market_cap"] == pytest.approx(4e8 * before["price"])
    f = future_split_factor(pm.split["S02"])
    assert f.loc[cal[499]] == 4.0 and f.loc[split_day] == 1.0


def test_implausible_share_count_is_flagged_not_ranked():
    prices, snaps, sectors, cal = make_world()
    snaps["S03"] = snaps["S03"].assign(shares_cover=1e3, shares_diluted=1e3)
    p = build_panel(build_matrices(prices, cal), snaps, pd.DatetimeIndex([cal[-1]]), sectors)
    row = p.loc[(cal[-1], "S03")]
    assert bool(row["share_count_unreliable"]) and np.isnan(row["market_cap"])


def test_forward_returns_start_at_next_open():
    prices, snaps, sectors, cal = make_world(120)
    pm = build_matrices(prices, cal)
    t = cal[50]
    fwd = forward_returns(pm, pd.DatetimeIndex([t]), 21)
    o = prices["S00"]["open"]
    assert fwd.loc[(t, "S00")] == pytest.approx(o.iloc[72] / o.iloc[51] - 1)
    assert forward_returns(pm, pd.DatetimeIndex([cal[-1]]), 21).isna().all()   # unknown future -> NaN, never filled


def test_zscore_winsorize_percentile():
    s = pd.Series([1.0, 2, 3, 4, 100])
    assert winsorize(s, 0.0, 0.75).max() == 4.0
    z = zscore(pd.Series([1.0, 2.0, 3.0]))
    assert z.mean() == pytest.approx(0) and z.std(ddof=0) == pytest.approx(1)
    assert zscore(pd.Series([5.0, 5.0, 5.0])).tolist() == [0, 0, 0]
    assert percentile(pd.Series([10.0, 20.0, np.nan, 30.0])).tolist()[:2] == pytest.approx([100 / 3, 200 / 3])


def test_sector_neutral_zscore_removes_sector_level():
    vals = pd.Series(np.r_[np.arange(10.0), 100 + np.arange(10.0)])
    sec = pd.Series(["a"] * 10 + ["b"] * 10)
    z = sector_zscore(vals, sec)
    assert z[:10].mean() == pytest.approx(0, abs=1e-9) and z[10:].mean() == pytest.approx(0, abs=1e-9)


def test_factor_composites_handle_missing_inputs():
    prices, snaps, sectors, cal = make_world()
    p = build_panel(build_matrices(prices, cal), snaps, pd.DatetimeIndex([cal[-1]]), sectors).droplevel("date")
    p.loc["S05", ["earnings_yield", "ebit_ev", "book_to_market"]] = np.nan
    fs = factor_scores(p)
    assert fs.loc["S05", "value_n"] == 1 and np.isfinite(fs.loc["S05", "value"])
    p.loc["S06", ["earnings_yield", "ebit_ev", "book_to_market", "fcf_yield"]] = np.nan
    assert np.isnan(factor_scores(p).loc["S06", "value"])           # no inputs -> missing, never zero-filled

import numpy as np
import pandas as pd
import pytest

from app.backtest.engine import CostModel, buy_and_hold, run_backtest, segment_bounds
from app.backtest.strategies import STRATEGIES, build_targets, equal_weight_universe
from app.research.panel import build_matrices
from tests.conftest import make_prices


def flat(n, price=100.0, start="2024-01-01"):
    idx = pd.bdate_range(start, periods=n)
    return pd.DataFrame({"open": price, "high": price, "low": price, "close": price, "adj_close": price, "volume": 1e6,
                         "dividend": 0.0, "split": 1.0}, index=idx)


def test_trades_at_next_open_not_at_signal_close():
    a = flat(10)
    a.loc[a.index[3]:, ["open", "high", "low", "close", "adj_close"]] = 110.0   # jump before the open of day 3
    a.loc[a.index[3], "open"] = 110.0
    pm = build_matrices({"A": a})
    res = run_backtest(pm, {a.index[2]: pd.Series({"A": 1.0})}, CostModel(0, 0), initial=1000.0)
    # the signal is formed at the close of day 2 (price 100) but the fill is at the open of day 3 (110): no gain is captured
    assert res.equity.iloc[0] == pytest.approx(1000.0)
    assert res.equity.iloc[-1] == pytest.approx(1000.0)
    assert res.equity.index[0] == a.index[3]


def test_costs_are_charged_on_traded_notional():
    a = flat(10)
    pm = build_matrices({"A": a})
    res = run_backtest(pm, {a.index[0]: pd.Series({"A": 1.0})}, CostModel(5, 5), initial=1000.0)
    # invest x with x*(1+0.001) = 1000 -> x = 999.001, cost = 0.999
    assert res.costs_total == pytest.approx(1000 - 1000 / 1.001, rel=1e-6)
    assert res.equity.iloc[-1] == pytest.approx(1000 / 1.001, rel=1e-6)
    assert res.equity.iloc[-1] < 1000.0


def test_buy_and_hold_matches_asset_return_and_never_levers():
    a = make_prices(300, seed=1)
    pm = build_matrices({"A": a})
    res = run_backtest(pm, {a.index[0]: pd.Series({"A": 1.0})}, CostModel(0, 0), initial=1e6)
    expected = a["adj_close"].iloc[-1] / a["open"].iloc[1] - 1
    assert res.equity.iloc[-1] / 1e6 - 1 == pytest.approx(expected, rel=1e-9)
    assert res.exposure_avg <= 1.0 + 1e-9


def test_rebalance_round_trip_statistics_and_turnover():
    a, b = flat(30), flat(30)
    b.loc[b.index[11]:, ["open", "high", "low", "close", "adj_close"]] = 120.0
    pm = build_matrices({"A": a, "B": b})
    targets = {a.index[0]: pd.Series({"B": 1.0}), a.index[19]: pd.Series({"A": 1.0})}
    res = run_backtest(pm, targets, CostModel(0, 0), initial=1000.0)
    assert res.equity.iloc[-1] == pytest.approx(1200.0)
    assert len(res.trades) == 1
    t = res.trades.iloc[0]
    assert t["symbol"] == "B" and t["pnl"] == pytest.approx(200.0) and t["pnl_pct"] == pytest.approx(0.2) and t["hold_days"] == 19
    assert res.turnover_annual > 0 and len(res.rebalance_log) == 2


def test_empty_target_moves_to_cash():
    a = make_prices(60, seed=2)
    pm = build_matrices({"A": a})
    res = run_backtest(pm, {a.index[0]: pd.Series({"A": 1.0}), a.index[20]: pd.Series(dtype=float)}, CostModel(0, 0))
    after = res.equity.loc[a.index[22]:]
    assert after.nunique() == 1                       # flat in cash after the exit


def test_untradable_stock_is_not_traded_but_stays_valued():
    a, b = flat(20), flat(20)
    b.loc[b.index[5], ["open", "high", "low", "close", "adj_close"]] = np.nan   # halt on the rebalance fill day
    pm = build_matrices({"A": a, "B": b})
    res = run_backtest(pm, {a.index[0]: pd.Series({"A": 0.5, "B": 0.5}), a.index[4]: pd.Series({"A": 1.0})}, CostModel(0, 0), initial=1000.0)
    assert res.equity.iloc[-1] == pytest.approx(1000.0)
    assert res.weights_last["B"] == pytest.approx(0.5)   # could not be sold during the halt


def test_segments_are_chronological_and_disjoint():
    idx = pd.bdate_range("2020-01-01", periods=1000)
    s = segment_bounds(idx)
    assert s["train"][0] == idx[0] and s["out_of_sample"][1] == idx[-1]
    assert s["train"][1] < s["validation"][0] <= s["validation"][1] < s["out_of_sample"][0]


def test_build_targets_top_n_and_cash_remainder():
    dates = pd.DatetimeIndex(["2024-01-31", "2024-02-29"])
    idx = pd.MultiIndex.from_product([dates, [f"S{i}" for i in range(10)]], names=["date", "symbol"])
    factors = pd.DataFrame({"value": np.tile(np.arange(10.0), 2)}, index=idx)
    for c in ["quality", "momentum", "earnings", "low_vol", "investment", "financial_strength", "size", "reversal"]:
        factors[c] = 0.0
    panel = pd.DataFrame({"price": 10.0, "sma_50": 9.0, "sma_200": 8.0, "mom_12_1": 0.1, "adv_dollar_63": 1e7, "dist_52w_high": -0.5}, index=idx)
    value = next(s for s in STRATEGIES if s.key == "value")
    tg = build_targets(value, panel, factors, top_n=3, max_weight=1.0)
    assert list(tg[dates[0]].index) == ["S9", "S8", "S7"] and tg[dates[0]].sum() == pytest.approx(1.0)
    capped = build_targets(value, panel, factors, top_n=3, max_weight=0.10)
    assert capped[dates[0]].max() == pytest.approx(0.10) and capped[dates[0]].sum() == pytest.approx(0.30)   # rest stays in cash
    breakout = next(s for s in STRATEGIES if s.key == "breakout")
    assert build_targets(breakout, panel, factors, top_n=3)[dates[0]].empty       # nothing near its high -> cash
    trend = next(s for s in STRATEGIES if s.key == "trend")
    off = pd.Series([False, True], index=dates)
    tt = build_targets(trend, panel, factors, top_n=3, index_above_200=off)
    assert tt[dates[0]].empty and len(tt[dates[1]]) == 3                            # market filter -> cash
    ew = equal_weight_universe(factors)
    assert ew[dates[0]].sum() == pytest.approx(1.0) and len(ew[dates[0]]) == 10


def test_buy_and_hold_benchmark():
    s = pd.Series([100.0, 110.0, 99.0], index=pd.bdate_range("2024-01-01", periods=3))
    assert buy_and_hold(s).tolist() == pytest.approx([0.10, -0.10])


def test_every_strategy_documents_hypothesis_and_evidence():
    for s in STRATEGIES:
        assert s.hypothesis and s.definition and s.evidence in ("evidence-backed", "needs validation")

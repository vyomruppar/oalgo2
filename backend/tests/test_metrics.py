import numpy as np
import pandas as pd
import pytest

from app.backtest import metrics as M


def series(vals):
    return pd.Series(vals, index=pd.bdate_range("2024-01-01", periods=len(vals)), dtype=float)


def test_total_return_and_cagr():
    r = series([0.10, -0.05, 0.02])
    assert M.total_return(r) == pytest.approx(1.10 * 0.95 * 1.02 - 1)
    one_year = series([0.0] * 251 + [0.21])
    assert M.cagr(one_year) == pytest.approx(0.21)


def test_sharpe_and_sortino():
    r = series([0.01, -0.01, 0.02, 0.00, 0.01])
    assert M.sharpe(r) == pytest.approx(r.mean() / r.std(ddof=1) * np.sqrt(252))
    assert M.sharpe(r, rf=0.001) == pytest.approx((r.mean() - 0.001) / r.std(ddof=1) * np.sqrt(252))
    dd = np.sqrt((np.minimum(r, 0) ** 2).mean()) * np.sqrt(252)
    assert M.sortino(r) == pytest.approx(r.mean() * 252 / dd)
    assert np.isnan(M.sharpe(series([0.01] * 5)))  # zero variance -> undefined, not infinite


def test_max_drawdown_and_calmar():
    r = series([0.10, -0.20, -0.10, 0.50])
    # equity 1.1 -> 0.88 -> 0.792 -> 1.188; trough vs peak 1.1 = -28%
    assert M.max_drawdown(r) == pytest.approx(0.792 / 1.1 - 1)
    assert M.drawdown_series(r).iloc[-1] == pytest.approx(0.0)
    assert M.max_drawdown(series([-0.10])) == pytest.approx(-0.10)  # loss from the starting capital counts


def test_var_cvar_historical():
    r = series(list(np.linspace(-0.10, 0.098, 100)))
    v = M.var_cvar(r, 0.95)
    q = np.quantile(r, 0.05)
    assert v["hist_var"] == pytest.approx(-q)
    assert v["hist_cvar"] == pytest.approx(-r[r <= q].mean())
    assert v["hist_cvar"] >= v["hist_var"] > 0
    assert v["param_cvar"] > v["param_var"]


def test_alpha_beta_recovers_known_values():
    rng = np.random.default_rng(1)
    b = series(rng.normal(0.0005, 0.01, 2000))
    r = 0.0002 + 1.3 * b + series(rng.normal(0, 0.001, 2000))
    ab = M.alpha_beta(r, b)
    assert ab["beta"] == pytest.approx(1.3, abs=0.01)
    assert ab["alpha"] == pytest.approx(0.0002 * 252, abs=0.01)
    ir = M.information_ratio(r, b)
    assert ir["tracking_error"] == pytest.approx((r - b).std(ddof=1) * np.sqrt(252))


def test_trade_stats():
    t = pd.DataFrame({"pnl": [100.0, -50.0, 30.0, -20.0], "pnl_pct": [0.10, -0.05, 0.03, -0.02], "hold_days": [10, 20, 30, 40]})
    s = M.trade_stats(t)
    assert s["n_trades"] == 4 and s["win_rate"] == 0.5
    assert s["avg_win"] == pytest.approx(0.065) and s["avg_loss"] == pytest.approx(-0.035)
    assert s["profit_factor"] == pytest.approx(130 / 70)
    assert M.trade_stats(pd.DataFrame())["n_trades"] == 0


def test_summarize_has_no_nan():
    rng = np.random.default_rng(2)
    r = series(rng.normal(0.0005, 0.01, 300))
    out = M.summarize(r, series(rng.normal(0.0003, 0.01, 300)))
    assert all(v is None or not (isinstance(v, float) and np.isnan(v)) for v in out.values())
    assert out["excess_cagr"] == pytest.approx(out["cagr"] - out["benchmark_cagr"])

import numpy as np
import pandas as pd
import pytest

from app.research import indicators as ind
from tests.conftest import make_prices

CLOSES = [44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84, 46.08, 45.89, 46.03, 45.61, 46.28, 46.28, 46.00,
          46.03, 46.41, 46.22, 45.64]


def test_sma_and_ema_hand_values():
    s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    assert ind.sma(s, 3).tolist()[2:] == [2.0, 3.0, 4.0]
    assert np.isnan(ind.sma(s, 3).iloc[1])
    # EMA alpha = 2/(3+1) = 0.5, seeded with first value: 1, 1.5, 2.25, 3.125, 4.0625
    assert ind.ema(s, 3).iloc[-1] == pytest.approx(4.0625)


def test_rsi_matches_wilder_hand_calculation():
    s = pd.Series(CLOSES)
    d = np.diff(CLOSES)
    gains, losses = np.clip(d, 0, None), np.clip(-d, 0, None)
    ag, al = gains[:14].mean(), losses[:14].mean()
    expected = [100 - 100 / (1 + ag / al)]
    for i in range(14, len(d)):
        ag, al = (ag * 13 + gains[i]) / 14, (al * 13 + losses[i]) / 14
        expected.append(100 - 100 / (1 + ag / al))
    got = ind.rsi(s, 14).dropna().tolist()
    assert got == pytest.approx(expected)
    assert got[0] == pytest.approx(70.46, abs=0.01)   # textbook value for this series


def test_rsi_all_gains_is_100():
    assert ind.rsi(pd.Series(np.arange(1.0, 40.0)), 14).iloc[-1] == 100.0


def test_macd_is_fast_minus_slow_ema():
    s = pd.Series(np.linspace(10, 30, 80))
    m = ind.macd(s)
    assert m["macd"].iloc[-1] == pytest.approx(ind.ema(s, 12).iloc[-1] - ind.ema(s, 26).iloc[-1])
    assert m["hist"].iloc[-1] == pytest.approx(m["macd"].iloc[-1] - m["signal"].iloc[-1])


def test_bollinger_uses_population_std():
    s = pd.Series([2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0])  # mean 5, population sd 2
    b = ind.bollinger(s, 8, 2.0).iloc[-1]
    assert b["mid"] == pytest.approx(5.0)
    assert b["upper"] == pytest.approx(9.0) and b["lower"] == pytest.approx(1.0)
    assert b["zscore"] == pytest.approx(2.0) and b["pct_b"] == pytest.approx(1.0)


def test_true_range_and_atr():
    h = pd.Series([10.0, 11.0, 12.0, 11.5])
    l = pd.Series([9.0, 9.5, 11.0, 10.0])
    c = pd.Series([9.5, 10.5, 11.5, 10.2])
    tr = ind.true_range(h, l, c)
    assert tr.tolist() == pytest.approx([1.0, 1.5, 1.5, 1.5])      # max(h-l, |h-pc|, |l-pc|)
    a = ind.atr(h, l, c, 3)
    assert a.iloc[2] == pytest.approx((1.0 + 1.5 + 1.5) / 3)
    assert a.iloc[3] == pytest.approx((a.iloc[2] * 2 + 1.5) / 3)


def test_obv():
    c = pd.Series([10.0, 11.0, 10.5, 10.5, 12.0])
    v = pd.Series([100.0, 200.0, 300.0, 400.0, 500.0])
    assert ind.obv(c, v).tolist() == [0.0, 200.0, -100.0, -100.0, 400.0]


def test_mfi_hand_value():
    h = pd.Series([10.0, 11, 12, 11, 13]); l = pd.Series([8.0, 9, 10, 9, 11]); c = pd.Series([9.0, 10, 11, 10, 12])
    v = pd.Series([100.0, 100, 100, 100, 100])
    # typical prices 9,10,11,10,12 -> flows up: 1000+1100+1200 = 3300, down: 1000 over the last 4 changes
    assert ind.mfi(h, l, c, v, 4).iloc[-1] == pytest.approx(100 - 100 / (1 + 3300 / 1000))


def test_rolling_vwap():
    h = pd.Series([10.0, 20.0]); l = pd.Series([10.0, 20.0]); c = pd.Series([10.0, 20.0]); v = pd.Series([1.0, 3.0])
    assert ind.rolling_vwap(h, l, c, v, 2).iloc[-1] == pytest.approx((10 * 1 + 20 * 3) / 4)


def test_ichimoku_cloud_is_shifted_forward():
    df = make_prices(200, seed=3)
    ich = ind.ichimoku(df["high"], df["low"], df["close"])
    tenkan = (df["high"].rolling(9).max() + df["low"].rolling(9).min()) / 2
    kijun = (df["high"].rolling(26).max() + df["low"].rolling(26).min()) / 2
    assert ich["span_a"].iloc[-1] == pytest.approx(((tenkan + kijun) / 2).iloc[-27])


def test_indicators_are_causal():
    """Appending future bars must not change any past indicator value (no look-ahead)."""
    df = make_prices(400, seed=5)
    bench = make_prices(400, seed=6)["adj_close"]
    full = ind.compute_all(df, bench)
    part = ind.compute_all(df.iloc[:300], bench.iloc[:300])
    pd.testing.assert_frame_equal(full.iloc[:300], part, check_exact=False, rtol=1e-10)

import numpy as np
import pandas as pd
import pytest
from scipy import stats

from app.backtest import validation as V


def test_benjamini_hochberg_textbook_example():
    p = {"a": 0.001, "b": 0.008, "c": 0.039, "d": 0.041, "e": 0.042, "f": 0.06, "g": 0.074, "h": 0.205}
    out = V.benjamini_hochberg(p, q=0.05)
    # step-up: largest k with p_(k) <= k/m*q -> k=2 (0.008 <= 0.0125), so only a and b are discoveries
    assert [k for k, v in out.items() if v["significant"]] == ["a", "b"]
    assert out["a"]["p_adj"] == pytest.approx(0.008)
    assert out["h"]["p_adj"] == pytest.approx(0.205)
    assert all(out[x]["p_adj"] <= out[y]["p_adj"] for x, y in zip("abcdefg", "bcdefgh"))


def test_bh_handles_missing():
    out = V.benjamini_hochberg({"a": 0.01, "b": float("nan")})
    assert out["a"]["significant"] and not out["b"]["significant"]


def test_probabilistic_sharpe_normal_case():
    assert V.probabilistic_sharpe(0.1, 253, 0.0, 3.0, 0.0) == pytest.approx(stats.norm.cdf(0.1 * np.sqrt(252) / np.sqrt(1 + 0.5 * 0.01)))
    assert V.probabilistic_sharpe(0.0, 500, 0.0, 3.0, 0.0) == pytest.approx(0.5)


def test_expected_max_sharpe_grows_with_trials():
    a, b = V.expected_max_sharpe(0.01, 5), V.expected_max_sharpe(0.01, 50)
    assert 0 < a < b
    assert V.expected_max_sharpe(0.01, 1) == 0.0


def test_deflated_sharpe_penalises_many_trials():
    rng = np.random.default_rng(3)
    r = pd.Series(rng.normal(0.0006, 0.01, 1500))
    few = V.deflated_sharpe(r, [0.02, 0.06])
    many = V.deflated_sharpe(r, list(rng.normal(0.03, 0.03, 100)))
    assert many["dsr"] < few["dsr"]
    assert many["sr0_annual"] > few["sr0_annual"]


def test_bootstrap_ci_brackets_point_estimate_and_noise_includes_zero():
    rng = np.random.default_rng(4)
    r = pd.Series(rng.normal(0.001, 0.01, 1000))
    ci = V.bootstrap_sharpe_ci(r, n_boot=300)
    sr = r.mean() / r.std(ddof=1) * np.sqrt(252)
    assert ci["lo"] < sr < ci["hi"]
    noise = V.bootstrap_sharpe_ci(pd.Series(rng.normal(0.0, 0.01, 1000)), n_boot=300)
    assert noise["lo"] < 0 < noise["hi"]


def test_stationary_bootstrap_indices_are_valid():
    idx = V.stationary_bootstrap_indices(500, 20, np.random.default_rng(0))
    assert idx.min() >= 0 and idx.max() < 500 and len(idx) == 500
    assert (np.diff(idx) == 1).mean() > 0.8   # mostly contiguous blocks


def test_mean_pvalue():
    rng = np.random.default_rng(5)
    assert V.mean_pvalue(pd.Series(rng.normal(0.002, 0.01, 2000))) < 0.01
    assert V.mean_pvalue(pd.Series(rng.normal(0.0, 0.01, 2000))) > 0.05

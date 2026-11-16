import numpy as np
import pandas as pd
import pytest

from app.research import ml


def dataset(signal: float, n_dates=70, n_syms=60, seed=0):
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2018-01-31", periods=n_dates, freq="ME")
    idx = pd.MultiIndex.from_product([dates, [f"S{i}" for i in range(n_syms)]], names=["date", "symbol"])
    X = pd.DataFrame(rng.normal(size=(len(idx), len(ml.FEATURES))), index=idx, columns=ml.FEATURES)
    fwd = pd.Series(signal * X["momentum"].to_numpy() + rng.normal(0, 0.05, len(idx)), index=idx)
    return X, fwd


def test_planted_signal_is_found_and_validated():
    X, fwd = dataset(0.03)
    rep, rank = ml.train_and_report(X, fwd)
    assert rep["status"] == "ok"
    assert rep["models"]["logistic"]["validated"] is True
    assert rep["models"]["logistic"]["out_of_sample"]["rank_ic_mean"] > 0.1
    assert rep["active_model"] in ("logistic", "gradient_boosting") and rank is not None
    top = rep["models"]["logistic"]["feature_importance"][0]
    assert top["feature"] == "momentum" and top["direction"] > 0


def test_pure_noise_is_not_validated_and_not_used():
    X, fwd = dataset(0.0, seed=1)
    rep, rank = ml.train_and_report(X, fwd)
    assert rep["status"] == "ok"
    assert rep["models"]["logistic"]["validated"] is False and rep["models"]["gradient_boosting"]["validated"] is False
    assert rep["active_model"] is None and rank is None       # an unvalidated model never reaches the score


def test_walk_forward_is_chronological_with_purge():
    X, fwd = dataset(0.02)
    rep = ml.walk_forward(ml.make_dataset(X, fwd))
    assert len(rep["folds"]) >= 2
    for f in rep["folds"]:
        tr0, tr1 = map(pd.Timestamp, f["train"]); v0, v1 = map(pd.Timestamp, f["validation"]); t0, t1 = map(pd.Timestamp, f["test"])
        assert tr0 <= tr1 < v0 <= v1 < t0 <= t1
        assert (t0.to_period("M") - v1.to_period("M")).n >= 2      # one full month purged between validation and test
    tests = [tuple(f["test"]) for f in rep["folds"]]
    assert len(set(tests)) == len(tests)                             # out-of-sample windows do not overlap


def test_label_is_cross_sectional_median_split():
    X, fwd = dataset(0.02, n_dates=5)
    d = ml.make_dataset(X, fwd)
    assert d.groupby(level="date")["y"].mean().between(0.45, 0.55).all()


def test_insufficient_history_is_reported_not_faked():
    X, fwd = dataset(0.02, n_dates=20)
    rep, rank = ml.train_and_report(X, fwd)
    assert rep["status"] == "insufficient_history" and rep["active_model"] is None and rank is None


def test_psi():
    rng = np.random.default_rng(0)
    a = rng.normal(size=5000)
    assert ml.psi(a, rng.normal(size=2000)) < 0.1
    assert ml.psi(a, rng.normal(2.0, 1.0, size=2000)) > 0.25
    assert np.isnan(ml.psi(a[:10], a))

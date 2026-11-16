"""Machine-learning baselines with walk-forward validation.

Task: classify whether a stock's forward 21-day return (open t+1 -> open t+22) beats the
cross-sectional median of the eligible universe on that date.
Models: L2 logistic regression (interpretable baseline) and histogram gradient boosting.
Validation: expanding window, retrained every 12 months, a one-month purge between the last training
label and the first test date so that overlapping label windows cannot leak.

A model's output only enters the research score if it is VALIDATED: out-of-sample rank IC is positive
with t-stat > 2 and (for gradient boosting) exceeds the logistic baseline. `probability` here is a
model score for ranking; it is not a calibrated probability of making money.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

FEATURES = ["value", "quality", "momentum", "earnings", "low_vol", "investment", "financial_strength", "size", "reversal"]
MODEL_VERSION = "2026.11-stage1"


def make_models() -> dict[str, Any]:
    return {
        "logistic": make_pipeline(StandardScaler(), LogisticRegression(C=0.5, max_iter=500)),
        "gradient_boosting": HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=150,
                                                            min_samples_leaf=40, l2_regularization=1.0, random_state=7),
    }


def make_dataset(factors: pd.DataFrame, fwd: pd.Series) -> pd.DataFrame:
    df = factors[FEATURES].join(fwd.rename("fwd"), how="inner").dropna(subset=["fwd"])
    med = df.groupby(level="date")["fwd"].transform("median")
    df["y"] = (df["fwd"] > med).astype(int)
    return df


def _rank_ic(df: pd.DataFrame, score: np.ndarray) -> pd.Series:
    tmp = pd.DataFrame({"s": score, "fwd": df["fwd"].to_numpy()}, index=df.index)
    return tmp.groupby(level="date").apply(lambda g: g["s"].corr(g["fwd"], method="spearman") if len(g) >= 10 else np.nan).dropna()


def _eval(df: pd.DataFrame, p: np.ndarray) -> dict[str, Any]:
    if len(df) == 0:
        return {}
    ic = _rank_ic(df, p)
    y = df["y"].to_numpy()
    tmp = pd.DataFrame({"p": p, "fwd": df["fwd"].to_numpy()}, index=df.index)
    dec = tmp.groupby(level="date").apply(
        lambda g: g.loc[g["p"] >= g["p"].quantile(0.9), "fwd"].mean() - g.loc[g["p"] <= g["p"].quantile(0.1), "fwd"].mean()).dropna()
    return {"n": int(len(df)), "n_dates": int(df.index.get_level_values("date").nunique()),
            "auc": float(roc_auc_score(y, p)) if len(np.unique(y)) > 1 else None,
            "accuracy": float(((p > 0.5).astype(int) == y).mean()), "brier": float(brier_score_loss(y, p)),
            "rank_ic_mean": float(ic.mean()) if len(ic) else None,
            "rank_ic_t": float(ic.mean() / ic.std(ddof=1) * np.sqrt(len(ic))) if len(ic) > 2 and ic.std(ddof=1) > 0 else None,
            "top_minus_bottom_decile_21d": float(dec.mean()) if len(dec) else None}


def _fillna_fit(X: pd.DataFrame) -> pd.DataFrame:
    return X.fillna(0.0)  # features are z-scores: 0 = cross-sectional average


def walk_forward(data: pd.DataFrame, min_train_months: int = 36, test_months: int = 12, purge_months: int = 1) -> dict[str, Any]:
    dates = data.index.get_level_values("date").unique().sort_values()
    if len(dates) < min_train_months + purge_months + 6:
        return {"status": "insufficient_history", "detail": f"{len(dates)} monthly cross-sections; need at least {min_train_months + purge_months + 6}"}
    dlev = data.index.get_level_values("date")
    folds, oos_pred = [], {k: [] for k in make_models()}
    start = min_train_months
    while start + purge_months < len(dates):
        train_d = dates[:start]
        val_d = train_d[-12:]
        fit_d = train_d[:-12]
        test_d = dates[start + purge_months: start + purge_months + test_months]
        if len(test_d) == 0:
            break
        fit, val, test = data[dlev.isin(fit_d)], data[dlev.isin(val_d)], data[dlev.isin(test_d)]
        fold = {"train": [str(fit_d[0].date()), str(fit_d[-1].date())], "validation": [str(val_d[0].date()), str(val_d[-1].date())],
                "test": [str(test_d[0].date()), str(test_d[-1].date())], "models": {}}
        for name, model in make_models().items():
            model.fit(_fillna_fit(fit[FEATURES]), fit["y"])
            res = {}
            for seg_name, seg in (("train", fit), ("validation", val), ("out_of_sample", test)):
                res[seg_name] = _eval(seg, model.predict_proba(_fillna_fit(seg[FEATURES]))[:, 1])
            fold["models"][name] = res
            oos_pred[name].append(pd.Series(model.predict_proba(_fillna_fit(test[FEATURES]))[:, 1], index=test.index))
        folds.append(fold)
        start += test_months
    report: dict[str, Any] = {"status": "ok", "folds": folds, "models": {}}
    for name in oos_pred:
        p = pd.concat(oos_pred[name])
        df = data.loc[p.index]
        agg = _eval(df, p.to_numpy())
        ic = _rank_ic(df, p.to_numpy())
        bins = pd.cut(p, np.linspace(0, 1, 11), include_lowest=True)
        cal = pd.DataFrame({"p": p, "y": df["y"]}).groupby(bins, observed=True).agg(pred=("p", "mean"), actual=("y", "mean"), n=("y", "size"))
        report["models"][name] = {
            "out_of_sample": agg,
            "train_mean": _mean_seg(folds, name, "train"), "validation_mean": _mean_seg(folds, name, "validation"),
            "ic_by_date": [[d.date().isoformat(), round(float(v), 4)] for d, v in ic.items()],
            "calibration": [{"predicted": float(r.pred), "actual": float(r.actual), "n": int(r.n)} for r in cal.itertuples() if r.n >= 20],
            "error_by_year": [{"year": int(y), "accuracy": float(((g["p"] > 0.5).astype(int) == g["y"]).mean()), "n": int(len(g))}
                              for y, g in pd.DataFrame({"p": p, "y": df["y"]}).groupby(p.index.get_level_values("date").year)],
        }
    lg, gb = report["models"]["logistic"]["out_of_sample"], report["models"]["gradient_boosting"]["out_of_sample"]

    def ok(m: dict[str, Any]) -> bool:
        return (m.get("rank_ic_mean") or 0) > 0 and (m.get("rank_ic_t") or 0) > 2.0

    report["models"]["logistic"]["validated"] = ok(lg)
    report["models"]["gradient_boosting"]["validated"] = ok(gb) and (gb.get("rank_ic_mean") or 0) > (lg.get("rank_ic_mean") or 0)
    report["models"]["gradient_boosting"]["validation_note"] = "must beat the logistic baseline out-of-sample to be used"
    return report


def _mean_seg(folds: list[dict[str, Any]], model: str, seg: str) -> dict[str, Any]:
    keys = ["auc", "accuracy", "brier", "rank_ic_mean"]
    out = {}
    for k in keys:
        vals = [f["models"][model][seg].get(k) for f in folds if f["models"][model].get(seg)]
        vals = [v for v in vals if v is not None]
        out[k] = float(np.mean(vals)) if vals else None
    return out


def psi(expected: np.ndarray, actual: np.ndarray, bins: int = 10) -> float:
    """Population Stability Index between a training feature distribution and the current one."""
    e, a = expected[np.isfinite(expected)], actual[np.isfinite(actual)]
    if e.size < 50 or a.size < 20:
        return float("nan")
    edges = np.unique(np.quantile(e, np.linspace(0, 1, bins + 1)))
    if edges.size < 3:
        return float("nan")
    edges[0], edges[-1] = -np.inf, np.inf
    pe = np.clip(np.histogram(e, edges)[0] / e.size, 1e-4, None)
    pa = np.clip(np.histogram(a, edges)[0] / a.size, 1e-4, None)
    return float(((pa - pe) * np.log(pa / pe)).sum())


def train_and_report(factors: pd.DataFrame, fwd: pd.Series) -> tuple[dict[str, Any], pd.Series | None]:
    """Returns (report, current ranking scores from the best VALIDATED model or None)."""
    data = make_dataset(factors, fwd)
    report = walk_forward(data)
    report.update({"version": MODEL_VERSION, "trained_at": pd.Timestamp.now(tz="UTC").isoformat(), "features": FEATURES,
                   "target": "forward 21-trading-day return above the universe median (open-to-open, entered at next open)",
                   "note": "Model scores rank stocks. They are not probabilities of making money."})
    if report.get("status") != "ok":
        report["active_model"] = None
        return report, None
    labelled_dates = data.index.get_level_values("date").unique().sort_values()
    train = data[data.index.get_level_values("date").isin(labelled_dates[:-1])]  # purge the most recent labelled month
    last_date = factors.index.get_level_values("date").max()
    current = factors.xs(last_date, level="date")
    report["trained_through"] = str(labelled_dates[-2].date()) if len(labelled_dates) > 1 else None
    report["n_training_rows"] = int(len(train))
    preds: dict[str, pd.Series] = {}
    for name, model in make_models().items():
        model.fit(_fillna_fit(train[FEATURES]), train["y"])
        preds[name] = pd.Series(model.predict_proba(_fillna_fit(current[FEATURES]))[:, 1], index=current.index)
        if name == "logistic":
            coef = model.named_steps["logisticregression"].coef_[0]
            imp = [{"feature": f, "importance": float(abs(c)), "direction": float(c)} for f, c in zip(FEATURES, coef)]
        else:
            recent = train[train.index.get_level_values("date").isin(labelled_dates[-13:-1])]
            pi = permutation_importance(model, _fillna_fit(recent[FEATURES]), recent["y"], n_repeats=5, random_state=7, scoring="roc_auc")
            imp = [{"feature": f, "importance": float(v), "direction": None} for f, v in zip(FEATURES, pi.importances_mean)]
        report["models"][name]["feature_importance"] = sorted(imp, key=lambda x: -x["importance"])
        report["models"][name]["current_predictions"] = [{"symbol": s, "model_score": float(v)} for s, v in preds[name].nlargest(25).items()]
    report["drift"] = [{"feature": f, "psi": (None if not np.isfinite(v) else v),
                        "level": "n/a" if not np.isfinite(v) else ("stable" if v < 0.1 else "moderate" if v < 0.25 else "significant")}
                       for f in FEATURES for v in [psi(train[f].to_numpy(dtype=float), current[f].to_numpy(dtype=float))]]
    active = None
    if report["models"]["gradient_boosting"]["validated"]:
        active = "gradient_boosting"
    elif report["models"]["logistic"]["validated"]:
        active = "logistic"
    report["active_model"] = active
    report["as_of"] = str(last_date.date())
    return report, (preds[active] if active else None)

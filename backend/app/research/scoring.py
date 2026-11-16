"""0-100 research score.

score = sum_i w_i * c_i / sum_i w_i over components with data, where c_i is a 0-100 component:
  factor components  -> cross-sectional percentile of the composite factor z-score in the screened universe
  technical          -> rule-based trend/momentum state of the individual stock
  market             -> market-regime reading (identical for all stocks)
  ml                 -> percentile of the model's out-of-sample ranking, only if the model is validated

The score is a RANKING AID. It is not a probability of profit and is never displayed as one.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field

from .factors import factor_scores, percentile
from .regime import REGIME_COMPONENT_SCORE

COMPONENT_LABELS = {
    "value": "Valuation (earnings, EBIT/EV, book, free cash flow yields)",
    "quality": "Quality and profitability (gross profitability, ROIC, accruals, Piotroski)",
    "momentum": "Price momentum and relative strength (12-1 and 6-1 month)",
    "earnings": "Earnings momentum (SUE, quarterly revenue growth)",
    "low_vol": "Low volatility",
    "investment": "Conservative investment (low asset growth)",
    "financial_strength": "Financial strength (coverage, leverage, liquidity)",
    "technical": "Technical trend state",
    "market": "Market conditions",
    "ml": "Machine-learning ranking (validated models only)",
}
FACTOR_COMPONENTS = ["value", "quality", "momentum", "earnings", "low_vol", "investment", "financial_strength"]


class ScoreConfig(BaseModel):
    weights: dict[str, float] = Field(default_factory=lambda: {
        "value": 20.0, "quality": 15.0, "momentum": 20.0, "earnings": 10.0, "low_vol": 10.0,
        "investment": 5.0, "financial_strength": 5.0, "technical": 10.0, "market": 5.0, "ml": 0.0,
    })
    strong_buy: float = 80.0
    buy: float = 68.0
    sell: float = 30.0
    score_change_alert: float = 10.0


def technical_component(row: pd.Series) -> tuple[float, list[dict[str, Any]]]:
    """Average of binary/graded trend checks, scaled to 0-100. Returns (score, checks)."""
    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool | None, detail: str) -> None:
        checks.append({"name": name, "passed": ok, "detail": detail})

    def f(k: str) -> float:
        v = row.get(k)
        return float(v) if v is not None and np.isfinite(v) else float("nan")

    p, s50, s200 = f("price"), f("sma_50"), f("sma_200")
    add("Price above 200-day average", None if not np.isfinite(s200) else p > s200, f"price {p:.2f} vs 200-day {s200:.2f}")
    add("Price above 50-day average", None if not np.isfinite(s50) else p > s50, f"price {p:.2f} vs 50-day {s50:.2f}")
    add("50-day above 200-day average", None if not (np.isfinite(s50) and np.isfinite(s200)) else s50 > s200, f"50-day {s50:.2f} vs 200-day {s200:.2f}")
    mh = f("macd_hist")
    add("MACD histogram positive", None if not np.isfinite(mh) else mh > 0, f"MACD histogram {mh:.3f}")
    r = f("rsi_14")
    add("RSI between 40 and 75", None if not np.isfinite(r) else 40 <= r <= 75, f"RSI(14) {r:.1f}" + (" (overbought)" if r > 75 else " (weak)" if r < 40 else ""))
    d = f("dist_52w_high")
    add("Within 15% of 52-week high", None if not np.isfinite(d) else d >= -0.15, f"{d:.1%} from 52-week high")
    vals = [c["passed"] for c in checks if c["passed"] is not None]
    return (float(np.mean(vals)) * 100.0 if vals else float("nan")), checks


def score_universe(cross: pd.DataFrame, cfg: ScoreConfig, regime: str, ml_rank: pd.Series | None = None) -> pd.DataFrame:
    """Score one cross-section of SCREENED stocks (index = symbol)."""
    fs = factor_scores(cross)
    comp = pd.DataFrame(index=cross.index)
    for name in FACTOR_COMPONENTS:
        comp[name] = percentile(fs[name])
    comp["size_z"] = fs["size"]
    comp["reversal_z"] = fs["reversal"]
    tech = cross.apply(technical_component, axis=1)
    comp["technical"] = [t[0] for t in tech]
    comp["market"] = REGIME_COMPONENT_SCORE.get(regime, 50.0)
    comp["ml"] = percentile(ml_rank.reindex(cross.index)) if ml_rank is not None else np.nan
    w = pd.Series({k: v for k, v in cfg.weights.items() if v > 0 and k in comp.columns})
    vals = comp[w.index]
    wmat = vals.notna().mul(w, axis=1)
    total_w = w.sum()
    used_w = wmat.sum(axis=1)
    out = comp.copy()
    out["score"] = (vals.fillna(0.0).mul(w, axis=1)).sum(axis=1) / used_w.where(used_w > 0)
    out["coverage"] = used_w / total_w if total_w > 0 else np.nan
    out["data_quality"] = pd.cut(out["coverage"], [-0.01, 0.55, 0.75, 0.9, 1.01], labels=["D", "C", "B", "A"]).astype(str)
    for name in FACTOR_COMPONENTS:
        out[f"{name}_z"] = fs[name]
        out[f"{name}_n"] = fs[f"{name}_n"]
    out["technical_checks"] = [t[1] for t in tech]
    return out


def contributions(row: pd.Series, cfg: ScoreConfig) -> list[dict[str, Any]]:
    """Per-component contribution to the score (points), for the explanation payload."""
    w = {k: v for k, v in cfg.weights.items() if v > 0}
    avail = {k: float(row[k]) for k in w if k in row.index and np.isfinite(row[k])}
    used = sum(w[k] for k in avail)
    out = []
    for k, weight in w.items():
        has = k in avail
        out.append({"component": k, "label": COMPONENT_LABELS.get(k, k), "weight": weight,
                    "component_score": avail.get(k), "effective_weight": (weight / used) if has and used else 0.0,
                    "contribution": (avail[k] * weight / used) if has and used else None,
                    "status": "ok" if has else "missing (weight redistributed)"})
    return out

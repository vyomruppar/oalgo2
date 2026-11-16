"""Price-data validation. Returns issues instead of silently repairing data."""
from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd

from .yahoo import last_bar_age_days


def validate_prices(df: pd.DataFrame, now: datetime | None = None, stale_after_days: int = 4) -> list[dict]:
    issues: list[dict] = []
    if df is None or df.empty:
        return [{"code": "empty", "severity": "error", "detail": "no price rows"}]
    bad_hl = int(((df["high"] < df["low"]) | (df["high"] < df[["open", "close"]].max(axis=1) * 0.999)
                  | (df["low"] > df[["open", "close"]].min(axis=1) * 1.001)).sum())
    if bad_hl:
        issues.append({"code": "ohlc_inconsistent", "severity": "warn", "detail": f"{bad_hl} bars with high/low inconsistent with open/close"})
    r = df["adj_close"].pct_change().dropna()
    jumps = r[(r.abs() > 0.6)]
    if len(jumps):
        issues.append({"code": "extreme_move", "severity": "warn",
                       "detail": f"{len(jumps)} daily moves beyond 60% (possible unadjusted corporate action); first {jumps.index[0].date()}"})
    gaps = pd.Series(df.index[1:] - df.index[:-1]).dt.days
    big = int((gaps > 10).sum())
    if big:
        issues.append({"code": "date_gap", "severity": "warn", "detail": f"{big} gaps longer than 10 calendar days (halts or missing data)"})
    zero_vol = float((df["volume"].tail(60) <= 0).mean())
    if zero_vol > 0.2:
        issues.append({"code": "zero_volume", "severity": "warn", "detail": f"{zero_vol:.0%} of the last 60 bars have zero volume"})
    age = last_bar_age_days(df, now)
    if age > stale_after_days:
        issues.append({"code": "stale", "severity": "error", "detail": f"last bar {df.index[-1].date()} is {age} business days old"})
    if not np.isfinite(df[["open", "high", "low", "close", "adj_close"]].to_numpy()).all():
        issues.append({"code": "non_finite", "severity": "error", "detail": "non-finite price values"})
    return issues

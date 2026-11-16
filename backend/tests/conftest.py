from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture()
def fixtures() -> Path:
    return FIX


@pytest.fixture()
def tmp_env(tmp_path, monkeypatch):
    """Isolated data directory + fresh SQLite database for tests that touch persistence."""
    monkeypatch.setenv("OALGO_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("OALGO_SCHEDULER_ENABLED", "false")
    from app import config, db
    config.get_settings.cache_clear()
    db.init_db()
    yield tmp_path
    config.get_settings.cache_clear()


def make_prices(n: int = 600, seed: int = 0, start: str = "2022-01-03", drift: float = 0.0004, vol: float = 0.015,
                price0: float = 50.0, volume: float = 2e6) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range(start, periods=n)
    r = rng.normal(drift, vol, n)
    close = price0 * np.exp(np.cumsum(r))
    open_ = np.r_[price0, close[:-1]] * (1 + rng.normal(0, 0.003, n))
    high = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, 0.004, n)))
    low = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, 0.004, n)))
    df = pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "adj_close": close,
                       "volume": volume * (1 + np.abs(rng.normal(0, 0.3, n))), "dividend": 0.0, "split": 1.0}, index=idx)
    df.index.name = "date"
    return df


def make_snapshots(dates: pd.DatetimeIndex, seed: int = 0, scale: float = 1e9) -> pd.DataFrame:
    """Synthetic quarterly fundamentals snapshots filed on `dates`."""
    from app.research.fundamentals import derive_metrics
    rng = np.random.default_rng(seed)
    rows = []
    for i, d in enumerate(dates):
        g = 1 + 0.02 * i
        rev = scale * g * (1 + rng.normal(0, 0.02))
        ni = 0.1 * rev * (1 + rng.normal(0, 0.1))
        row = {"filed": d, "period_end": d - pd.Timedelta(days=35), "fy_end": d - pd.Timedelta(days=35), "q_end": d - pd.Timedelta(days=35),
               "ttm_basis": "ttm", "sue": float(rng.normal()), "shares_cover": 1e8, "shares_cover_date": d - pd.Timedelta(days=10),
               "shares_bs": 1e8, "shares_diluted": 1.02e8, "balance_date": d - pd.Timedelta(days=35),
               "net_income_q": ni / 4, "net_income_q_prev_year": ni / 4.2, "revenue_q": rev / 4, "revenue_q_prev_year": rev / 4.3}
        flows = {"revenue": rev, "cogs": 0.6 * rev, "gross_profit": 0.4 * rev, "operating_income": 0.15 * rev, "pretax_income": 0.13 * rev,
                 "net_income": ni, "interest_expense": 0.01 * rev, "tax": 0.03 * rev, "da": 0.04 * rev, "ocf": 1.2 * ni, "capex": 0.05 * rev,
                 "dividends_paid": 0.02 * rev, "buybacks": 0.01 * rev, "sbc": 0.01 * rev}
        for k, v in flows.items():
            row[f"{k}_ttm"], row[f"{k}_fy"], row[f"{k}_fy_prev"] = v, v, v / 1.05
        stocks = {"assets": 2 * rev, "current_assets": 0.8 * rev, "liabilities": rev, "current_liabilities": 0.4 * rev, "equity": rev,
                  "retained_earnings": 0.5 * rev, "cash": 0.2 * rev, "lt_debt": 0.4 * rev, "st_debt": 0.05 * rev, "goodwill": 0.1 * rev}
        for k, v in stocks.items():
            row[k], row[f"{k}_fy"], row[f"{k}_fy_prev"] = v, v, v / 1.04
        rows.append(row)
    return derive_metrics(pd.DataFrame(rows).set_index("filed"))

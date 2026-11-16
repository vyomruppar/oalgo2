"""Cross-sectional research panel: one row per (date, symbol) built ONLY from information available
at that date. The same builder serves live scoring (last date), backtests and ML (history), so a
truncation test on this module covers look-ahead bias for all three.

Timing convention: features at date t use prices up to and including the close of t and
fundamentals from filings filed strictly before t. Trades based on them happen at the open of t+1.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

TRADING_DAYS = 252

FUND_COLS = [
    "revenue_ttm", "net_income_ttm", "operating_income_ttm", "ebitda_ttm", "fcf_ttm", "ocf_ttm", "gross_profit_ttm",
    "assets", "liabilities", "equity", "cash", "total_debt", "net_debt", "current_assets", "current_liabilities",
    "retained_earnings", "shares_cover", "shares_bs", "shares_diluted", "dividends_paid_ttm", "buybacks_ttm",
    "gross_margin", "operating_margin", "net_margin", "fcf_margin", "roe", "roa", "roic", "gross_profitability",
    "accruals", "cash_conversion", "asset_growth", "revenue_growth", "revenue_growth_q", "earnings_growth",
    "current_ratio", "debt_to_equity", "net_debt_to_ebitda", "interest_coverage", "sbc_to_revenue",
    "piotroski", "piotroski_n", "sue",
]


@dataclass
class PriceMatrices:
    close: pd.DataFrame      # split-adjusted close
    adj: pd.DataFrame        # split- and dividend-adjusted close (total return)
    open: pd.DataFrame
    high: pd.DataFrame
    low: pd.DataFrame
    volume: pd.DataFrame
    split: pd.DataFrame      # split ratio on the ex-date, 1.0 otherwise

    @property
    def dates(self) -> pd.DatetimeIndex:
        return self.close.index


def build_matrices(prices: dict[str, pd.DataFrame], calendar: pd.DatetimeIndex | None = None) -> PriceMatrices:
    if calendar is None:
        calendar = pd.DatetimeIndex(sorted(set().union(*[set(df.index) for df in prices.values()])))
    def wide(col: str, fill: float | None = None) -> pd.DataFrame:
        m = pd.DataFrame({s: df[col] for s, df in prices.items()}).reindex(calendar)
        return m if fill is None else m.fillna(fill)
    return PriceMatrices(wide("close"), wide("adj_close"), wide("open"), wide("high"), wide("low"),
                         wide("volume"), wide("split", 1.0))


def month_end_dates(dates: pd.DatetimeIndex) -> pd.DatetimeIndex:
    s = pd.Series(dates, index=dates)
    return pd.DatetimeIndex(s.groupby([dates.year, dates.month]).last().values)


def future_split_factor(split: pd.Series) -> pd.Series:
    """F(t) = product of split ratios with ex-date strictly after t. A share count reported for date s
    must be multiplied by F(s) to be comparable with split-adjusted prices."""
    rev = split[::-1].cumprod()[::-1]
    return (rev / split).reindex(split.index)


def price_features(pm: PriceMatrices, dates: pd.DatetimeIndex) -> pd.DataFrame:
    """Price/volume features at each requested date (long format, MultiIndex [date, symbol])."""
    adj, close, vol = pm.adj, pm.close, pm.volume
    ret = adj.pct_change(fill_method=None)
    logret = np.log(adj).diff()
    feats = {
        "price": close,
        "ret_1m": adj / adj.shift(21) - 1,
        "mom_12_1": adj.shift(21) / adj.shift(252) - 1,          # Jegadeesh-Titman, skipping the latest month
        "mom_6_1": adj.shift(21) / adj.shift(126) - 1,
        "vol_252": logret.rolling(252, min_periods=200).std() * np.sqrt(TRADING_DAYS),
        "vol_63": logret.rolling(63, min_periods=50).std() * np.sqrt(TRADING_DAYS),
        "adv_dollar_63": (close * vol).rolling(63, min_periods=40).mean(),
        "sma_50": close.rolling(50, min_periods=50).mean(),
        "sma_200": close.rolling(200, min_periods=200).mean(),
        "high_252": close.rolling(252, min_periods=200).max(),
        "n_bars": close.notna().cumsum(),
        "max_dd_252": (adj / adj.rolling(252, min_periods=120).max() - 1).rolling(252, min_periods=120).min(),
        "ret_1d": ret,
        "vol_ratio_20": vol / vol.rolling(20, min_periods=20).mean().shift(1),
    }
    out = pd.concat({k: v.reindex(dates).stack(future_stack=True) for k, v in feats.items()}, axis=1)
    out.index.names = ["date", "symbol"]
    out["dist_52w_high"] = out["price"] / out["high_252"] - 1
    out["above_sma_200"] = (out["price"] > out["sma_200"]).where(out["sma_200"].notna())
    return out


def fundamentals_asof(snapshots: dict[str, pd.DataFrame], dates: pd.DatetimeIndex, max_age_days: int = 200) -> pd.DataFrame:
    """Last snapshot filed strictly before each date. Snapshots older than `max_age_days` after their
    filing are treated as missing (the company stopped filing, or data are stale)."""
    frames = []
    left = pd.DataFrame({"date": dates})
    for sym, snap in snapshots.items():
        if snap is None or snap.empty:
            continue
        cols = [c for c in FUND_COLS if c in snap.columns] + [c for c in ("shares_cover_date", "balance_date", "period_end") if c in snap.columns]
        right = snap[cols].copy()
        right.index.name = None
        right.insert(0, "filed", pd.to_datetime(right.index))
        right = right.reset_index(drop=True).sort_values("filed")
        right["filed"] = right["filed"].astype(left["date"].dtype)
        m = pd.merge_asof(left, right, left_on="date", right_on="filed", allow_exact_matches=False)
        stale = (m["date"] - m["filed"]).dt.days > max_age_days
        m.loc[stale, [c for c in m.columns if c not in ("date",)]] = np.nan
        m["symbol"] = sym
        frames.append(m)
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True).set_index(["date", "symbol"]).sort_index()
    return out


def build_panel(pm: PriceMatrices, snapshots: dict[str, pd.DataFrame], dates: pd.DatetimeIndex,
                sectors: dict[str, str] | None = None) -> pd.DataFrame:
    px = price_features(pm, dates)
    fa = fundamentals_asof(snapshots, dates)
    panel = px.join(fa, how="left") if not fa.empty else px.assign(**{c: np.nan for c in FUND_COLS})
    for c in FUND_COLS + ["filed", "shares_cover_date", "balance_date"]:
        if c not in panel.columns:
            panel[c] = np.nan if c in FUND_COLS else pd.NaT
    # --- split-adjusted share count and market cap -------------------------------------------------------
    fsf = pd.concat({s: future_split_factor(pm.split[s]) for s in pm.split.columns}, axis=1)
    fsf_long = fsf.stack(future_stack=True)
    fsf_long.index.names = ["date", "symbol"]

    def factor_at(date_col: str) -> pd.Series:
        """Future-split factor at the share-count date (falls back to the filing date)."""
        d = pd.to_datetime(panel[date_col]).where(panel[date_col].notna(), pd.to_datetime(panel["filed"]))
        idx = pm.split.index
        pos = idx.searchsorted(d.fillna(idx[0]).to_numpy(), side="right") - 1
        pos = np.clip(pos, 0, len(idx) - 1)
        col = pm.split.columns.get_indexer(panel.index.get_level_values("symbol"))
        vals = fsf.to_numpy()[pos, col]
        return pd.Series(vals, index=panel.index).where(d.notna()).fillna(1.0)

    cover, diluted = panel["shares_cover"], panel["shares_diluted"]
    ratio = cover / diluted
    use_cover = cover.notna() & (diluted.isna() | ((ratio > 0.5) & (ratio < 2.0)))
    shares_raw = cover.where(use_cover, diluted)
    share_date_factor = factor_at("shares_cover_date").where(use_cover, factor_at("balance_date"))
    panel["shares"] = shares_raw * share_date_factor
    panel["market_cap"] = panel["shares"] * panel["price"]
    # Multi-class companies can report a share count for one class only (e.g. class-A equivalents),
    # which makes price x shares meaningless. Treat an implausibly small market cap as UNKNOWN rather
    # than rank on a wrong number: below 1% of trailing revenue AND below 1% of total assets.
    implausible = (panel["market_cap"] < 0.01 * panel["revenue_ttm"]) & (panel["market_cap"] < 0.01 * panel["assets"])
    panel["share_count_unreliable"] = implausible.fillna(False)
    panel.loc[implausible.fillna(False), ["market_cap", "shares"]] = np.nan
    panel["enterprise_value"] = panel["market_cap"] + panel["net_debt"].fillna(0.0)
    mc = panel["market_cap"].where(panel["market_cap"] > 0)
    ev = panel["enterprise_value"].where(panel["enterprise_value"] > 0)
    # --- valuation (yields, so that negative earnings rank low instead of breaking a ratio) --------------
    panel["earnings_yield"] = panel["net_income_ttm"] / mc
    panel["ebit_ev"] = panel["operating_income_ttm"] / ev            # Greenblatt earnings yield
    panel["book_to_market"] = panel["equity"] / mc
    panel["fcf_yield"] = panel["fcf_ttm"] / mc
    panel["sales_to_price"] = panel["revenue_ttm"] / mc
    panel["shareholder_yield"] = (panel["dividends_paid_ttm"].fillna(0) + panel["buybacks_ttm"].fillna(0)) / mc
    panel["pe"] = (mc / panel["net_income_ttm"].where(panel["net_income_ttm"] > 0))
    panel["ev_ebitda"] = ev / panel["ebitda_ttm"].where(panel["ebitda_ttm"] > 0)
    panel["pb"] = mc / panel["equity"].where(panel["equity"] > 0)
    panel["ps"] = mc / panel["revenue_ttm"].where(panel["revenue_ttm"] > 0)
    panel["log_mcap"] = np.log(mc)
    panel["days_since_filing"] = (panel.index.get_level_values("date") - pd.to_datetime(panel["filed"])).dt.days
    # Altman Z (not meaningful for financials -> NaN there)
    sec = pd.Series(panel.index.get_level_values("symbol").map(sectors or {}), index=panel.index).fillna("Unknown")
    panel["sector"] = sec
    need = ["current_assets", "current_liabilities", "retained_earnings", "operating_income_ttm", "revenue_ttm", "assets", "liabilities"]
    ta, tl = panel["assets"].where(panel["assets"] > 0), panel["liabilities"].where(panel["liabilities"] > 0)
    z = (1.2 * (panel["current_assets"] - panel["current_liabilities"]) / ta + 1.4 * panel["retained_earnings"] / ta
         + 3.3 * panel["operating_income_ttm"] / ta + 0.6 * panel["market_cap"] / tl + 1.0 * panel["revenue_ttm"] / ta)
    panel["altman_z"] = z.where(panel[need].notna().all(axis=1) & ~sec.isin(["Financials", "Real Estate"]))
    return panel


def forward_returns(pm: PriceMatrices, dates: pd.DatetimeIndex, horizon: int = 21) -> pd.Series:
    """Return from the OPEN of t+1 to the open of t+1+horizon, total-return adjusted.
    Used only as a label (ML target / information-coefficient study), never as a feature."""
    adj_open = pm.open * (pm.adj / pm.close)
    fwd = adj_open.shift(-(horizon + 1)) / adj_open.shift(-1) - 1
    out = fwd.reindex(dates).stack(future_stack=True)
    out.index.names = ["date", "symbol"]
    return out.rename(f"fwd_{horizon}")

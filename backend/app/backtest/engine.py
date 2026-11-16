"""Daily portfolio backtester.

Timing: target weights decided with data up to the close of a rebalance date t are traded at the
OPEN of the next session t+1. Positions are marked at the close. Prices are total-return adjusted
(dividends reinvested). Costs = (commission_bps + slippage_bps) of traded notional, each way.

All output is BACKTESTED (hypothetical). With the free data sources the universe contains only
currently listed companies, so results carry survivorship bias and overstate what was achievable.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from ..research.panel import PriceMatrices


@dataclass
class CostModel:
    commission_bps: float = 1.0
    slippage_bps: float = 9.0   # half-spread plus market impact for liquid US equities

    @property
    def rate(self) -> float:
        return (self.commission_bps + self.slippage_bps) / 1e4


@dataclass
class BacktestResult:
    returns: pd.Series
    equity: pd.Series
    weights_last: pd.Series
    trades: pd.DataFrame
    turnover_annual: float
    exposure_avg: float
    costs_total: float
    holdings_avg: float
    rebalance_log: list[dict[str, Any]] = field(default_factory=list)


def run_backtest(pm: PriceMatrices, targets: dict[pd.Timestamp, pd.Series], cost: CostModel | None = None,
                 initial: float = 1_000_000.0, start: pd.Timestamp | None = None, end: pd.Timestamp | None = None) -> BacktestResult:
    """`targets[t]` = desired portfolio weights (symbol -> weight, sum <= 1) decided at the close of t."""
    cost = cost or CostModel()
    dates = pm.dates
    syms = list(pm.close.columns)
    col = {s: i for i, s in enumerate(syms)}
    ratio = (pm.adj / pm.close).to_numpy()
    adj_close = pm.adj.ffill().to_numpy()                # carry last price through halts for valuation
    adj_open_raw = (pm.open.to_numpy() * ratio)          # NaN where the stock did not trade
    reb_dates = sorted(t for t in targets if t in pm.close.index)
    if not reb_dates:
        raise ValueError("no rebalance dates inside the price history")
    pos_of = {d: i for i, d in enumerate(dates)}
    pending: dict[int, pd.Series] = {}
    for t in reb_dates:
        i = pos_of[t] + 1
        if i < len(dates):
            pending[i] = targets[t]
    first = min(pending) if pending else len(dates)
    if start is not None:
        first = max(first, int(dates.searchsorted(start)))
    last = len(dates) if end is None else int(dates.searchsorted(end, side="right"))
    shares = np.zeros(len(syms))
    cash = initial
    invested = np.zeros(len(syms)); proceeds = np.zeros(len(syms)); opened = np.full(len(syms), -1)
    eq_vals, eq_idx, expo, nhold = [], [], [], []
    trades: list[dict[str, Any]] = []
    traded_notional = 0.0
    costs_total = 0.0
    log: list[dict[str, Any]] = []
    prev_close = np.where(np.isfinite(adj_close[first - 1]), adj_close[first - 1], 0.0) if first > 0 else np.zeros(len(syms))
    for i in range(first, last):
        if i in pending:
            w = pending[i]
            op = adj_open_raw[i]
            tradable = np.isfinite(op) & (op > 0)
            mark = np.where(tradable, op, prev_close)
            value = cash + float(np.nansum(shares * mark))
            tgt = np.zeros(len(syms))
            for s, wt in w.items():
                j = col.get(s)
                if j is not None and tradable[j] and wt > 0:
                    tgt[j] = wt
            tgt_sh = np.where(tradable, tgt * value / np.where(tradable, op, 1.0), shares)  # untradable: keep position
            delta = tgt_sh - shares
            notional = np.abs(delta) * np.where(tradable, op, 0.0)
            c = float(notional.sum()) * cost.rate
            # scale buys down slightly so that costs are paid from the portfolio, never from leverage
            buys = float((np.clip(delta, 0, None) * np.where(tradable, op, 0.0)).sum())
            sells = float((np.clip(-delta, 0, None) * np.where(tradable, op, 0.0)).sum())
            if buys > 0 and cash + sells - buys - c < 0:
                k = max(0.0, (cash + sells - c) / buys)
                delta = np.where(delta > 0, delta * k, delta)
                notional = np.abs(delta) * np.where(tradable, op, 0.0)
                c = float(notional.sum()) * cost.rate
                buys *= k
            for j in np.flatnonzero(np.abs(delta) > 1e-12):
                amt = delta[j] * op[j]
                if amt > 0:
                    if shares[j] <= 1e-12:
                        opened[j] = i; invested[j] = 0.0; proceeds[j] = 0.0
                    invested[j] += amt * (1 + cost.rate)
                else:
                    proceeds[j] += -amt * (1 - cost.rate)
                    if shares[j] + delta[j] <= 1e-9:
                        pnl = proceeds[j] - invested[j]
                        trades.append({"symbol": syms[j], "entry_date": dates[opened[j]], "exit_date": dates[i],
                                       "hold_days": int(i - opened[j]), "pnl": pnl,
                                       "pnl_pct": pnl / invested[j] if invested[j] > 0 else 0.0})
            shares = shares + delta
            shares[np.abs(shares) < 1e-9] = 0.0
            cash = cash + sells - buys - c
            traded_notional += float(notional.sum())
            costs_total += c
            log.append({"date": dates[i].date().isoformat(), "n_positions": int((shares > 0).sum()),
                        "traded_pct": float(notional.sum() / value) if value > 0 else 0.0, "cost": c})
        px = np.where(np.isfinite(adj_close[i]), adj_close[i], prev_close)
        pos_val = float(np.nansum(shares * px))
        eq = cash + pos_val
        eq_vals.append(eq); eq_idx.append(dates[i]); expo.append(pos_val / eq if eq > 0 else 0.0); nhold.append(int((shares > 0).sum()))
        prev_close = px
    equity = pd.Series(eq_vals, index=pd.DatetimeIndex(eq_idx), name="equity")
    rets = equity.pct_change()
    if len(equity):
        rets.iloc[0] = equity.iloc[0] / initial - 1
    years = max(len(equity) / 252.0, 1e-9)
    px_last = prev_close
    wl = pd.Series(shares * px_last / eq_vals[-1] if eq_vals else 0.0, index=syms)
    return BacktestResult(
        returns=rets, equity=equity, weights_last=wl[wl > 0].sort_values(ascending=False),
        trades=pd.DataFrame(trades), turnover_annual=float(traded_notional / 2.0 / max(equity.mean(), 1e-9) / years) if len(equity) else 0.0,
        exposure_avg=float(np.mean(expo)) if expo else 0.0, costs_total=costs_total,
        holdings_avg=float(np.mean(nhold)) if nhold else 0.0, rebalance_log=log)


def buy_and_hold(adj_close: pd.Series) -> pd.Series:
    """Daily total returns of holding one instrument (benchmarks)."""
    return adj_close.dropna().pct_change().dropna()


def segment_bounds(index: pd.DatetimeIndex, train: float = 0.5, validation: float = 0.25) -> dict[str, tuple[pd.Timestamp, pd.Timestamp]]:
    """Chronological train / validation / out-of-sample split of the evaluation window."""
    n = len(index)
    a, b = int(n * train), int(n * (train + validation))
    return {"train": (index[0], index[max(a - 1, 0)]), "validation": (index[a], index[max(b - 1, a)]),
            "out_of_sample": (index[b], index[-1])}

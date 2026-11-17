"""Real-holdings tracker. TRACKING ONLY.

The user records lots they own (symbol, shares, cost per share, purchase date). Nothing here creates,
routes or simulates an order; it values what is already owned from stored end-of-day prices.

Split handling: stored prices are split-adjusted to today, while a lot is entered in the shares and
price that applied on its purchase date. Multiplying the entered shares by the product of all splits
after the purchase date puts them on the same basis as the price series, for every date.
"""
from __future__ import annotations

import csv
import io
from datetime import date
from typing import Any, Callable

import numpy as np
import pandas as pd
from sqlalchemy import select

from ..db import Holding, Security, session
from ..research.panel import future_split_factor

PriceLoader = Callable[[str], "pd.DataFrame | None"]
RANGES = {"1m": 21, "3m": 63, "6m": 126, "1y": 252, "2y": 504, "5y": 1260, "all": 10 ** 6}


class HoldingError(ValueError):
    pass


def validate(symbol: str, shares: float, cost: float, purchase_date: str) -> tuple[str, str]:
    """Return (normalised symbol, ISO date) or raise HoldingError with a reason a person can act on."""
    sym = symbol.strip().upper().replace(".", "-")
    if not sym:
        raise HoldingError("ticker is required")
    if not (isinstance(shares, (int, float)) and np.isfinite(shares) and shares > 0):
        raise HoldingError("shares must be a positive number")
    if not (isinstance(cost, (int, float)) and np.isfinite(cost) and cost >= 0):
        raise HoldingError("cost per share must be zero or more")
    try:
        d = date.fromisoformat(str(purchase_date).strip())
    except ValueError as e:
        raise HoldingError("purchase date must be YYYY-MM-DD") from e
    if d > date.today():
        raise HoldingError("purchase date cannot be in the future")
    with session() as s:
        sec = s.get(Security, sym)
        if sec is None:
            raise HoldingError(f"{sym} is not in the verified NYSE/NASDAQ directory (OTC and other venues are not supported)")
    return sym, d.isoformat()


def add(symbol: str, shares: float, cost: float, purchase_date: str, note: str | None = None) -> int:
    sym, d = validate(symbol, shares, cost, purchase_date)
    with session() as s:
        h = Holding(symbol=sym, shares=float(shares), cost=float(cost), purchase_date=d, note=(note or None))
        s.add(h)
        s.flush()
        return h.id


def update(holding_id: int, shares: float, cost: float, purchase_date: str, note: str | None = None) -> None:
    with session() as s:
        h = s.get(Holding, holding_id)
        if h is None:
            raise HoldingError("holding not found")
        sym = h.symbol
    _, d = validate(sym, shares, cost, purchase_date)
    with session() as s:
        h = s.get(Holding, holding_id)
        h.shares, h.cost, h.purchase_date, h.note = float(shares), float(cost), d, (note or None)


def delete(holding_id: int) -> bool:
    with session() as s:
        h = s.get(Holding, holding_id)
        if h is None:
            return False
        s.delete(h)
        return True


def parse_csv(text: str) -> tuple[list[dict[str, Any]], list[str]]:
    """Parse `symbol,shares,cost,date[,note]` rows (header optional). Returns (rows, errors)."""
    rows, errors = [], []
    reader = csv.reader(io.StringIO(text.strip()))
    for i, r in enumerate(reader, 1):
        r = [c.strip() for c in r]
        if not r or not any(r):
            continue
        if i == 1 and r[0].lower() in ("symbol", "ticker"):
            continue
        if len(r) < 4:
            errors.append(f"line {i}: expected symbol,shares,cost,date")
            continue
        try:
            shares, cost = float(r[1].replace(",", "")), float(r[2].replace("$", "").replace(",", ""))
            sym, d = validate(r[0], shares, cost, r[3])
            rows.append({"symbol": sym, "shares": shares, "cost": cost, "purchase_date": d, "note": r[4] if len(r) > 4 and r[4] else None})
        except (ValueError, HoldingError) as e:
            errors.append(f"line {i}: {e}")
    return rows, errors


def import_csv(text: str) -> dict[str, Any]:
    """All-or-nothing import: nothing is saved if any line is invalid."""
    rows, errors = parse_csv(text)
    if errors or not rows:
        return {"imported": 0, "errors": errors or ["no rows found"]}
    with session() as s:
        for r in rows:
            s.add(Holding(**r))
    return {"imported": len(rows), "errors": []}


def lots() -> list[dict[str, Any]]:
    with session() as s:
        return [{"id": h.id, "symbol": h.symbol, "shares": h.shares, "cost": h.cost, "purchase_date": h.purchase_date, "note": h.note}
                for h in s.scalars(select(Holding).order_by(Holding.symbol, Holding.purchase_date)).all()]


def symbols() -> list[str]:
    return sorted({x["symbol"] for x in lots()})


def average_costs() -> dict[str, float]:
    """symbol -> share-weighted average cost on today's (split-adjusted) share basis is not needed for
    alerts; the entered average is close enough for a stop reference and is what the user recognises."""
    agg: dict[str, list[float]] = {}
    for x in lots():
        a = agg.setdefault(x["symbol"], [0.0, 0.0])
        a[0] += x["shares"] * x["cost"]
        a[1] += x["shares"]
    return {k: v[0] / v[1] for k, v in agg.items() if v[1] > 0}


def _adj_shares(lot: dict[str, Any], df: pd.DataFrame) -> float:
    """Entered shares converted to today's share basis (see module docstring)."""
    f = future_split_factor(df["split"])
    before = f[f.index <= pd.Timestamp(lot["purchase_date"])]
    factor = float(before.iloc[-1]) if len(before) else float(df["split"].prod())
    return lot["shares"] * factor


def summary(load_prices: PriceLoader, research: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    """Current positions aggregated by symbol, with totals. Missing prices stay missing (never zero)."""
    research = research or {}
    all_lots = lots()
    by: dict[str, dict[str, Any]] = {}
    missing: list[str] = []
    for lot in all_lots:
        sym = lot["symbol"]
        p = by.get(sym)
        if p is None:
            df = load_prices(sym)
            p = by[sym] = {"symbol": sym, "shares": 0.0, "invested": 0.0, "lots": 0, "_df": df}
            if df is None or df.empty:
                missing.append(sym)
        df = p["_df"]
        p["shares"] += _adj_shares(lot, df) if df is not None and len(df) else lot["shares"]
        p["invested"] += lot["shares"] * lot["cost"]
        p["lots"] += 1
        p["first_purchase"] = min(p.get("first_purchase", lot["purchase_date"]), lot["purchase_date"])
    out = []
    for sym, p in by.items():
        df = p.pop("_df")
        r = research.get(sym, {})
        row: dict[str, Any] = {**p, "avg_cost": p["invested"] / p["shares"] if p["shares"] else None, "company": r.get("company"),
                               "sector": r.get("sector"), "signal": r.get("signal"), "score": r.get("score"), "researched": bool(r)}
        if df is not None and len(df):
            c = df["close"]
            price, prev = float(c.iloc[-1]), (float(c.iloc[-2]) if len(c) > 1 else None)
            row.update({"price": price, "price_date": df.index[-1].date().isoformat(), "value": price * p["shares"],
                        "day_change_pct": (price / prev - 1) if prev else None,
                        "day_change": (price - prev) * p["shares"] if prev else None,
                        "gain": price * p["shares"] - p["invested"],
                        "gain_pct": (price * p["shares"] / p["invested"] - 1) if p["invested"] > 0 else None,
                        "spark": [round(float(v), 4) for v in c.tail(60)]})
        else:
            row.update({"price": None, "price_date": None, "value": None, "day_change_pct": None, "day_change": None,
                        "gain": None, "gain_pct": None, "spark": []})
        out.append(row)
    total = sum(r["value"] for r in out if r["value"] is not None)
    invested_priced = sum(r["invested"] for r in out if r["value"] is not None)
    for r in out:
        r["weight"] = (r["value"] / total) if r["value"] is not None and total > 0 else None
    day = sum(r["day_change"] for r in out if r["day_change"] is not None)
    out.sort(key=lambda r: -(r["value"] or 0))
    return {
        "label": "Your recorded holdings, valued at the last completed session's close. Tracking only; no orders are placed.",
        "positions": out, "lots": all_lots, "n_positions": len(out),
        "value": total if out else 0.0, "invested": sum(r["invested"] for r in out),
        "gain": (total - invested_priced) if out else 0.0,
        "gain_pct": (total / invested_priced - 1) if invested_priced > 0 else None,
        "day_change": day, "day_change_pct": (day / (total - day)) if total - day > 0 else None,
        "as_of": max((r["price_date"] for r in out if r["price_date"]), default=None),
        "missing_prices": missing,
    }


def history(load_prices: PriceLoader, benchmark_adj: pd.Series | None, rng: str = "all") -> dict[str, Any]:
    """Daily value of the holdings since the first purchase, with the amount invested, dividends received
    and a benchmark that puts the same dollars into SPY on the same dates (total return)."""
    all_lots = lots()
    if not all_lots:
        return {"empty": True, "series": []}
    frames: dict[str, pd.DataFrame] = {}
    for sym in {x["symbol"] for x in all_lots}:
        df = load_prices(sym)
        if df is not None and len(df):
            frames[sym] = df
    priced = [x for x in all_lots if x["symbol"] in frames]
    if not priced:
        return {"empty": True, "series": [], "note": "No stored prices for these holdings yet. Run a scan."}
    start = pd.Timestamp(min(x["purchase_date"] for x in priced))
    cal = pd.DatetimeIndex(sorted(set().union(*[set(df.index) for df in frames.values()])))
    cal = cal[cal >= start]
    if len(cal) == 0:
        return {"empty": True, "series": [], "note": "Holdings were bought after the last stored session."}
    value = pd.Series(0.0, index=cal)
    invested = pd.Series(0.0, index=cal)
    dividends = pd.Series(0.0, index=cal)
    bench = pd.Series(0.0, index=cal)
    b = benchmark_adj.dropna() if benchmark_adj is not None else None
    for lot in priced:
        df = frames[lot["symbol"]]
        sh = _adj_shares(lot, df)
        active = (cal >= pd.Timestamp(lot["purchase_date"])).astype(float)
        close = df["close"].reindex(cal).ffill()
        value += (close * sh * active).fillna(0.0)
        invested += lot["shares"] * lot["cost"] * active
        div = df["dividend"].reindex(cal).fillna(0.0)
        dividends += (div * sh * active).cumsum()
        if b is not None and len(b):
            after = b[b.index >= pd.Timestamp(lot["purchase_date"])]
            if len(after):
                bb = b.reindex(cal).ffill()
                bench += (lot["shares"] * lot["cost"] * bb / float(after.iloc[0]) * active).fillna(0.0)
    n = RANGES.get(rng, 10 ** 6)
    sl = slice(-n, None)
    total = value + dividends
    return {
        "empty": False, "range": rng, "start": cal[0].date().isoformat(), "end": cal[-1].date().isoformat(),
        "series": [[d.date().isoformat(), round(float(v), 2), round(float(i), 2), round(float(dv), 2), (round(float(bv), 2) if b is not None else None)]
                   for d, v, i, dv, bv in zip(cal[sl], value[sl], invested[sl], dividends[sl], bench[sl])],
        "columns": ["date", "value", "invested", "dividends_cumulative", "benchmark"],
        "total_return_pct": float(total.iloc[-1] / invested.iloc[-1] - 1) if invested.iloc[-1] > 0 else None,
        "benchmark_return_pct": float(bench.iloc[-1] / invested.iloc[-1] - 1) if b is not None and invested.iloc[-1] > 0 else None,
        "dividends_received": float(dividends.iloc[-1]),
        "note": "Market value uses split-adjusted closes. Dividends are added as cash, not reinvested. The benchmark invests the "
                "same dollars in SPY (dividends reinvested) on each purchase date. Sales and cash balances are not tracked.",
        "unpriced": sorted({x["symbol"] for x in all_lots} - set(frames)),
    }

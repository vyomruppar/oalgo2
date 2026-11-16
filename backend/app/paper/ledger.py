"""Paper-trading ledger. HYPOTHETICAL ONLY: there is no broker connection anywhere in this codebase
and no code path that can place a real order.

Fill model: an order entered after seeing the close of date D fills at the OPEN of the first session
after D, adjusted by slippage, plus commission. Orders stay pending until that bar exists.
"""
from __future__ import annotations

from typing import Any, Callable

import pandas as pd
from sqlalchemy import select

from ..db import PaperEquity, PaperPosition, PaperTrade, kv_get, kv_set, session

INITIAL_CASH = 100_000.0
SLIPPAGE_BPS = 9.0
COMMISSION_BPS = 1.0
PriceLoader = Callable[[str], "pd.DataFrame | None"]


def get_cash() -> float:
    return float(kv_get("paper:cash", INITIAL_CASH))


def reset(initial_cash: float = INITIAL_CASH) -> None:
    with session() as s:
        for model in (PaperTrade, PaperPosition, PaperEquity):
            s.query(model).delete()
    kv_set("paper:cash", initial_cash)
    kv_set("paper:initial_cash", initial_cash)
    kv_set("paper:dividends", 0.0)


def place_order(symbol: str, side: str, quantity: float, last_price_date: str, note: str | None = None) -> int:
    side = side.upper()
    if side not in ("BUY", "SELL"):
        raise ValueError("side must be BUY or SELL")
    if quantity <= 0:
        raise ValueError("quantity must be positive")
    with session() as s:
        if side == "SELL":
            pos = s.get(PaperPosition, symbol)
            if pos is None or pos.quantity < quantity - 1e-9:
                raise ValueError("cannot sell more than the paper position (short selling is not modelled)")
        t = PaperTrade(symbol=symbol, side=side, quantity=quantity, status="pending", requested_price_date=last_price_date, note=note)
        s.add(t)
        s.flush()
        return t.id


def process(load_prices: PriceLoader, benchmark: pd.Series | None = None) -> dict[str, Any]:
    """Fill pending orders, apply splits and dividends, and append daily equity marks."""
    filled, rejected = 0, 0
    cash = get_cash()
    dividends_total = float(kv_get("paper:dividends", 0.0))
    cache: dict[str, pd.DataFrame | None] = {}

    def px(sym: str) -> pd.DataFrame | None:
        if sym not in cache:
            cache[sym] = load_prices(sym)
        return cache[sym]

    with session() as s:
        # 1) corporate actions on held positions since their last action date
        for pos in s.scalars(select(PaperPosition)).all():
            df = px(pos.symbol)
            if df is None or df.empty:
                continue
            new = df[df.index > pd.Timestamp(pos.last_action_date)]
            for dt, row in new.iterrows():
                if row["split"] != 1.0 and row["split"] > 0:
                    pos.quantity *= float(row["split"])
                    pos.avg_cost /= float(row["split"])
                if row["dividend"] > 0:
                    amt = float(row["dividend"]) * pos.quantity
                    cash += amt
                    dividends_total += amt
            if len(new):
                pos.last_action_date = new.index[-1].date().isoformat()
        # 2) pending orders
        for t in s.scalars(select(PaperTrade).where(PaperTrade.status == "pending").order_by(PaperTrade.id)).all():
            df = px(t.symbol)
            if df is None or df.empty:
                continue
            nxt = df[df.index > pd.Timestamp(t.requested_price_date)]
            if nxt.empty:
                continue  # the next session has not printed yet
            bar_date, bar = nxt.index[0], nxt.iloc[0]
            slip = SLIPPAGE_BPS / 1e4
            price = float(bar["open"]) * (1 + slip if t.side == "BUY" else 1 - slip)
            notional = price * t.quantity
            commission = notional * COMMISSION_BPS / 1e4
            pos = s.get(PaperPosition, t.symbol)
            if t.side == "BUY":
                if notional + commission > cash + 1e-6:
                    t.status, t.note = "rejected", f"insufficient paper cash ({cash:,.2f}) for {notional + commission:,.2f}"
                    rejected += 1
                    continue
                cash -= notional + commission
                if pos is None:
                    s.add(PaperPosition(symbol=t.symbol, quantity=t.quantity, avg_cost=(notional + commission) / t.quantity,
                                        opened_at=bar_date.date().isoformat(), last_action_date=df.index[-1].date().isoformat()))
                else:
                    total = pos.avg_cost * pos.quantity + notional + commission
                    pos.quantity += t.quantity
                    pos.avg_cost = total / pos.quantity
            else:
                if pos is None or pos.quantity < t.quantity - 1e-9:
                    t.status, t.note = "rejected", "position no longer large enough"
                    rejected += 1
                    continue
                cash += notional - commission
                t.realized_pnl = (price - pos.avg_cost) * t.quantity - commission
                pos.quantity -= t.quantity
                if pos.quantity <= 1e-9:
                    s.delete(pos)
            t.status, t.fill_date, t.fill_price = "filled", bar_date.date().isoformat(), price
            t.cost = commission + abs(price - float(bar["open"])) * t.quantity
            filled += 1
        s.flush()
        # 3) daily equity marks for every session since the last mark
        positions = s.scalars(select(PaperPosition)).all()
        last_mark = s.scalars(select(PaperEquity).order_by(PaperEquity.date.desc()).limit(1)).first()
        ref = benchmark.dropna() if benchmark is not None else None
        if ref is not None and len(ref):
            dates = ref.index[ref.index > pd.Timestamp(last_mark.date)] if last_mark else ref.index[-1:]
            for dt in dates:
                # only the latest mark reflects current holdings exactly; earlier gaps use current positions
                pv = 0.0
                for pos in positions:
                    df = px(pos.symbol)
                    if df is None:
                        continue
                    hist = df.loc[:dt, "close"]
                    if len(hist):
                        pv += float(hist.iloc[-1]) * pos.quantity
                d = dt.date().isoformat()
                row = s.get(PaperEquity, d)
                if row is None:
                    s.add(PaperEquity(date=d, cash=cash, positions_value=pv, equity=cash + pv, benchmark_close=float(ref.loc[dt])))
                else:
                    row.cash, row.positions_value, row.equity = cash, pv, cash + pv
            if last_mark is not None and not len(dates):
                pv = sum(float(px(p.symbol)["close"].iloc[-1]) * p.quantity for p in positions if px(p.symbol) is not None)
                last_mark.cash, last_mark.positions_value, last_mark.equity = cash, pv, cash + pv
    kv_set("paper:cash", cash)
    kv_set("paper:dividends", dividends_total)
    return {"filled": filled, "rejected": rejected, "cash": cash}


def snapshot(load_prices: PriceLoader) -> dict[str, Any]:
    cash = get_cash()
    initial = float(kv_get("paper:initial_cash", INITIAL_CASH))
    with session() as s:
        positions = s.scalars(select(PaperPosition)).all()
        trades = s.scalars(select(PaperTrade).order_by(PaperTrade.id.desc()).limit(200)).all()
        marks = s.scalars(select(PaperEquity).order_by(PaperEquity.date)).all()
        pos_out, pv = [], 0.0
        for p in positions:
            df = load_prices(p.symbol)
            price = float(df["close"].iloc[-1]) if df is not None and len(df) else None
            pdate = df.index[-1].date().isoformat() if df is not None and len(df) else None
            mv = price * p.quantity if price is not None else None
            pv += mv or 0.0
            pos_out.append({"symbol": p.symbol, "quantity": p.quantity, "avg_cost": p.avg_cost, "price": price, "price_date": pdate,
                            "market_value": mv, "unrealized_pnl": (price - p.avg_cost) * p.quantity if price is not None else None,
                            "unrealized_pct": (price / p.avg_cost - 1) if price is not None and p.avg_cost else None, "opened_at": p.opened_at})
        equity = cash + pv
        for x in pos_out:
            x["weight"] = (x["market_value"] / equity) if x["market_value"] is not None and equity else None
        realized = sum(t.realized_pnl or 0.0 for t in s.scalars(select(PaperTrade).where(PaperTrade.status == "filled")).all())
        return {
            "label": "paper-traded (hypothetical; no real orders are ever placed)",
            "cash": cash, "initial_cash": initial, "positions_value": pv, "equity": equity,
            "total_return": equity / initial - 1 if initial else None,
            "realized_pnl": realized, "unrealized_pnl": sum(x["unrealized_pnl"] or 0.0 for x in pos_out),
            "dividends_received": float(kv_get("paper:dividends", 0.0)),
            "positions": sorted(pos_out, key=lambda x: -(x["market_value"] or 0)),
            "trades": [{"id": t.id, "created_at": t.created_at.isoformat(), "symbol": t.symbol, "side": t.side, "quantity": t.quantity,
                        "status": t.status, "requested_price_date": t.requested_price_date, "fill_date": t.fill_date,
                        "fill_price": t.fill_price, "cost": t.cost, "realized_pnl": t.realized_pnl, "note": t.note} for t in trades],
            "equity_curve": [{"date": m.date, "equity": m.equity, "cash": m.cash, "benchmark_close": m.benchmark_close} for m in marks],
            "fill_model": f"next session open, {SLIPPAGE_BPS:.0f} bps slippage, {COMMISSION_BPS:.0f} bp commission",
        }

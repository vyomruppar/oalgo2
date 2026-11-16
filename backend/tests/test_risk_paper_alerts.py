import numpy as np
import pandas as pd
import pytest
from sqlalchemy import select

from app.risk import portfolio as risk
from tests.conftest import make_prices


def test_risk_contributions_sum_to_one():
    rng = np.random.default_rng(0)
    r = pd.DataFrame(rng.normal(0, [0.01, 0.02, 0.03], (500, 3)), columns=list("ABC"))
    rc = risk.risk_contributions(pd.Series({"A": 0.5, "B": 0.3, "C": 0.2}), risk.ledoit_wolf_cov(r))
    assert rc["risk_pct"].sum() == pytest.approx(1.0)
    assert rc.loc["C", "risk_pct"] > rc.loc["C", "weight"]        # the volatile asset contributes more risk than weight


def test_position_sizing_caps():
    s = risk.vol_scaled_size(0.30, 100_000, 50.0, risk_budget=0.01, max_weight=0.10)
    monthly = 0.30 * np.sqrt(21 / 252)
    assert s["weight"] == pytest.approx(min(0.10, 0.01 / monthly)) and s["shares"] == int(s["weight"] * 100_000 / 50)
    assert risk.vol_scaled_size(0.05, 100_000, 50.0)["binding"] == "maximum position weight"
    assert risk.vol_scaled_size(0.30, 1e9, 50.0, adv_dollar=1e6)["binding"].startswith("liquidity")
    assert risk.vol_scaled_size(float("nan"), 1e5, 50.0)["weight"] == 0.0


def test_portfolio_analysis():
    px = {s: make_prices(400, seed=i) for i, s in enumerate(["A", "B", "C"])}
    adj = pd.DataFrame({s: d["adj_close"] for s, d in px.items()})
    pos = pd.DataFrame({"quantity": {"A": 100.0, "B": 50.0, "C": 10.0}, "price": {s: float(d["close"].iloc[-1]) for s, d in px.items()}})
    out = risk.analyze(pos, adj, adj["A"], {"A": "Technology", "B": "Technology", "C": "Energy"}, {"A": 1.0}, {"A": 1e7}, cash=1000.0)
    assert out["n_positions"] == 3 and out["gross_exposure"] < 1.0
    assert sum(x["weight"] for x in out["sector_exposure"]) == pytest.approx(out["gross_exposure"])
    assert out["var_99"]["hist_var"] >= out["var_95"]["hist_var"] > 0
    assert sum(x["risk_pct"] for x in out["risk_contributions"]) == pytest.approx(1.0)
    assert out["position_scenarios"][0]["stop_loss_pct_of_equity"] < 0
    assert risk.analyze(pd.DataFrame(), adj, None, {})["empty"] is True


# ---- paper ledger -------------------------------------------------------------------------------------
def loader(frames):
    return lambda sym: frames.get(sym)


def test_paper_order_fills_at_next_open_with_costs(tmp_env):
    from app.db import PaperPosition, PaperTrade, session
    from app.paper import ledger
    ledger.reset(10_000.0)
    df = make_prices(50, seed=1)
    oid = ledger.place_order("AAA", "BUY", 10, df.index[30].date().isoformat())
    ledger.process(loader({"AAA": df.iloc[:31]}))
    with session() as s:
        assert s.get(PaperTrade, oid).status == "pending"                 # next session not available yet
    ledger.process(loader({"AAA": df}))
    with session() as s:
        t = s.get(PaperTrade, oid)
        assert t.status == "filled" and t.fill_date == df.index[31].date().isoformat()
        expected = df["open"].iloc[31] * (1 + ledger.SLIPPAGE_BPS / 1e4)
        assert t.fill_price == pytest.approx(expected)
        pos = s.get(PaperPosition, "AAA")
        assert pos.quantity == 10 and pos.avg_cost > expected              # commission included in cost basis
    assert ledger.get_cash() == pytest.approx(10_000 - expected * 10 * (1 + ledger.COMMISSION_BPS / 1e4))


def test_paper_rejections_and_no_shorting(tmp_env):
    from app.db import PaperTrade, session
    from app.paper import ledger
    ledger.reset(100.0)
    df = make_prices(50, seed=2)
    oid = ledger.place_order("AAA", "BUY", 1000, df.index[10].date().isoformat())
    ledger.process(loader({"AAA": df}))
    with session() as s:
        t = s.get(PaperTrade, oid)
        assert t.status == "rejected" and "insufficient" in t.note
    with pytest.raises(ValueError):
        ledger.place_order("AAA", "SELL", 1, df.index[10].date().isoformat())
    with pytest.raises(ValueError):
        ledger.place_order("AAA", "HOLD", 1, df.index[10].date().isoformat())
    assert ledger.get_cash() == 100.0


def test_paper_dividends_splits_and_realized_pnl(tmp_env):
    from app.db import PaperPosition, PaperTrade, session
    from app.paper import ledger
    ledger.reset(100_000.0)
    df = make_prices(60, seed=3)
    df.loc[df.index[40], "dividend"] = 0.5
    df.loc[df.index[45], "split"] = 2.0
    ledger.place_order("AAA", "BUY", 100, df.index[20].date().isoformat())
    ledger.process(loader({"AAA": df.iloc[:30]}))
    cash_after_buy = ledger.get_cash()
    ledger.process(loader({"AAA": df}))
    assert ledger.get_cash() == pytest.approx(cash_after_buy + 0.5 * 100)   # dividend credited once
    with session() as s:
        pos = s.get(PaperPosition, "AAA")
        assert pos.quantity == 200
        cost_basis = pos.avg_cost
    ledger.process(loader({"AAA": df}))
    assert ledger.get_cash() == pytest.approx(cash_after_buy + 50)          # idempotent: no double credit
    sid = ledger.place_order("AAA", "SELL", 200, df.index[50].date().isoformat())
    ledger.process(loader({"AAA": df}))
    with session() as s:
        t = s.get(PaperTrade, sid)
        assert t.status == "filled"
        assert t.realized_pnl == pytest.approx((t.fill_price - cost_basis) * 200 - t.fill_price * 200 * ledger.COMMISSION_BPS / 1e4)
        assert s.get(PaperPosition, "AAA") is None
    snap = ledger.snapshot(loader({"AAA": df}))
    assert snap["positions"] == [] and snap["dividends_received"] == pytest.approx(50)
    assert "paper" in snap["label"] and snap["equity"] == pytest.approx(ledger.get_cash())


# ---- alerts -------------------------------------------------------------------------------------------
def payload(signal, score, flags=(), **kw):
    return {"signal": signal, "score": score, "company": "Test Co", "price": 10.0, "price_date": "2026-11-13", "reasons": ["r"],
            "weaknesses": ["w"], "gates": [], "red_flags": list(flags), "unusual": {}, **kw}


def test_alert_deduplication(tmp_env):
    from app.alerts import engine
    from app.db import Alert, session
    assert engine.emit("signal", "AAA", "t", "m", {"signal": "BUY"}) is not None
    assert engine.emit("signal", "AAA", "t", "m", {"signal": "BUY"}) is None          # unchanged state -> no repeat
    assert engine.emit("signal", "AAA", "t", "m", {"signal": "SELL"}) is not None     # state change -> new alert
    assert engine.emit("signal", "AAA", "t", "m", {"signal": "BUY"}) is not None      # back again is a real change
    assert engine.emit("signal", "BBB", "t", "m", {"signal": "BUY"}) is not None      # other symbol is independent
    with session() as s:
        assert len(s.scalars(select(Alert)).all()) == 4


def test_stock_alerts_only_on_meaningful_change(tmp_env):
    from app.alerts import engine
    assert engine.evaluate_stock("AAA", None, payload("HOLD", 55), first_scan=True) == []
    assert len(engine.evaluate_stock("AAA", None, payload("BUY", 75), first_scan=True)) == 1
    assert engine.evaluate_stock("AAA", payload("BUY", 75), payload("BUY", 76)) == []            # nothing changed
    ids = engine.evaluate_stock("AAA", payload("BUY", 75), payload("HOLD", 58))                  # downgrade + score move
    assert len(ids) == 2
    assert len(engine.evaluate_stock("BBB", payload("HOLD", 50), payload("SELL", 25))) == 2      # SELL + score change
    severe = {"code": "weak_coverage", "severity": "severe", "text": "coverage 1.0x"}
    assert len(engine.evaluate_stock("CCC", payload("BUY", 70), payload("BUY", 70, [severe]))) == 1
    assert engine.evaluate_stock("CCC", payload("BUY", 70, [severe]), payload("BUY", 70, [severe])) == []
    un = payload("BUY", 70, unusual={"volume_ratio": 4.0, "ret_1d": 0.08, "move_sigma": 4.0})
    assert len(engine.evaluate_stock("DDD", payload("BUY", 70), un)) == 2
    assert engine.evaluate_stock("DDD", un, un) == []                                            # same day -> deduplicated
    assert engine.evaluate_stock("EEE", payload("HOLD", 50), payload("HOLD", 50, unusual={"volume_ratio": 9.0})) == []   # not a tracked name


def test_regime_and_provider_alerts(tmp_env):
    from app.alerts import engine
    from app.data.http import record_health
    assert engine.evaluate_regime(None, {"regime": "neutral", "components": []}) is None
    assert engine.evaluate_regime({"regime": "neutral"}, {"regime": "risk_off", "components": []}) is not None
    assert engine.evaluate_regime({"regime": "risk_off"}, {"regime": "risk_off", "components": []}) is None
    for _ in range(3):
        record_health("yahoo", False, "HTTP 429")
    assert len(engine.evaluate_providers()) == 1
    assert engine.evaluate_providers() == []                 # still failing: no repeat
    record_health("yahoo", True)
    assert len(engine.evaluate_providers()) == 1             # recovery notice
    assert engine.evaluate_providers() == []

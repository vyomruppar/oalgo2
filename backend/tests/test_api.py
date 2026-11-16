import pandas as pd
import pytest
from fastapi.testclient import TestClient

from tests.conftest import make_prices


@pytest.fixture()
def client(tmp_env):
    from app.api.main import app
    from app.db import Security, StockResult, session, utcnow
    with session() as s:
        s.add(Security(symbol="AAA", name="Aaa Corp Common Stock", exchange="NYSE", listing_source="nasdaqtrader.com/otherlisted.txt",
                       listing_as_of=utcnow(), security_type="common", eligible=True, sector="Technology"))
        s.add(Security(symbol="ETFX", name="Some ETF", exchange="NASDAQ", listing_source="nasdaqtrader.com/nasdaqlisted.txt",
                       listing_as_of=utcnow(), security_type="excluded", eligible=False, exclusion_reason="exchange-traded fund"))
        s.add(StockResult(symbol="AAA", scan_id=1, as_of=utcnow(), price_date="2026-11-13", price=50.0, screen_pass=True,
                          screen_detail=[{"rule": "min_price", "passed": True, "detail": "ok"}], score=72.0, signal="BUY", data_quality="A",
                          payload={"company": "Aaa Corp", "exchange": "NYSE", "sector": "Technology", "components": [{"component": "value", "component_score": 80.0}],
                                   "risk": {"volatility_1y": 0.3, "adv_dollar_63": 1e8}, "fundamentals": {"market_cap": 1e9}}))
    df = make_prices(300, seed=1, start="2025-09-01")
    from app.data.yahoo import YahooPrices
    df.to_parquet(YahooPrices().path("AAA"))
    with TestClient(app) as c:
        yield c


def test_health_and_overview(client):
    assert client.get("/api/health").json()["status"] == "ok"
    o = client.get("/api/overview").json()
    assert o["universe"]["listed"] == 2 and o["universe"]["eligible_listings"] == 1
    assert o["top"][0]["symbol"] == "AAA" and "real-time" in o["data_freshness"]
    assert {p["key"] for p in o["providers"]} == {"nasdaq_trader", "sec_edgar", "yahoo", "ken_french", "fred"}


def test_stock_endpoints(client):
    r = client.get("/api/stocks", params={"signal": "BUY"}).json()
    assert r["total"] == 1 and r["items"][0]["components"]["value"] == 80.0
    d = client.get("/api/stocks/aaa").json()
    assert d["security"]["exchange"] == "NYSE" and d["result"]["signal"] == "BUY"
    p = client.get("/api/stocks/AAA/prices", params={"range": "3m"}).json()
    assert p["freshness"] == "end_of_day" and len(p["dates"]) == 63 and len(p["indicators"]["rsi_14"]) == 63
    assert "approximation" in p["indicator_notes"]["vwap_20"]
    assert client.get("/api/stocks/ZZZZ").status_code == 404
    assert client.get("/api/stocks/DROP TABLE").status_code == 400
    assert client.get("/api/stocks/AAA/fundamentals").json()["available"] is False


def test_config_validation_and_update(client):
    cfg = client.get("/api/config").json()
    assert cfg["score"]["weights"]["value"] == 20.0
    bad = {"score": {**cfg["score"], "weights": {"value": -1}}, "rescore": False}
    assert client.put("/api/config", json=bad).status_code == 400
    bad2 = {"score": {**cfg["score"], "buy": 90, "strong_buy": 80}, "rescore": False}
    assert client.put("/api/config", json=bad2).status_code == 400
    bad3 = {"score": {**cfg["score"], "weights": {"astrology": 5}}, "rescore": False}
    assert client.put("/api/config", json=bad3).status_code == 400
    ok = {"screen": {**cfg["screen"], "min_price": 10.0}, "rescore": False}
    assert client.put("/api/config", json=ok).status_code == 200
    assert client.get("/api/config").json()["screen"]["min_price"] == 10.0


def test_paper_orders_only_for_verified_listings(client):
    assert client.post("/api/portfolio/orders", json={"symbol": "ETFX", "side": "BUY", "quantity": 1}).status_code == 400
    assert client.post("/api/portfolio/orders", json={"symbol": "NOPE", "side": "BUY", "quantity": 1}).status_code == 400
    assert client.post("/api/portfolio/orders", json={"symbol": "AAA", "side": "BUY", "quantity": -5}).status_code == 422
    assert client.post("/api/portfolio/orders", json={"symbol": "AAA", "side": "SHORT", "quantity": 1}).status_code == 422
    r = client.post("/api/portfolio/orders", json={"symbol": "AAA", "side": "BUY", "quantity": 10})
    assert r.status_code == 201 and r.json()["paper"] is True
    pf = client.get("/api/portfolio").json()
    assert pf["trades"][0]["status"] == "pending" and "paper" in pf["label"]
    assert client.get("/api/portfolio/risk").json()["empty"] is True
    size = client.get("/api/portfolio/size/AAA").json()
    assert 0 < size["weight"] <= 0.10


def test_alert_endpoints(client):
    from app.alerts import engine
    engine.emit("signal", "AAA", "BUY: AAA", "msg", {"signal": "BUY"})
    a = client.get("/api/alerts").json()
    assert a["unread"] == 1 and a["items"][0]["symbol"] == "AAA"
    assert client.post("/api/alerts/read").json()["marked"] == 1
    assert client.get("/api/alerts", params={"unread": True}).json()["items"] == []
    assert client.get("/api/events/recent").json()[-1]["type"] == "alert"


def test_there_is_no_live_trading_surface(client):
    """The platform is research and paper trading only: no route or dependency for real execution."""
    paths = [r.path for r in client.app.routes]
    assert not any(w in p.lower() for p in paths for w in ("broker", "execute", "live", "real"))
    import importlib.metadata as md
    installed = {d.metadata["Name"].lower() for d in md.distributions()}
    assert not installed & {"alpaca-trade-api", "alpaca-py", "ib-insync", "ibapi", "robin-stocks", "ccxt", "tda-api", "schwab-py"}
    assert client.get("/api/strategies").json()["available"] is False      # nothing fabricated before a backtest exists
    assert client.get("/api/ml").json()["status"] == "not_trained"

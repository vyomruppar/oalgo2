from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from tests.conftest import make_prices


def seed_security(*symbols, eligible=True):
    from app.db import Security, session, utcnow
    with session() as s:
        for sym in symbols:
            s.add(Security(symbol=sym, name=f"{sym} Corp Common Stock", exchange="NYSE", listing_source="nasdaqtrader.com/otherlisted.txt",
                           listing_as_of=utcnow(), security_type="common", eligible=eligible, sector="Technology"))


def loader(frames):
    return lambda sym: frames.get(sym)


# ---- holdings -----------------------------------------------------------------------------------------
def test_holding_validation(tmp_env):
    from app.portfolio import holdings as H
    seed_security("AAA")
    assert H.add("aaa", 10, 50.0, "2024-01-10") > 0
    for args, msg in [(("ZZZ", 1, 1.0, "2024-01-10"), "not in the verified"), (("AAA", 0, 1.0, "2024-01-10"), "positive"),
                      (("AAA", 1, -1.0, "2024-01-10"), "zero or more"), (("AAA", 1, 1.0, "10/01/2024"), "YYYY-MM-DD"),
                      (("AAA", 1, 1.0, "2999-01-01"), "future")]:
        with pytest.raises(H.HoldingError, match=msg):
            H.add(*args)
    assert len(H.lots()) == 1


def test_summary_values_positions_and_never_fakes_missing_prices(tmp_env):
    from app.portfolio import holdings as H
    seed_security("AAA", "BBB")
    df = make_prices(100, seed=1, start="2024-01-02")
    H.add("AAA", 10, 40.0, "2024-01-10")
    H.add("AAA", 5, 60.0, "2024-03-01")
    H.add("BBB", 3, 20.0, "2024-02-01")
    s = H.summary(loader({"AAA": df}))
    a = next(p for p in s["positions"] if p["symbol"] == "AAA")
    price = float(df["close"].iloc[-1])
    assert a["shares"] == 15 and a["lots"] == 2 and a["invested"] == pytest.approx(10 * 40 + 5 * 60)
    assert a["avg_cost"] == pytest.approx(700 / 15)
    assert a["value"] == pytest.approx(15 * price) and a["gain"] == pytest.approx(15 * price - 700)
    assert a["day_change"] == pytest.approx(15 * (price - float(df["close"].iloc[-2])))
    b = next(p for p in s["positions"] if p["symbol"] == "BBB")
    assert b["value"] is None and b["price"] is None and s["missing_prices"] == ["BBB"]
    assert s["value"] == pytest.approx(15 * price)                 # unpriced holding is excluded, not counted as zero gain
    assert s["gain"] == pytest.approx(15 * price - 700)
    assert a["weight"] == pytest.approx(1.0) and "no orders" in s["label"].lower()


def test_split_after_purchase_scales_shares_not_value(tmp_env):
    from app.portfolio import holdings as H
    seed_security("AAA")
    df = make_prices(100, seed=2, start="2024-01-02")
    df.loc[df.index[60], "split"] = 4.0            # provider prices are already split-adjusted
    H.add("AAA", 10, 200.0, df.index[10].date().isoformat())      # bought before the split: 10 old shares
    H.add("AAA", 8, 50.0, df.index[80].date().isoformat())        # bought after: 8 new shares
    a = H.summary(loader({"AAA": df}))["positions"][0]
    assert a["shares"] == pytest.approx(10 * 4 + 8)
    assert a["invested"] == pytest.approx(10 * 200 + 8 * 50)


def test_history_tracks_value_invested_dividends_and_benchmark(tmp_env):
    from app.portfolio import holdings as H
    seed_security("AAA", "BBB")
    a, b = make_prices(120, seed=3, start="2024-01-02"), make_prices(120, seed=4, start="2024-01-02")
    a.loc[a.index[50], "dividend"] = 0.5
    spy = make_prices(120, seed=5, start="2024-01-02")["adj_close"]
    d1, d2 = a.index[20], a.index[70]
    H.add("AAA", 10, float(a["close"].loc[d1]), d1.date().isoformat())
    H.add("BBB", 4, float(b["close"].loc[d2]), d2.date().isoformat())
    h = H.history(loader({"AAA": a, "BBB": b}), spy)
    rows = {r[0]: r for r in h["series"]}
    assert h["start"] == d1.date().isoformat() and min(rows) == d1.date().isoformat()        # nothing before the first purchase
    first = rows[d1.date().isoformat()]
    assert first[1] == pytest.approx(first[2], abs=0.01) and first[4] == pytest.approx(first[2], abs=0.01)   # bought at cost
    mid = rows[a.index[60].date().isoformat()]
    assert mid[1] == pytest.approx(10 * a["close"].iloc[60], abs=0.01) and mid[2] == pytest.approx(10 * a["close"].loc[d1], abs=0.01)
    assert mid[3] == pytest.approx(5.0)                                                       # 10 shares x 0.50 dividend
    assert rows[a.index[40].date().isoformat()][3] == 0.0
    last = rows[a.index[-1].date().isoformat()]
    inv = 10 * a["close"].loc[d1] + 4 * b["close"].loc[d2]
    assert last[1] == pytest.approx(10 * a["close"].iloc[-1] + 4 * b["close"].iloc[-1], abs=0.01) and last[2] == pytest.approx(inv, abs=0.01)
    bench = 10 * a["close"].loc[d1] * spy.iloc[-1] / spy.loc[d1] + 4 * b["close"].loc[d2] * spy.iloc[-1] / spy.loc[d2]
    assert last[4] == pytest.approx(bench, abs=0.01)
    assert h["total_return_pct"] == pytest.approx((last[1] + 5.0) / inv - 1, abs=1e-5)   # series values are rounded to cents
    assert len(H.history(loader({"AAA": a, "BBB": b}), spy, "1m")["series"]) == 21
    assert H.history(loader({}), spy)["empty"] is True


def test_csv_import_is_all_or_nothing(tmp_env):
    from app.portfolio import holdings as H
    seed_security("AAA", "BBB")
    bad = "symbol,shares,cost,date\nAAA,10,50,2024-01-10\nNOPE,1,1,2024-01-10\nBBB,x,1,2024-01-10\n"
    out = H.import_csv(bad)
    assert out["imported"] == 0 and len(out["errors"]) == 2 and "line 3" in out["errors"][0] and H.lots() == []
    ok = H.import_csv("AAA,10,$1,250.50,2024-01-10\n")          # a comma inside the price shifts columns -> rejected, not guessed
    assert ok["imported"] == 0
    good = H.import_csv("ticker,shares,cost,date,note\nAAA,10,50.5,2024-01-10,first lot\nbbb,2.5,20,2024-02-01\n")
    assert good == {"imported": 2, "errors": []}
    assert [(x["symbol"], x["shares"], x["note"]) for x in H.lots()] == [("AAA", 10.0, "first lot"), ("BBB", 2.5, None)]


def test_update_and_delete(tmp_env):
    from app.portfolio import holdings as H
    seed_security("AAA")
    hid = H.add("AAA", 10, 50.0, "2024-01-10")
    H.update(hid, 12, 48.0, "2024-01-11", "edited")
    assert H.lots()[0]["shares"] == 12 and H.lots()[0]["note"] == "edited" and H.average_costs() == {"AAA": 48.0}
    with pytest.raises(H.HoldingError):
        H.update(999, 1, 1, "2024-01-10")
    assert H.delete(hid) is True and H.delete(hid) is False and H.symbols() == []


# ---- news and sentiment -------------------------------------------------------------------------------
def test_parse_news_fixture(fixtures):
    from app.data.news import parse_search
    items = parse_search((fixtures / "yahoo_news_mu.json").read_bytes(), "MU", "Micron Technology, Inc. - Common Stock")
    assert len(items) >= 3
    for it in items:
        assert it["uuid"] and it["title"] and it["published_at"].tzinfo is not None and 0 < it["relevance"] <= 1
        assert it["link"] is None or it["link"].startswith("https://")


def test_relevance_distinguishes_company_news_from_roundups():
    from app.data.news import name_tokens, relevance
    assert name_tokens("Micron Technology, Inc. - Common Stock") == ["micron", "technology"]
    assert relevance("Micron beats estimates", "MU", "Micron Technology, Inc.", ["MU"]) == 1.0
    assert relevance("Why MU stock jumped today", "MU", "Micron Technology, Inc.", ["MU", "NVDA"]) == 1.0
    wide = relevance("Hedge fund reshuffles its tech bets", "MU", "Micron Technology, Inc.", ["A", "B", "C", "D", "E", "F", "G", "MU"])
    assert 0.15 <= wide < 0.3


def test_lexicon_engine():
    from app.research.sentiment import LexiconEngine
    r = LexiconEngine().score(["Shares surge after company beats estimates", "Stock plunges on fraud probe", "Annual meeting set for May",
                               "Company did not miss estimates"])
    assert r[0][1] == "positive" and r[0][0] > 0.5
    assert r[1][1] == "negative" and r[1][0] < -0.5
    assert r[2] == (0.0, "neutral")
    assert r[3][0] > 0                                   # negation flips "miss"


def test_engine_selection_and_status(tmp_env):
    from app.research import sentiment as S
    assert S.get_engine().name == "lexicon"
    st = S.engine_status()
    assert st["is_ai"] is False and "not AI" in st["description"] and "not forecasts" in st["caveat"]


def test_aggregate_weights_recency_and_relevance():
    from app.research.sentiment import aggregate
    now = datetime(2026, 11, 17, tzinfo=timezone.utc)
    fresh_neg = {"sentiment": -0.9, "sentiment_label": "negative", "relevance": 1.0, "published_at": now - timedelta(hours=2)}
    old_pos = {"sentiment": 0.9, "sentiment_label": "positive", "relevance": 1.0, "published_at": now - timedelta(days=9)}
    a = aggregate([fresh_neg, old_pos], now)
    assert a["n"] == 2 and a["score"] < -0.6 and a["label"] == "negative" and a["counts"] == {"positive": 1, "neutral": 0, "negative": 1}
    weak = {**fresh_neg, "relevance": 0.15}
    strong_pos = {**old_pos, "published_at": now - timedelta(hours=2)}
    assert aggregate([weak, strong_pos], now)["score"] > 0.5        # a round-up mention counts for little
    assert aggregate([], now) == {"score": None, "label": None, "n": 0, "counts": {"positive": 0, "neutral": 0, "negative": 0}}


def test_news_service_stores_once_and_dedupes_across_symbols(tmp_env, fixtures, monkeypatch):
    from app.data import news as N
    from app.research import news_service as NS
    raw = (fixtures / "yahoo_news_mu.json").read_bytes()
    monkeypatch.setattr(N.YahooNews, "fetch", lambda self, sym, company=None, count=12, ttl_seconds=0: N.parse_search(raw, sym, company))
    first = NS.refresh({"MU": "Micron Technology", "NVDA": "NVIDIA Corporation"})
    assert first["new"] > 0 and NS.refresh({"MU": "Micron Technology", "NVDA": "NVIDIA Corporation"})["new"] == 0
    items = NS.items_for(["MU", "NVDA"])
    assert all(i["sentiment"] is not None and i["engine"] == "lexicon" for i in items)
    pub = NS.public(items)
    assert len(pub) == len(items) // 2 and sorted(pub[0]["symbols"]) == ["MU", "NVDA"]     # one story, tagged with both
    assert set(NS.sentiment_by_symbol(["MU"])) == {"MU"}


def test_sentiment_alert_only_starts_on_negative_and_reports_recovery(tmp_env):
    from app.alerts import engine
    neg = {"score": -0.6, "n": 4, "counts": {"positive": 0, "neutral": 1, "negative": 3}}
    pos = {"score": 0.5, "n": 4, "counts": {"positive": 3, "neutral": 1, "negative": 0}}
    assert engine.evaluate_sentiment("AAA", pos) is None                       # good news alone is not an alert
    assert engine.evaluate_sentiment("AAA", {**neg, "n": 2}) is None           # too few headlines
    assert engine.evaluate_sentiment("AAA", neg) is not None
    assert engine.evaluate_sentiment("AAA", neg) is None                       # unchanged -> no repeat
    assert engine.evaluate_sentiment("AAA", pos) is not None                   # tone recovered


# ---- API ----------------------------------------------------------------------------------------------
@pytest.fixture()
def client(tmp_env):
    from app.api.main import app
    from app.data.yahoo import YahooPrices
    seed_security("AAA", "BBB")
    y = YahooPrices()
    for i, sym in enumerate(["AAA", "BBB", "SPY"]):
        make_prices(300, seed=i, start="2025-09-01").to_parquet(y.path(sym))
    with TestClient(app) as c:
        yield c


def test_holdings_api_flow(client):
    assert client.get("/api/holdings").json()["positions"] == []
    assert client.post("/api/holdings", json={"symbol": "NOPE", "shares": 1, "cost": 1, "purchase_date": "2025-10-01"}).status_code == 400
    assert client.post("/api/holdings", json={"symbol": "AAA", "shares": -1, "cost": 1, "purchase_date": "2025-10-01"}).status_code == 422
    r = client.post("/api/holdings", json={"symbol": "AAA", "shares": 10, "cost": 50, "purchase_date": "2025-10-01"})
    assert r.status_code == 201
    hid = r.json()["id"]
    assert client.post("/api/holdings/import", json={"csv": "BBB,5,20,2025-11-03"}).json()["imported"] == 1
    assert client.post("/api/holdings/import", json={"csv": "BBB,5"}).status_code == 400
    h = client.get("/api/holdings").json()
    assert {p["symbol"] for p in h["positions"]} == {"AAA", "BBB"} and h["value"] > 0 and len(h["positions"][0]["spark"]) == 60
    hist = client.get("/api/holdings/history", params={"range": "3m"}).json()
    assert hist["empty"] is False and hist["columns"][1] == "value" and len(hist["series"]) == 63
    rk = client.get("/api/holdings/risk").json()
    assert rk["empty"] is False and rk["n_positions"] == 2 and rk["cash"] == 0
    assert client.put(f"/api/holdings/{hid}", json={"shares": 20, "cost": 50, "purchase_date": "2025-10-01"}).status_code == 200
    assert client.delete(f"/api/holdings/{hid}").status_code == 200 and client.delete(f"/api/holdings/{hid}").status_code == 404
    from app.db import PaperTrade, session
    with session() as s:
        assert s.query(PaperTrade).count() == 0                  # recording holdings never creates an order of any kind


def test_dashboard_news_and_lab_endpoints(client):
    client.post("/api/holdings", json={"symbol": "AAA", "shares": 10, "cost": 50, "purchase_date": "2025-10-01"})
    d = client.get("/api/dashboard").json()
    assert d["holdings"]["n_positions"] == 1 and d["stars"] == [] and d["engine"]["engine"] == "lexicon"
    n = client.get("/api/news").json()
    assert n["items"] == [] and "headlines only" in n["source"]
    assert client.get("/api/news", params={"symbol": "bad symbol"}).status_code == 400
    assert client.get("/api/lab/mean-reversion").json()["items"] == []
    assert client.get("/api/lab/regime-history").json()["available"] is False

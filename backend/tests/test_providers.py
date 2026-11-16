import json
from datetime import datetime, timezone

import pandas as pd
import pytest

from app.data.fred import parse_fred_csv
from app.data.french import parse_french_csv
from app.data.sec import norm_ticker, parse_submissions, parse_tickers_exchange, sic_to_sector
from app.data.validate import validate_prices
from app.data.yahoo import parse_chart, parse_spark
from tests.conftest import make_prices

AFTER_CLOSE = datetime(2026, 11, 20, 23, 0, tzinfo=timezone.utc)


def test_parse_chart_fixture(fixtures):
    raw = (fixtures / "yahoo_chart_aapl.json").read_bytes()
    df, meta = parse_chart(raw, now=AFTER_CLOSE)
    assert meta["symbol"] == "AAPL"
    assert list(df.columns) == ["open", "high", "low", "close", "adj_close", "volume", "dividend", "split"]
    assert df.index.is_monotonic_increasing and df.index.is_unique
    assert (df[["open", "high", "low", "close"]] > 0).all().all()
    assert (df["high"] >= df["low"]).all()
    assert df.index[-1] == pd.Timestamp("2026-11-13")
    assert df.loc["2026-11-12", "dividend"] == pytest.approx(0.27)
    assert (df["adj_close"] <= df["close"] + 1e-9).all()       # dividend adjustment only lowers past prices


def test_parse_chart_drops_bar_of_open_session(fixtures):
    d = json.loads((fixtures / "yahoo_chart_aapl.json").read_text())
    r = d["chart"]["result"][0]
    last = r["timestamp"][-1]
    r["timestamp"].append(last + 3 * 86400)                       # Monday 2026-11-16, session in progress
    for k in r["indicators"]["quote"][0]:
        r["indicators"]["quote"][0][k].append(r["indicators"]["quote"][0][k][-1])
    r["indicators"]["adjclose"][0]["adjclose"].append(r["indicators"]["adjclose"][0]["adjclose"][-1])
    regular_end = int(datetime(2026, 11, 16, 21, 0, tzinfo=timezone.utc).timestamp())
    r["meta"]["currentTradingPeriod"]["regular"]["end"] = regular_end
    raw = json.dumps(d).encode()
    during, _ = parse_chart(raw, now=datetime(2026, 11, 16, 15, 0, tzinfo=timezone.utc))
    assert during.index[-1] == pd.Timestamp("2026-11-13")         # in-progress bar is not stored
    after, _ = parse_chart(raw, now=datetime(2026, 11, 16, 21, 30, tzinfo=timezone.utc))
    assert after.index[-1] == pd.Timestamp("2026-11-16")          # completed session is kept


def test_parse_chart_drops_null_rows_instead_of_filling():
    raw = json.dumps({"chart": {"error": None, "result": [{"meta": {}, "timestamp": [1700000000, 1700086400, 1700172800],
           "indicators": {"quote": [{"open": [1.0, None, 3.0], "high": [1.1, None, 3.1], "low": [0.9, None, 2.9], "close": [1.0, None, 3.0],
                                     "volume": [10, None, 30]}], "adjclose": [{"adjclose": [1.0, None, 3.0]}]}}]}}).encode()
    df, _ = parse_chart(raw, now=AFTER_CLOSE)
    assert len(df) == 2 and df["close"].tolist() == [1.0, 3.0]


def test_parse_spark(fixtures):
    out = parse_spark((fixtures / "yahoo_spark.json").read_bytes())
    assert out["XOM"]["price"] > 0 and out["XOM"]["avg_dollar_volume"] > 1e8
    assert len(out) == 20


def test_sec_parsers(fixtures):
    prof = parse_submissions((fixtures / "sec_submissions_aapl.json").read_bytes())
    assert prof.cik == "0000320193" and prof.sic == "3571" and "AAPL" in prof.tickers
    assert prof.filings[0]["url"].startswith("https://www.sec.gov/Archives/edgar/data/320193/")
    assert sic_to_sector("3571") == "Technology" and sic_to_sector("6021") == "Financials"
    assert sic_to_sector("2834") == "Health Care" and sic_to_sector(None) == "Unknown"
    m = parse_tickers_exchange(json.dumps({"fields": ["cik", "name", "ticker", "exchange"],
                                           "data": [[320193, "Apple Inc.", "AAPL", "Nasdaq"], [1067983, "Berkshire", "BRK-B", "NYSE"]]}).encode())
    assert m == {"AAPL": "0000320193", "BRK-B": "0001067983"}
    assert norm_ticker("brk.b") == "BRK-B"


def test_french_and_fred_parsers(fixtures):
    ff = parse_french_csv((fixtures / "french_ff3_daily.csv").read_text())
    assert list(ff.columns) == ["Mkt-RF", "SMB", "HML", "RF"]
    assert ff.loc["1926-07-01", "Mkt-RF"] == pytest.approx(0.0009)   # percent converted to decimal
    assert ff.index[-1] == pd.Timestamp("2026-09-30")
    s = parse_fred_csv((fixtures / "fred_dgs10.csv").read_text())
    assert s.index.is_monotonic_increasing and s.notna().all() and 0 < s.iloc[-1] < 20


def test_validate_prices_flags_problems():
    df = make_prices(300, seed=1, start="2025-09-01")
    now = datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)
    assert validate_prices(df, now=datetime.combine(df.index[-1].date(), datetime.min.time(), timezone.utc).replace(hour=23)) == []
    codes = {i["code"] for i in validate_prices(df, now=now.replace(year=2027))}
    assert "stale" in codes
    bad = df.copy()
    bad.iloc[100, bad.columns.get_loc("adj_close")] *= 3.0
    assert "extreme_move" in {i["code"] for i in validate_prices(bad, now=now)}
    assert validate_prices(df.iloc[0:0])[0]["code"] == "empty"

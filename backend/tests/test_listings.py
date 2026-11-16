from app.data.nasdaq_trader import classify, parse_nasdaq_listed, parse_other_listed


def test_classification_rules():
    assert classify("AAPL", "Apple Inc. - Common Stock", False, False, "N") == ("common", True, None)
    assert classify("TQQQ", "ProShares UltraPro QQQ", True, False, "N")[1] is False
    assert classify("ZAZZT", "Tick Pilot Test Stock", False, True, "N")[2] == "test issue"
    assert classify("ABCDW", "Abc Corp - Warrant", False, False, "N")[1] is False
    assert classify("ABCU", "Abc Corp - Units", False, False, "N")[1] is False
    assert classify("ABCR", "Abc Corp - Rights", False, False, "N")[1] is False
    assert classify("ABC$D", "Abc 6% Preferred Series D", False, False)[1] is False
    assert classify("EAI", "Entergy Arkansas, LLC First Mortgage Bonds, 4.875% Series Due September 1, 2066", False, False)[1] is False
    assert classify("FWAC", "Futurewave Acquisition Corporation - Ordinary Shares", False, False, "N")[1] is False
    assert classify("XYZ", "Xyz Inc - Common Stock", False, False, "D")[1] is False       # Nasdaq deficiency flag
    assert classify("BABA", "Alibaba Group Holding Limited American Depositary Shares", False, False) == ("adr", True, None)
    assert classify("BRK.B", "Berkshire Hathaway Inc. Common Stock", False, False)[1] is True


def test_parse_nasdaq_listed_fixture(fixtures):
    rows = parse_nasdaq_listed((fixtures / "nasdaqlisted_sample.txt").read_text())
    by = {r.symbol: r for r in rows}
    assert by["AAPL"].eligible and by["AAPL"].exchange == "NASDAQ"
    assert not by["TQQQ"].eligible and by["TQQQ"].exclusion_reason == "exchange-traded fund"
    assert not by["ZAZZT"].eligible
    assert all(r.exchange == "NASDAQ" and r.source.endswith("nasdaqlisted.txt") for r in rows)
    assert all(r.eligible or r.exclusion_reason for r in rows)          # every exclusion carries a reason
    assert by["AAPL"].as_of.tzinfo is not None


def test_parse_other_listed_keeps_only_nyse(fixtures):
    text = (fixtures / "otherlisted_sample.txt").read_text()
    rows = parse_other_listed(text)
    by = {r.symbol: r for r in rows}
    assert by["KO"].eligible and by["KO"].exchange == "NYSE"
    assert by["BRK.B"].eligible
    assert "SPY" not in by and "GLD" not in by       # NYSE Arca listings are out of scope entirely
    assert "AAA" not in by
    assert not by["ABR$D"].eligible                  # preferred share class
    assert not by["EAI"].eligible                    # exchange-listed bond
    assert {r.exchange for r in rows} == {"NYSE"}
    venues = {ln.split("|")[2] for ln in text.splitlines()[1:-1]}
    assert venues - {"N"}, "fixture must contain non-NYSE venues for this test to be meaningful"

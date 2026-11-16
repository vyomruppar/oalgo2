import numpy as np
import pandas as pd
import pytest

from app.research.scoring import ScoreConfig, contributions, score_universe, technical_component
from app.research.signals import build_payload, classify, estimate_next_report, ordinal, red_flags
from app.universe.screener import ScreenConfig, eligibility_mask, passes, screen_row

GOOD = {"price": 50.0, "market_cap": 5e9, "adv_dollar_63": 4e7, "n_bars": 900, "vol_252": 0.3, "assets": 1e9, "net_income_ttm": 1e8,
        "sector": "Technology"}


def test_screen_records_every_rule_with_reason():
    d = screen_row(pd.Series(GOOD), ScreenConfig(), [], 1)
    assert passes(d) and {r["rule"] for r in d} >= {"min_price", "min_market_cap", "min_adv_dollar", "min_history", "max_volatility",
                                                    "fundamentals_available", "sector", "price_data_quality", "fresh_prices"}
    assert all(r["detail"] for r in d)


@pytest.mark.parametrize("change,rule", [({"price": 2.0}, "min_price"), ({"market_cap": 1e8}, "min_market_cap"),
                                         ({"adv_dollar_63": 1e5}, "min_adv_dollar"), ({"n_bars": 100}, "min_history"),
                                         ({"vol_252": 1.5}, "max_volatility"), ({"assets": np.nan}, "fundamentals_available"),
                                         ({"market_cap": np.nan}, "min_market_cap")])
def test_screen_failures(change, rule):
    d = screen_row(pd.Series({**GOOD, **change}), ScreenConfig(), [], 1)
    failed = [r["rule"] for r in d if not r["passed"]]
    assert failed == [rule]


def test_screen_config_is_respected_and_missing_data_fails_closed():
    row = pd.Series({**GOOD, "price": 3.0})
    assert passes(screen_row(row, ScreenConfig(min_price=2.0), [], 1))
    assert not passes(screen_row(pd.Series(GOOD), ScreenConfig(excluded_sectors=["Technology"]), [], 1))
    assert not passes(screen_row(pd.Series(GOOD), ScreenConfig(), [], 9))                      # stale prices
    assert not passes(screen_row(pd.Series(GOOD), ScreenConfig(), [{"code": "non_finite", "severity": "error", "detail": "x"}], 1))
    assert not passes(screen_row(pd.Series({**GOOD, "share_count_unreliable": True}), ScreenConfig(), [], 1))


def test_eligibility_mask_matches_row_screen():
    df = pd.DataFrame([GOOD, {**GOOD, "price": 1.0}, {**GOOD, "assets": np.nan}])
    assert eligibility_mask(df, ScreenConfig()).tolist() == [True, False, False]


def universe(n=40, seed=0):
    rng = np.random.default_rng(seed)
    cols = ["earnings_yield", "ebit_ev", "book_to_market", "fcf_yield", "mom_12_1", "mom_6_1", "gross_profitability", "roic", "accruals",
            "piotroski", "asset_growth", "vol_252", "sue", "revenue_growth_q", "log_mcap", "ret_1m", "interest_coverage",
            "net_debt_to_ebitda", "current_ratio"]
    df = pd.DataFrame(rng.normal(size=(n, len(cols))), columns=cols, index=[f"S{i}" for i in range(n)])
    df["vol_252"] = df["vol_252"].abs() * 0.2 + 0.1
    df["sector"] = ["Technology", "Financials", "Energy", "Health Care"] * (n // 4)
    df["price"], df["sma_50"], df["sma_200"] = 100.0, 95.0, 90.0
    df["macd_hist"], df["rsi_14"], df["dist_52w_high"] = 0.5, 55.0, -0.05
    return df


def test_score_is_bounded_and_weights_renormalise_when_data_missing():
    u = universe()
    cfg = ScoreConfig()
    out = score_universe(u, cfg, "neutral")
    assert out["score"].between(0, 100).all()
    assert (out["data_quality"] == "A").all()
    u2 = u.copy()
    u2.loc["S0", ["earnings_yield", "ebit_ev", "book_to_market", "fcf_yield"]] = np.nan
    out2 = score_universe(u2, cfg, "neutral")
    w = cfg.weights
    assert out2.loc["S0", "coverage"] == pytest.approx(1 - w["value"] / sum(v for v in w.values() if v > 0))
    comps = [k for k in w if w[k] > 0 and k != "value"]
    expected = sum(w[k] * out2.loc["S0", k] for k in comps) / sum(w[k] for k in comps)
    assert out2.loc["S0", "score"] == pytest.approx(expected)
    c = {x["component"]: x for x in contributions(out2.loc["S0"], cfg)}
    assert c["value"]["contribution"] is None and "missing" in c["value"]["status"]
    assert sum(x["contribution"] for x in c.values() if x["contribution"] is not None) == pytest.approx(out2.loc["S0", "score"])


def test_changing_weights_changes_ranking_input():
    u = universe()
    only_value = ScoreConfig(weights={"value": 100.0})
    out = score_universe(u, only_value, "neutral")
    assert out["score"].equals(out["value"])
    assert score_universe(u, ScoreConfig(), "risk_off")["score"].mean() < score_universe(u, ScoreConfig(), "risk_on")["score"].mean()


def test_technical_component():
    s, checks = technical_component(pd.Series({"price": 100.0, "sma_50": 95.0, "sma_200": 90.0, "macd_hist": 1.0, "rsi_14": 60.0, "dist_52w_high": -0.02}))
    assert s == 100.0 and len(checks) == 6
    s2, _ = technical_component(pd.Series({"price": 80.0, "sma_50": 95.0, "sma_200": 90.0, "macd_hist": -1.0, "rsi_14": 30.0, "dist_52w_high": -0.4}))
    assert s2 == pytest.approx(100 / 6)     # only "50-day above 200-day" holds
    s3, c3 = technical_component(pd.Series({"price": 80.0}))
    assert np.isnan(s3) and all(c["passed"] is None for c in c3)


def row(score, dq="A", price=100.0, sma200=90.0, **kw):
    return pd.Series({"score": score, "data_quality": dq, "price": price, "sma_200": sma200, **kw})


def test_signal_classification_and_gates():
    cfg = ScoreConfig()
    assert classify(row(85), cfg, "risk_on", [])[0] == "STRONG BUY"
    sig, gates = classify(row(85), cfg, "neutral", [])
    assert sig == "BUY" and "STRONG BUY withheld" in gates[0]
    assert classify(row(72), cfg, "risk_on", [])[0] == "BUY"
    sig, gates = classify(row(72, price=80.0), cfg, "risk_on", [])
    assert sig == "WATCHLIST" and "200-day" in gates[0]
    assert classify(row(72), cfg, "risk_off", [])[0] == "WATCHLIST"
    assert classify(row(72, dq="C"), cfg, "risk_on", [])[0] == "WATCHLIST"
    severe = [{"code": "x", "severity": "severe", "text": "distress"}]
    assert classify(row(72), cfg, "risk_on", severe)[0] == "WATCHLIST"
    assert classify(row(40), cfg, "risk_on", severe)[0] == "SELL"
    assert classify(row(25), cfg, "risk_on", [])[0] == "SELL"
    assert classify(row(55), cfg, "risk_on", [])[0] == "HOLD"


def test_no_action_when_evidence_is_insufficient():
    cfg = ScoreConfig()
    assert classify(row(90, dq="D"), cfg, "risk_on", [])[0] == "NO_ACTION"
    assert classify(row(np.nan), cfg, "risk_on", [])[0] == "NO_ACTION"


def test_red_flags():
    flags = red_flags(pd.Series({"altman_z": 1.2, "piotroski": 2, "piotroski_n": 8, "accruals": 0.2, "interest_coverage": 1.0,
                                 "net_debt_to_ebitda": 7, "sector": "Industrials", "vol_252": 0.9}))
    codes = {f["code"] for f in flags}
    assert codes >= {"altman_distress", "piotroski_weak", "high_accruals", "weak_coverage", "high_leverage", "high_volatility"}
    assert red_flags(pd.Series({"altman_z": 4.0, "piotroski": 7, "piotroski_n": 8})) == []
    assert red_flags(pd.Series({"net_debt_to_ebitda": 9, "sector": "Financials"})) == []      # leverage is structural for banks


def test_payload_contains_every_required_field():
    u = universe()
    cfg = ScoreConfig()
    scored = score_universe(u, cfg, "neutral")
    r = pd.concat([u.loc["S1"], scored.loc["S1"]])
    r["max_dd_252"], r["vol_63"], r["adv_dollar_63"] = -0.2, 0.25, 5e7
    sec = {"name": "Test Co", "exchange": "NYSE", "listing_source": "nasdaqtrader.com/otherlisted.txt", "listing_as_of": "2026-11-13"}
    p = build_payload("S1", sec, r, cfg, {"regime": "neutral"}, [], "BUY", [], 2.0, {"label": "backtested"}, None, "2026-11-13",
                      [{"name": "x", "as_of": "2026-11-13"}])
    for k in ["company", "symbol", "exchange", "price", "price_date", "score", "components", "entry_conditions", "exit_conditions",
              "holding_period", "strategy_performance", "risk", "scenarios", "upcoming_events", "reasons", "invalidation", "sources", "signal"]:
        assert k in p, k
    assert p["exchange"] == "NYSE" and p["risk"]["stop_reference"] == pytest.approx(100 - 5.0)
    assert "not a probability" in p["score_note"].lower() and "not a forecast" in p["scenarios"]["basis"]
    assert p["scenarios"]["one_sigma_down"] < 100 < p["scenarios"]["one_sigma_up"]
    assert p["entry_conditions"] and p["exit_conditions"] and p["invalidation"]


def test_next_report_estimate_is_labelled_unconfirmed():
    fl = [{"form": "10-Q", "filing_date": d} for d in ["2025-05-01", "2025-08-01", "2025-10-31", "2026-01-30", "2026-05-01", "2026-07-31"]]
    e = estimate_next_report(fl, "2026-10-01")
    assert e["confirmed"] is False and e["date"] == "2026-10-30" and "estimated" in e["type"]
    assert estimate_next_report(fl[:2], "2026-10-01") is None


def test_ordinal():
    assert [ordinal(x) for x in (1, 2, 3, 4, 11, 12, 13, 21, 22, 96, 100)] == ["1st", "2nd", "3rd", "4th", "11th", "12th", "13th", "21st", "22nd", "96th", "100th"]

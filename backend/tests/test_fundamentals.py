import json
from datetime import date

import numpy as np
import pandas as pd
import pytest

from app.research import fundamentals as F


def fact(start, end, val, filed, form="10-Q"):
    return {"start": start, "end": end, "val": val, "filed": filed, "form": form}


def inst(end, val, filed, form="10-Q"):
    return {"end": end, "val": val, "filed": filed, "form": form}


def make_facts():
    ni = [
        fact("2022-01-01", "2022-12-31", 400, "2023-02-15", "10-K"),
        fact("2022-01-01", "2022-03-31", 80, "2022-05-01"),
        fact("2023-01-01", "2023-03-31", 120, "2023-05-01"),
        fact("2022-01-01", "2022-06-30", 180, "2022-08-01"),
        fact("2023-01-01", "2023-06-30", 260, "2023-08-01"),
        fact("2022-01-01", "2022-03-31", 80, "2023-05-01"),      # comparative re-reported in the next year's 10-Q
        fact("2022-01-01", "2022-06-30", 180, "2023-08-01"),
    ]
    assets = [inst("2022-12-31", 1000, "2023-02-15", "10-K"), inst("2023-03-31", 1100, "2023-05-01"), inst("2021-12-31", 900, "2023-02-15", "10-K")]
    return {"facts": {"us-gaap": {"NetIncomeLoss": {"units": {"USD": ni}}, "Assets": {"units": {"USD": assets}}}, "dei": {}}}


def test_ttm_is_fiscal_year_plus_ytd_minus_prior_ytd():
    snap = F.build_snapshots(make_facts())
    assert snap.loc["2023-02-15", "net_income_ttm"] == 400
    assert snap.loc["2023-02-15", "ttm_basis"] == "fiscal_year"
    assert snap.loc["2023-05-01", "net_income_ttm"] == 400 + 120 - 80
    assert snap.loc["2023-08-01", "net_income_ttm"] == 400 + 260 - 180
    assert snap.loc["2023-08-01", "ttm_basis"] == "ttm"
    assert snap.loc["2023-05-01", "assets"] == 1100
    assert snap.loc["2023-02-15", "asset_growth"] == pytest.approx(1000 / 900 - 1)


def test_point_in_time_restatement_only_visible_after_it_is_filed():
    f = make_facts()
    f["facts"]["us-gaap"]["NetIncomeLoss"]["units"]["USD"].append(fact("2022-01-01", "2022-12-31", 350, "2023-08-01", "10-K/A"))
    snap = F.build_snapshots(f)
    assert snap.loc["2023-05-01", "net_income_fy"] == 400          # original value, as known in May
    assert snap.loc["2023-08-01", "net_income_fy"] == 350          # restated value, known from August


def test_known_never_uses_future_filings():
    recs = F.extract_field(make_facts(), "net_income")
    known = F._known(recs, date(2023, 4, 30))
    assert (date(2023, 1, 1), date(2023, 3, 31)) not in known
    assert known[(date(2022, 1, 1), date(2022, 12, 31))] == 400


def test_q4_is_derived_from_fiscal_year_minus_nine_months():
    known = {(date(2022, 1, 1), date(2022, 12, 31)): 400.0, (date(2022, 1, 1), date(2022, 9, 30)): 290.0,
             (date(2022, 7, 1), date(2022, 9, 30)): 110.0}
    fv = F.flow_values(known)
    assert fv["q"] == 110.0 and fv["q_end"] == date(2022, 12, 31)


def test_sue_seasonal_random_walk():
    q = {}
    vals = [10, 12, 11, 13, 12, 13, 13, 16, 13, 15, 16, 17, 18, 16, 15, 30]
    ends = pd.date_range("2020-03-31", periods=16, freq="QE")
    for e, v in zip(ends, vals):
        q[((e - pd.Timedelta(days=89)).date(), e.date())] = float(v)
    diffs = [vals[i] - vals[i - 4] for i in range(4, 16)]
    expected = diffs[-1] / np.std(diffs[-9:-1], ddof=1)
    assert F.sue_from_quarters(q) == pytest.approx(expected)
    assert np.isnan(F.sue_from_quarters({k: v for k, v in list(q.items())[:6]}))


def test_concept_priority_merges_tag_changes():
    f = {"facts": {"us-gaap": {
        "Revenues": {"units": {"USD": [fact("2022-01-01", "2022-12-31", 1000, "2023-02-01", "10-K")]}},
        "SalesRevenueNet": {"units": {"USD": [fact("2021-01-01", "2021-12-31", 900, "2022-02-01", "10-K"),
                                              fact("2022-01-01", "2022-12-31", 999, "2023-02-01", "10-K")]}}}}}
    recs = F.extract_field(f, "revenue")
    by = {(r.end, r.filed): r.val for r in recs}
    assert by[(date(2022, 12, 31), date(2023, 2, 1))] == 1000     # higher-priority concept wins
    assert by[(date(2021, 12, 31), date(2022, 2, 1))] == 900      # older tag still contributes history


def test_real_apple_filing_values(fixtures):
    snap = F.build_snapshots(json.loads((fixtures / "sec_facts_aapl.json").read_text()))
    row = snap.loc["2026-11-03"]                                   # FY2026 10-K
    assert row["net_income_fy"] == 132_175_000_000
    assert row["ttm_basis"] == "fiscal_year" and row["net_income_ttm"] == row["net_income_fy"]
    q3 = snap.loc["2026-07-31"]
    assert q3["net_income_q"] == 29_789_000_000 and q3["ttm_basis"] == "ttm"
    assert q3["shares_diluted"] > 1e10                             # a share count, never a derived difference
    assert 0.4 < row["gross_margin"] < 0.55
    assert row["fcf_ttm"] == row["ocf_ttm"] - row["capex_ttm"]
    assert snap.index.is_monotonic_increasing


def test_piotroski_reports_denominator_and_bounds():
    snap = F.build_snapshots(make_facts())
    assert (snap["piotroski_n"] <= 8).all()                        # dilution signal is not evaluated in this stage
    ok = snap["piotroski"].dropna()
    assert ((ok >= 0) & (ok <= snap.loc[ok.index, "piotroski_n"])).all()


def test_altman_z_formula():
    row = pd.Series({"current_assets": 500.0, "current_liabilities": 200.0, "retained_earnings": 300.0, "operating_income_ttm": 150.0,
                     "revenue_ttm": 1200.0, "assets": 1000.0, "liabilities": 400.0})
    expected = 1.2 * 0.3 + 1.4 * 0.3 + 3.3 * 0.15 + 0.6 * (800 / 400) + 1.0 * 1.2
    assert F.altman_z(row, 800.0) == pytest.approx(expected)
    assert np.isnan(F.altman_z(row.drop("retained_earnings"), 800.0))

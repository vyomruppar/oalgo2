"""Point-in-time fundamentals from SEC XBRL company facts (us-gaap taxonomy).

For every 10-K/10-Q filing date we build one snapshot of what was publicly known on that date:
trailing-twelve-month (TTM) flows, latest fiscal-year and prior-fiscal-year values, and latest balances.
Research code selects the last snapshot filed strictly BEFORE the analysis date, which prevents
look-ahead bias (restated values enter only on the date the restatement was filed).

TTM flow = latest fiscal-year value + current year-to-date - same year-to-date one year earlier.
If the year-to-date comparison is unavailable the fiscal-year value is used and `ttm_basis` says so.

Limitations: IFRS filers (ifrs-full taxonomy) are not parsed in this stage; companies using
non-standard extension tags will have missing fields. Missing stays missing (NaN).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd

# field -> (kind, unit, [us-gaap concepts in priority order])
FIELDS: dict[str, tuple[str, str, list[str]]] = {
    "revenue": ("flow", "USD", ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet",
                                "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueGoodsNet",
                                "RevenuesNetOfInterestExpense"]),
    "cogs": ("flow", "USD", ["CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfGoodsSold"]),
    "gross_profit": ("flow", "USD", ["GrossProfit"]),
    "operating_income": ("flow", "USD", ["OperatingIncomeLoss"]),
    "pretax_income": ("flow", "USD", ["IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
                                      "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments"]),
    "net_income": ("flow", "USD", ["NetIncomeLoss", "ProfitLoss", "NetIncomeLossAvailableToCommonStockholdersBasic"]),
    "interest_expense": ("flow", "USD", ["InterestExpense", "InterestExpenseNonoperating", "InterestExpenseDebt"]),
    "tax": ("flow", "USD", ["IncomeTaxExpenseBenefit"]),
    "da": ("flow", "USD", ["DepreciationDepletionAndAmortization", "DepreciationAndAmortization",
                           "DepreciationAmortizationAndAccretionNet", "Depreciation"]),
    "ocf": ("flow", "USD", ["NetCashProvidedByUsedInOperatingActivities",
                            "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"]),
    "capex": ("flow", "USD", ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"]),
    "dividends_paid": ("flow", "USD", ["PaymentsOfDividendsCommonStock", "PaymentsOfDividends"]),
    "buybacks": ("flow", "USD", ["PaymentsForRepurchaseOfCommonStock"]),
    "sbc": ("flow", "USD", ["ShareBasedCompensation", "AllocatedShareBasedCompensationExpense"]),
    "shares_diluted": ("flow", "shares", ["WeightedAverageNumberOfDilutedSharesOutstanding",
                                          "WeightedAverageNumberOfSharesOutstandingBasic"]),
    "assets": ("stock", "USD", ["Assets"]),
    "current_assets": ("stock", "USD", ["AssetsCurrent"]),
    "liabilities": ("stock", "USD", ["Liabilities"]),
    "current_liabilities": ("stock", "USD", ["LiabilitiesCurrent"]),
    "equity": ("stock", "USD", ["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"]),
    "retained_earnings": ("stock", "USD", ["RetainedEarningsAccumulatedDeficit"]),
    "cash": ("stock", "USD", ["CashAndCashEquivalentsAtCarryingValue",
                              "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"]),
    "lt_debt": ("stock", "USD", ["LongTermDebtNoncurrent", "LongTermDebtAndCapitalLeaseObligations", "LongTermDebt"]),
    "st_debt": ("stock", "USD", ["LongTermDebtCurrent", "DebtCurrent", "ShortTermBorrowings",
                                 "LongTermDebtAndCapitalLeaseObligationsCurrent"]),
    "goodwill": ("stock", "USD", ["Goodwill"]),
    "shares_cover": ("stock", "shares", ["dei:EntityCommonStockSharesOutstanding"]),
    "shares_bs": ("stock", "shares", ["CommonStockSharesOutstanding"]),
}
FLOW_FIELDS = [k for k, v in FIELDS.items() if v[0] == "flow"]
STOCK_FIELDS = [k for k, v in FIELDS.items() if v[0] == "stock"]
PERIODIC_FORMS = {"10-K", "10-Q", "10-K/A", "10-Q/A", "10-KT", "10-QT"}
ANNUAL_FORMS = {"10-K", "10-K/A", "10-KT"}


@dataclass(frozen=True)
class Rec:
    start: date | None
    end: date
    val: float
    filed: date
    form: str


def _d(s: str) -> date:
    return date.fromisoformat(s)


def extract_field(facts: dict[str, Any], field: str) -> list[Rec]:
    """All reported values for a field, merging concepts by priority (first concept wins per period+filing)."""
    kind, unit, concepts = FIELDS[field]
    seen: dict[tuple, Rec] = {}
    for concept in concepts:
        tax, name = ("dei", concept.split(":", 1)[1]) if concept.startswith("dei:") else ("us-gaap", concept)
        node = facts.get("facts", {}).get(tax, {}).get(name)
        if not node:
            continue
        for r in node.get("units", {}).get(unit, []):
            try:
                if kind == "flow" and "start" not in r:
                    continue
                rec = Rec(_d(r["start"]) if kind == "flow" else None, _d(r["end"]), float(r["val"]), _d(r["filed"]), r.get("form", ""))
            except (KeyError, ValueError, TypeError):
                continue
            seen.setdefault((rec.start, rec.end, rec.filed), rec)
    return sorted(seen.values(), key=lambda x: (x.filed, x.end))


def _known(recs: list[Rec], asof: date) -> dict[tuple, float]:
    """(start,end) -> most recently filed value among filings on or before `asof`."""
    out: dict[tuple, float] = {}
    for r in recs:  # sorted by filed ascending, so later filings overwrite earlier ones
        if r.filed > asof:
            break
        out[(r.start, r.end)] = r.val
    return out


def _span(k: tuple) -> int:
    return (k[1] - k[0]).days + 1


def _find(known: dict[tuple, float], end: date, span: int, tol_end: int = 12, tol_span: int = 12) -> float | None:
    best, best_gap = None, 10 ** 9
    for k, v in known.items():
        gap = abs((k[1] - end).days)
        if gap <= tol_end and abs(_span(k) - span) <= tol_span and gap < best_gap:
            best, best_gap = v, gap
    return best


def flow_values(known: dict[tuple, float]) -> dict[str, Any]:
    """Derive fy, fy_prev, ttm and latest-quarter values from the known duration facts."""
    out: dict[str, Any] = {"fy": np.nan, "fy_prev": np.nan, "ttm": np.nan, "ttm_basis": None, "fy_end": None,
                           "q": np.nan, "q_prev_year": np.nan, "q_end": None, "period_end": None}
    if not known:
        return out
    annual = {k: v for k, v in known.items() if 350 <= _span(k) <= 380}
    a_key = max(annual, key=lambda k: k[1]) if annual else None
    if a_key is not None:
        out["fy"], out["fy_end"], out["period_end"] = annual[a_key], a_key[1], a_key[1]
        prev = _find(annual, a_key[1] - timedelta(days=365), 365)
        out["fy_prev"] = prev if prev is not None else np.nan
        out["ttm"], out["ttm_basis"] = annual[a_key], "fiscal_year"
        ytd = {k: v for k, v in known.items() if k[1] > a_key[1] and 80 <= _span(k) <= 290 and abs((k[0] - a_key[1]).days - 1) <= 10}
        if ytd:
            y_key = max(ytd, key=lambda k: (k[1], _span(k)))
            prior = _find(known, y_key[1] - timedelta(days=365), _span(y_key))
            if prior is not None:
                out["ttm"], out["ttm_basis"], out["period_end"] = annual[a_key] + ytd[y_key] - prior, "ttm", y_key[1]
    quarters = {k: v for k, v in known.items() if 80 <= _span(k) <= 100}
    # derive fiscal Q4 = fiscal year - nine-month year-to-date
    for k, v in annual.items():
        nine = [(kk, vv) for kk, vv in known.items() if kk[0] == k[0] and 260 <= _span(kk) <= 285]
        if nine:
            kk, vv = max(nine, key=lambda x: x[0][1])
            quarters.setdefault((kk[1] + timedelta(days=1), k[1]), v - vv)
    if quarters:
        q_key = max(quarters, key=lambda k: k[1])
        out["q"], out["q_end"] = quarters[q_key], q_key[1]
        py = _find(quarters, q_key[1] - timedelta(days=365), _span(q_key), tol_span=15)
        out["q_prev_year"] = py if py is not None else np.nan
        out["_quarters"] = quarters
        if out["ttm_basis"] is None:
            ordered = sorted(quarters.items(), key=lambda x: x[0][1])[-4:]
            if len(ordered) == 4 and (ordered[-1][0][1] - ordered[0][0][0]).days <= 380:
                out["ttm"], out["ttm_basis"], out["period_end"] = float(sum(v for _, v in ordered)), "sum_4q", q_key[1]
    return out


def sue_from_quarters(quarters: dict[tuple, float], n_hist: int = 8) -> float:
    """Standardised unexpected earnings under a seasonal random walk:
    SUE = (E_q - E_{q-4}) / std(E_j - E_{j-4} over the previous n_hist quarters). Needs >= 6 diffs."""
    if not quarters:
        return np.nan
    items = sorted(quarters.items(), key=lambda x: x[0][1])
    diffs: list[float] = []
    for k, v in items:
        py = _find(quarters, k[1] - timedelta(days=365), _span(k), tol_span=15)
        if py is not None:
            diffs.append(v - py)
    if len(diffs) < 6:
        return np.nan
    hist = np.array(diffs[-(n_hist + 1):-1], dtype=float)
    sd = hist.std(ddof=1)
    if not np.isfinite(sd) or sd <= 0:
        return np.nan
    return float(diffs[-1] / sd)


def build_snapshots(facts: dict[str, Any]) -> pd.DataFrame:
    """One row per periodic filing date. Index = filing date (when the information became public)."""
    recs = {f: extract_field(facts, f) for f in FIELDS}
    filing_dates = sorted({r.filed for f in ("net_income", "assets", "revenue") for r in recs[f] if r.form in PERIODIC_FORMS})
    rows: list[dict[str, Any]] = []
    for fd in filing_dates:
        row: dict[str, Any] = {"filed": pd.Timestamp(fd)}
        ni_quarters: dict[tuple, float] = {}
        for f in FLOW_FIELDS:
            if f == "shares_diluted":  # a weighted-average count: take the most recent period, never derive
                kn = _known(recs[f], fd)
                row["shares_diluted"] = kn[max(kn, key=lambda k: (k[1], -_span(k)))] if kn else np.nan
                continue
            fv = flow_values(_known(recs[f], fd))
            row[f"{f}_ttm"], row[f"{f}_fy"], row[f"{f}_fy_prev"] = fv["ttm"], fv["fy"], fv["fy_prev"]
            if f == "net_income":
                row["ttm_basis"], row["fy_end"], row["period_end"] = fv["ttm_basis"], fv["fy_end"], fv["period_end"]
                row["net_income_q"], row["net_income_q_prev_year"], row["q_end"] = fv["q"], fv["q_prev_year"], fv["q_end"]
                ni_quarters = fv.get("_quarters", {})
            if f == "revenue":
                row["revenue_q"], row["revenue_q_prev_year"] = fv["q"], fv["q_prev_year"]
        row["sue"] = sue_from_quarters(ni_quarters)
        fy_end = row.get("fy_end")
        for f in STOCK_FIELDS:
            known = _known(recs[f], fd)
            if not known:
                row[f] = np.nan
                if f not in ("shares_cover", "shares_bs"):
                    row[f"{f}_fy"], row[f"{f}_fy_prev"] = np.nan, np.nan
                continue
            last_key = max(known, key=lambda k: k[1])
            row[f] = known[last_key]
            if f == "shares_cover":
                row["shares_cover_date"] = pd.Timestamp(last_key[1])
            if f == "assets":
                row["balance_date"] = pd.Timestamp(last_key[1])
            if f in ("shares_cover", "shares_bs"):
                continue
            if fy_end is not None:
                def at(d: date) -> float:
                    c = [(abs((k[1] - d).days), v) for k, v in known.items() if abs((k[1] - d).days) <= 12]
                    return min(c)[1] if c else np.nan
                row[f"{f}_fy"], row[f"{f}_fy_prev"] = at(fy_end), at(fy_end - timedelta(days=365))
            else:
                row[f"{f}_fy"], row[f"{f}_fy_prev"] = np.nan, np.nan
        for k in ("fy_end", "period_end", "q_end"):
            row[k] = pd.Timestamp(row[k]) if row.get(k) is not None else pd.NaT
        rows.append(row)
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows).set_index("filed").sort_index()
    return derive_metrics(df)


def _nz(s: pd.Series) -> pd.Series:
    return s.fillna(0.0)


def _safe_div(a: pd.Series, b: pd.Series) -> pd.Series:
    return (a / b.where(b > 0)).astype(float)


def derive_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """Accounting ratios that do not depend on market price (price-based ratios are computed in the panel)."""
    d = df.copy()
    gp_ttm = d["gross_profit_ttm"].where(d["gross_profit_ttm"].notna(), d["revenue_ttm"] - d["cogs_ttm"])
    gp_fy = d["gross_profit_fy"].where(d["gross_profit_fy"].notna(), d["revenue_fy"] - d["cogs_fy"])
    gp_fy_prev = d["gross_profit_fy_prev"].where(d["gross_profit_fy_prev"].notna(), d["revenue_fy_prev"] - d["cogs_fy_prev"])
    d["gross_profit_ttm"], d["gross_profit_fy"], d["gross_profit_fy_prev"] = gp_ttm, gp_fy, gp_fy_prev
    d["total_debt"] = (_nz(d["lt_debt"]) + _nz(d["st_debt"])).where(d["lt_debt"].notna() | d["st_debt"].notna())
    d["net_debt"] = d["total_debt"] - _nz(d["cash"])
    d["fcf_ttm"] = d["ocf_ttm"] - _nz(d["capex_ttm"])
    d["ebit_ttm"] = d["operating_income_ttm"]
    d["ebitda_ttm"] = d["operating_income_ttm"] + d["da_ttm"]
    # margins
    d["gross_margin"] = _safe_div(gp_ttm, d["revenue_ttm"])
    d["operating_margin"] = _safe_div(d["operating_income_ttm"], d["revenue_ttm"])
    d["net_margin"] = _safe_div(d["net_income_ttm"], d["revenue_ttm"])
    d["fcf_margin"] = _safe_div(d["fcf_ttm"], d["revenue_ttm"])
    # returns
    d["roe"] = _safe_div(d["net_income_ttm"], d["equity"])
    d["roa"] = _safe_div(d["net_income_ttm"], d["assets"])
    tax_rate = (d["tax_ttm"] / d["pretax_income_ttm"].where(d["pretax_income_ttm"] > 0)).clip(0, 0.5).fillna(0.21)
    invested = d["equity"] + _nz(d["total_debt"]) - _nz(d["cash"])
    d["roic"] = _safe_div(d["operating_income_ttm"] * (1 - tax_rate), invested)
    d["gross_profitability"] = _safe_div(gp_ttm, d["assets"])  # Novy-Marx (2013)
    # quality / accruals (Sloan 1996, cash-flow form)
    d["accruals"] = _safe_div(d["net_income_ttm"] - d["ocf_ttm"], d["assets"])
    d["cash_conversion"] = _safe_div(d["ocf_ttm"], d["net_income_ttm"])
    # investment (Fama-French CMA style) and growth
    d["asset_growth"] = d["assets_fy"] / d["assets_fy_prev"].where(d["assets_fy_prev"] > 0) - 1
    d["revenue_growth"] = d["revenue_fy"] / d["revenue_fy_prev"].where(d["revenue_fy_prev"] > 0) - 1
    d["revenue_growth_q"] = d["revenue_q"] / d["revenue_q_prev_year"].where(d["revenue_q_prev_year"] > 0) - 1
    d["earnings_growth"] = (d["net_income_fy"] - d["net_income_fy_prev"]) / d["net_income_fy_prev"].abs().where(d["net_income_fy_prev"] != 0)
    # financial strength
    d["current_ratio"] = _safe_div(d["current_assets"], d["current_liabilities"])
    d["debt_to_equity"] = _safe_div(d["total_debt"], d["equity"])
    d["net_debt_to_ebitda"] = d["net_debt"] / d["ebitda_ttm"].where(d["ebitda_ttm"] > 0)
    d["interest_coverage"] = d["operating_income_ttm"] / d["interest_expense_ttm"].where(d["interest_expense_ttm"] > 0)
    d["sbc_to_revenue"] = _safe_div(d["sbc_ttm"], d["revenue_ttm"])
    d["piotroski"], d["piotroski_n"] = piotroski(d)
    return d


PIOTROSKI_SIGNALS = ["roa_positive", "ocf_positive", "roa_improving", "ocf_exceeds_net_income", "leverage_falling",
                     "liquidity_improving", "no_dilution", "gross_margin_improving", "asset_turnover_improving"]


def piotroski_signals(d: pd.DataFrame) -> pd.DataFrame:
    """Piotroski (2000) nine binary signals on fiscal-year data. NaN where inputs are missing."""
    def flag(cond: pd.Series, valid: pd.Series) -> pd.Series:
        return cond.astype(float).where(valid)
    roa = d["net_income_fy"] / d["assets_fy_prev"].where(d["assets_fy_prev"] > 0)
    cfo = d["ocf_fy"] / d["assets_fy_prev"].where(d["assets_fy_prev"] > 0)
    lev = d["lt_debt_fy"].fillna(0) / d["assets_fy"].where(d["assets_fy"] > 0)
    lev_prev = d["lt_debt_fy_prev"].fillna(0) / d["assets_fy_prev"].where(d["assets_fy_prev"] > 0)
    cr = d["current_assets_fy"] / d["current_liabilities_fy"].where(d["current_liabilities_fy"] > 0)
    cr_prev = d["current_assets_fy_prev"] / d["current_liabilities_fy_prev"].where(d["current_liabilities_fy_prev"] > 0)
    gm = d["gross_profit_fy"] / d["revenue_fy"].where(d["revenue_fy"] > 0)
    gm_prev = d["gross_profit_fy_prev"] / d["revenue_fy_prev"].where(d["revenue_fy_prev"] > 0)
    at = d["revenue_fy"] / d["assets_fy_prev"].where(d["assets_fy_prev"] > 0)
    out = pd.DataFrame(index=d.index)
    out["roa_positive"] = flag(roa > 0, roa.notna())
    out["ocf_positive"] = flag(cfo > 0, cfo.notna())
    # t-2 balances are not carried in the snapshot, so "improving" signals compare both years on the
    # prior-year asset base (documented deviation from Piotroski's beginning-of-year scaling)
    out["roa_improving"] = flag(d["net_income_fy"] > d["net_income_fy_prev"], d["net_income_fy"].notna() & d["net_income_fy_prev"].notna())
    out["ocf_exceeds_net_income"] = flag(d["ocf_fy"] > d["net_income_fy"], d["ocf_fy"].notna() & d["net_income_fy"].notna())
    out["leverage_falling"] = flag(lev <= lev_prev, lev.notna() & lev_prev.notna())
    out["liquidity_improving"] = flag(cr > cr_prev, cr.notna() & cr_prev.notna())
    # Needs split-adjusted share counts for two fiscal years, which the snapshot does not carry yet.
    # Left unevaluated (NaN): the score is reported as "x of piotroski_n signals", never padded.
    out["no_dilution"] = np.nan
    out["gross_margin_improving"] = flag(gm > gm_prev, gm.notna() & gm_prev.notna())
    rev_at_prev = d["revenue_fy_prev"] / d["assets_fy_prev"].where(d["assets_fy_prev"] > 0)
    out["asset_turnover_improving"] = flag(at > rev_at_prev, at.notna() & rev_at_prev.notna())
    return out


def piotroski(d: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """(score, number of signals that could be evaluated). The share-dilution signal is not evaluated
    in this stage, so the maximum attainable score is 8, and it is always displayed with its denominator."""
    sig = piotroski_signals(d)
    return sig.sum(axis=1, min_count=1), sig.notna().sum(axis=1)


def altman_z(row: pd.Series, market_cap: float) -> float:
    """Altman (1968) Z-score for public manufacturers:
    Z = 1.2*WC/TA + 1.4*RE/TA + 3.3*EBIT/TA + 0.6*MVE/TL + 1.0*Sales/TA.
    Not meaningful for financial companies; a screening diagnostic, not a prediction of failure."""
    ta, tl = row.get("assets"), row.get("liabilities")
    vals = [row.get("current_assets"), row.get("current_liabilities"), row.get("retained_earnings"),
            row.get("operating_income_ttm"), row.get("revenue_ttm"), ta, tl, market_cap]
    if any(v is None or not np.isfinite(v) for v in vals) or ta <= 0 or tl <= 0:
        return np.nan
    wc = row["current_assets"] - row["current_liabilities"]
    return float(1.2 * wc / ta + 1.4 * row["retained_earnings"] / ta + 3.3 * row["operating_income_ttm"] / ta
                 + 0.6 * market_cap / tl + 1.0 * row["revenue_ttm"] / ta)

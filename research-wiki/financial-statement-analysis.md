# Financial statement analysis

## 1. Definition

Turning reported income statements, balance sheets and cash-flow statements into measures of profitability, financial strength, cash-flow quality and earnings quality, using only what was public on each date.

## 2. Why it matters

Every fundamental factor, the screener and the red flags depend on it. A backtest that uses numbers before they were filed, or restated numbers before the restatement, is invalid.

## 3. Mathematical formula

**Point-in-time snapshots.** For each 10-K/10-Q filing date, the snapshot holds the most recently filed value of every period as known on that date. Research on date `t` uses the last snapshot filed strictly before `t`; snapshots older than 200 days are treated as missing.

**Trailing twelve months** = latest fiscal year + current year-to-date - the same year-to-date one year earlier. If the comparison is missing, the fiscal-year figure is used and labelled `FY`.

**Fiscal Q4** = fiscal year - nine-month year-to-date (companies do not report Q4 separately).

| Measure | Formula |
|---|---|
| Gross / operating / net margin | gross profit, operating income, net income over revenue |
| ROE, ROA | net income / equity, / assets |
| ROIC | operating income x (1 - tax rate) / (equity + debt - cash); tax rate clipped to 0-50%, 21% if unknown |
| Gross profitability | gross profit / total assets |
| Accruals | (net income - operating cash flow) / total assets |
| Free cash flow | operating cash flow - capital expenditure |
| Current ratio | current assets / current liabilities |
| Net debt / EBITDA | (debt - cash) / (operating income + D&A) |
| Interest coverage | operating income / interest expense |
| Asset growth | fiscal-year assets / prior-year assets - 1 |
| SUE | (E_q - E_{q-4}) / std of the previous eight seasonal differences, on quarterly net income |

**Piotroski F-score:** nine binary signals; eight are evaluated (ROA positive, operating cash flow positive, net income improving, cash flow above net income, leverage falling, current ratio improving, gross margin improving, asset turnover improving). The share-dilution signal is not evaluated. The score is always shown with its denominator.

**Altman Z** = 1.2 WC/TA + 1.4 RE/TA + 3.3 EBIT/TA + 0.6 MVE/TL + 1.0 Sales/TA. Not computed for financials and real estate.

## 4. How to interpret it

- Accruals above about 10% of assets: earnings are running ahead of cash.
- Altman Z below 1.81 is the original distress zone; above 2.99 the safe zone.
- F-score of 7 or more (of 8) is strong; 2 or less is weak.
- These are screening diagnostics. They are not fraud detection and not a probability of distress.

## 5. Data requirements

SEC EDGAR XBRL company facts, us-gaap taxonomy, with `filed` dates. Concept names vary by company and over time, so each field has a prioritised list of tags.

## 6. Practical application

The stock page shows a filing-date history of statements, the derived ratios, the screen outcome and any red flags. Red flags marked severe (distress-zone Z, coverage below 1.5x, F-score of 2 or less) block a buy signal.

## 7. Limitations

- IFRS filers (20-F, `ifrs-full`) are not parsed; they fail the screen with "no usable fundamentals".
- Companies using custom extension tags have missing fields; missing stays missing.
- "Improving" Piotroski signals compare two years on the prior-year asset base, a documented deviation from the original beginning-of-year scaling.
- Multi-class companies can report a share count for one class only. An implausible market cap (under 1% of both revenue and assets) is flagged and the stock is not ranked.
- Not yet covered: Beneish M-score, goodwill impairment, non-GAAP reconciliation, related-party transactions, debt maturity, cash conversion cycle.
- SIC-based sectors differ from GICS.

## 8. Sources

- Piotroski, J. (2000). Value investing: the use of historical financial statement information to separate winners from losers. *Journal of Accounting Research*.
- Sloan, R. (1996). Do stock prices fully reflect information in accruals and cash flows about future earnings? *The Accounting Review*.
- Altman, E. (1968). Financial ratios, discriminant analysis and the prediction of corporate bankruptcy. *Journal of Finance*.
- Novy-Marx, R. (2013). The other side of value: the gross profitability premium. *Journal of Financial Economics*.
- Bernard, V. and Thomas, J. (1989). Post-earnings-announcement drift. *Journal of Accounting Research*.
- Beneish, M. (1999). The detection of earnings manipulation. *Financial Analysts Journal*. (deferred)
- SEC EDGAR API documentation; FASB Accounting Standards Codification.

## 9. Implementation status

Implemented in `backend/app/research/fundamentals.py` (snapshots, ratios, Piotroski, Altman) and `research/signals.py` (red flags). Beneish M-score and the items listed under Limitations are deferred.

## 10. Associated tests

- `tests/test_fundamentals.py::test_ttm_is_fiscal_year_plus_ytd_minus_prior_ytd`
- `tests/test_fundamentals.py::test_point_in_time_restatement_only_visible_after_it_is_filed`
- `tests/test_fundamentals.py::test_known_never_uses_future_filings`
- `tests/test_fundamentals.py::test_q4_is_derived_from_fiscal_year_minus_nine_months`
- `tests/test_fundamentals.py::test_sue_seasonal_random_walk`
- `tests/test_fundamentals.py::test_real_apple_filing_values` (checked against Apple's FY2026 10-K values)
- `tests/test_fundamentals.py::test_altman_z_formula`, `test_piotroski_reports_denominator_and_bounds`
- `tests/test_panel.py::test_fundamentals_enter_strictly_after_filing`, `test_stale_fundamentals_become_missing`

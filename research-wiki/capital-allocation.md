# Capital allocation

## 1. Definition

What management does with the cash the business generates: reinvest, acquire, pay down debt, pay dividends, or repurchase shares, and at what return.

## 2. Why it matters

Over long periods, the return on retained earnings determines whether growth creates or destroys value per share. Dilution quietly transfers value away from existing owners.

## 3. Mathematical formula

Implemented:

- Shareholder yield = (dividends paid + share repurchases, trailing twelve months) / market cap
- Asset growth = fiscal-year assets / prior-year assets - 1 (the investment factor, negative sign)
- Stock-based compensation intensity = SBC / revenue (red flag above 20%)
- Free-cash-flow margin, cash conversion = operating cash flow / net income

Deferred:

- Reinvestment rate = (capex - D&A + change in working capital) / after-tax operating income
- Return on incremental invested capital = change in after-tax operating income / change in invested capital
- Buyback effectiveness = repurchase price paid versus estimated intrinsic value
- Dividend sustainability = dividends / free cash flow, with debt and coverage checks
- Net share-count change (needed for the ninth Piotroski signal)

## 4. How to interpret it

- Rapid asset growth has historically preceded lower returns; the investment factor ranks slow growers higher.
- A high dividend or buyback yield is not automatically good. Check that free cash flow covers it and that debt is not funding it.
- Buybacks should be judged by price paid against value, which needs the valuation suite.

## 5. Data requirements

Cash-flow statement items (dividends, repurchases, capex, SBC), share counts by period, acquisition spending. Insider ownership, compensation and guidance accuracy need proxy statements and transcripts, which are not parsed.

## 6. Practical application

Conservative investment has a 5% starting weight. Shareholder yield, asset growth and the SBC warning appear on each stock page. Form 4 and DEF 14A filings are stored and linked but not analysed.

## 7. Limitations

- No judgment about acquisition discipline, management quality or communication. The platform does not infer integrity from wording.
- Shareholder yield uses gross repurchases and ignores issuance, so it overstates the net return of cash at companies that issue heavily.
- Asset growth mixes organic investment with acquisitions.

## 8. Sources

- Cooper, M., Gulen, H. and Schill, M. (2008). Asset growth and the cross-section of stock returns. *Journal of Finance*.
- Fama, E. and French, K. (2015). A five-factor asset pricing model. *Journal of Financial Economics*.
- Thorndike, W. (2012). *The Outsiders*.
- Mauboussin, M. and Callahan, D. Capital Allocation (Credit Suisse research note).
- Buffett, W. Berkshire Hathaway shareholder letters (repurchases and retained earnings).

## 9. Implementation status

| Item | Status |
|---|---|
| Shareholder yield, asset growth factor, SBC red flag, cash conversion | Implemented (`research/panel.py`, `fundamentals.py`, `signals.py`) |
| Reinvestment rate, incremental ROIC, buyback effectiveness, dividend sustainability score | Deferred |
| Insider ownership, compensation, guidance accuracy | Deferred (needs proxy and transcript parsing) |

## 10. Associated tests

- `tests/test_screen_score_signal.py::test_red_flags`
- `tests/test_fundamentals.py::test_ttm_is_fiscal_year_plus_ytd_minus_prior_ytd` (asset growth)
- `tests/test_panel.py::test_panel_has_no_lookahead`

# Intrinsic valuation

## 1. Definition

An estimate of what a business is worth from its own cash flows, earnings power or assets, independent of its market price. Several models should be used together, because each fails in a different way.

## 2. Why it matters

Price only means something relative to value. A range of values from independent methods is the basis for a margin of safety.

## 3. Mathematical formula

**Deferred models (documented for the next stage, not built):**

- Discounted cash flow: `V = sum_t FCF_t / (1 + r)^t + TV / (1 + r)^N`, with terminal value `TV = FCF_{N+1} / (r - g)` (perpetuity growth) or an exit multiple. `r` is WACC for unlevered cash flows and cost of equity for levered ones.
- WACC = `E/(D+E) * k_e + D/(D+E) * k_d * (1 - tax)`; cost of equity from CAPM `k_e = r_f + beta * ERP`.
- Earnings power value (Greenwald) = normalised after-tax operating earnings / cost of capital, assuming no growth.
- Gordon growth / dividend discount: `V = D_1 / (r - g)`.
- Net current asset value = current assets - total liabilities; net-net when price is below about two thirds of NCAV per share.
- Owner earnings (Buffett) = net income + non-cash charges - maintenance capex - required working-capital investment.

**Implemented relative-valuation measures:** P/E, P/B, P/S, EV/EBITDA, EBIT/EV, free-cash-flow yield, shareholder yield = (dividends + buybacks) / market cap. Ratios with a non-positive denominator are shown as missing, never as zero.

## 4. How to interpret it

A single point estimate is false precision. The planned output is a conservative / base / optimistic range with a sensitivity table over growth, margin, discount rate and terminal assumptions. Until then, the platform reports multiples and sector-relative percentiles only, and does not display an intrinsic value or a margin of safety.

## 5. Data requirements

Multi-year cash flows, capex split into maintenance and growth, debt schedule, tax rate, risk-free rate (FRED is available), equity risk premium and beta. Analyst forecasts are not available from the free sources.

## 6. Practical application

Today: use the valuation block and the filing-date history table on a stock page to see whether multiples are low because the price fell or because earnings rose. Scenario ranges on the stock page are volatility-based price dispersion, not valuation.

## 7. Limitations

- DCF value is dominated by the terminal value and by `r - g`; small changes move the answer a lot.
- Maintenance capex is not reported. Any owner-earnings figure needs a stated assumption and an uncertainty band rather than one number.
- Multiples compare price with one year of accounting earnings, which can be far from normal.
- Enterprise value here uses reported debt and cash only; leases, pensions and minority interests are not adjusted.

## 8. Sources

- Damodaran, A. *Investment Valuation* and the NYU Stern data pages.
- Greenwald, B. et al. (2001). *Value Investing: From Graham to Buffett and Beyond*.
- Graham, B. and Dodd, D. (1934). *Security Analysis*.
- Gordon, M. (1959). Dividends, earnings, and stock prices. *Review of Economics and Statistics*.
- Campbell, J. and Shiller, R. (1988). Stock prices, earnings, and expected dividends. *Journal of Finance*.

## 9. Implementation status

| Item | Status |
|---|---|
| P/E, P/B, P/S, EV/EBITDA, EBIT/EV, FCF yield, shareholder yield | Implemented (`backend/app/research/panel.py`) |
| DCF with scenarios and sensitivity | Deferred |
| Earnings power value, normalised earnings, CAPE | Deferred |
| Dividend discount and Gordon growth | Deferred |
| NCAV, net-net, liquidation and sum-of-the-parts | Deferred |
| Intrinsic value range and margin of safety on the dashboard | Deferred |

## 10. Associated tests

- `tests/test_panel.py::test_market_cap_is_continuous_across_a_split` (market cap used by every multiple)
- `tests/test_panel.py::test_implausible_share_count_is_flagged_not_ranked`
- No tests exist for the deferred models because they are not built.

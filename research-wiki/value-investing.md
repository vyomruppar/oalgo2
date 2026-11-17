# Value investing

## 1. Definition

Buying an ownership interest in a business for less than a conservative estimate of what it is worth, and requiring a gap (the margin of safety) large enough to absorb errors in that estimate.

The frameworks are distinct, not interchangeable:

| Framework | Core logic | Main limitation |
|---|---|---|
| Graham and Dodd | Value from assets and normalised earnings; demand a margin of safety; diversify | Balance-sheet bargains are rare in large liquid stocks; book value understates intangible-heavy firms |
| Buffett and Munger | A durable business compounding at high returns on capital is worth paying a fair price for | Requires judgment about durability that numbers only partly capture |
| Fisher | Long-run growth from R&D, sales organisation and management depth | Largely qualitative; hard to test |
| Schloss | Asset value and balance-sheet discipline across many small positions | Needs small, illiquid stocks that this platform screens out |
| Klarman | Downside first; hold cash when nothing is cheap | Not a formula |
| Greenblatt | Rank on earnings yield (EBIT/EV) plus return on capital | Simple ranks are crowded and cost-sensitive |
| Neff | Low P/E with total return (growth plus yield) | P/E is distorted by cyclical earnings |
| Marks | Risk is the probability of permanent loss; cycles and expectations matter | Descriptive rather than prescriptive |
| Mauboussin | Price implies expectations; test them against ROIC and the competitive-advantage period | Needs explicit forecasts |
| Greenwald | Earnings power value versus asset reproduction value reveals franchise value | Needs normalised earnings and maintenance capex |
| Shiller | Cyclically adjusted earnings smooth the cycle | A market-level tool; ten years of history per company |

## 2. Why it matters

Value is one of the most studied return characteristics, and the margin-of-safety discipline directly addresses the platform's goal of measuring downside before upside.

## 3. Mathematical formula

Implemented valuation yields (trailing twelve months, market cap `M`, enterprise value `EV = M + debt - cash`):

- Earnings yield = net income / M
- Greenblatt earnings yield = EBIT / EV
- Book-to-market = shareholders' equity / M
- Free-cash-flow yield = (operating cash flow - capital expenditure) / M
- Value composite = mean of the sector-neutral z-scores of the four yields

Graham-style thresholds available through the screener and red flags: current ratio, debt to equity, interest coverage, price and size minimums. They are configuration, not laws.

Margin of safety = 1 - price / intrinsic value. **Not computed in Stage 1** because no intrinsic-value model is implemented yet (see [intrinsic-valuation.md](intrinsic-valuation.md)).

## 4. How to interpret it

A high value percentile means the stock is cheap relative to sector peers on current fundamentals. It does not say why. Cheap stocks are often cheap for a reason, which is why the score pairs value with quality, financial strength and red flags, and why a severe red flag blocks a buy signal.

## 5. Data requirements

SEC XBRL company facts (income statement, balance sheet, cash flow) with filing dates; split-adjusted price; share count.

## 6. Practical application

Value has a 20% starting weight in the research score. The dashboard shows each yield, the composite z-score and the sector-relative percentile on every stock page. The standalone value strategy is backtested on the Strategies page.

## 7. Limitations

- Yields use reported, not normalised, earnings. One-off gains or cyclical peaks inflate them.
- Book value is weak for firms whose assets are mostly intangible or that have bought back a lot of stock.
- In the Stage 1 backtest (2015 to 2026, today's liquid survivors) the value strategy did not beat the equal-weight universe. That is a result, not a defect, and it is shown as "not supported".
- Financial companies need different measures; sector-neutral ranking only partly handles this.

## 8. Sources

- Graham, B. and Dodd, D. (1934). *Security Analysis*.
- Graham, B. (1949). *The Intelligent Investor*.
- Buffett, W. Berkshire Hathaway Owner's Manual and shareholder letters (owner earnings: 1986 letter).
- Greenblatt, J. (2005). *The Little Book That Beats the Market*.
- Greenwald, B. et al. (2001). *Value Investing: From Graham to Buffett and Beyond*.
- Fama, E. and French, K. (1992). The cross-section of expected stock returns. *Journal of Finance*.
- Lakonishok, J., Shleifer, A. and Vishny, R. (1994). Contrarian investment, extrapolation, and risk. *Journal of Finance*.
- Columbia Business School, History of Value Investing.

## 9. Implementation status

| Item | Status | Where |
|---|---|---|
| Valuation yields and value composite | Implemented | `backend/app/research/panel.py`, `factors.py` |
| Greenblatt combined rank | Implemented | `factors.greenblatt_rank` |
| Graham-style financial-strength checks | Implemented as screen rules and red flags | `universe/screener.py`, `research/signals.py` |
| Margin of safety, net-net, NCAV | Deferred | needs the valuation suite |
| Owner earnings | Deferred | maintenance capex cannot be separated from XBRL totals without assumptions |

## 10. Associated tests

- `tests/test_panel.py::test_factor_composites_handle_missing_inputs`
- `tests/test_panel.py::test_sector_neutral_zscore_removes_sector_level`
- `tests/test_panel.py::test_implausible_share_count_is_flagged_not_ranked`
- `tests/test_screen_score_signal.py::test_red_flags`

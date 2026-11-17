# Business quality and moats

## 1. Definition

Quality is the ability to earn high returns on capital and convert earnings into cash. A moat is a structural reason those returns persist: brand, switching costs, network effects, cost advantage, scale, intangible assets, distribution, or regulatory barriers.

## 2. Why it matters

A cheap stock with deteriorating economics is a value trap. Quality is also an independently documented return characteristic, and it tends to hold up when the market falls.

## 3. Mathematical formula

Quality composite (sector-neutral z-scores, averaged):

- gross profitability = gross profit / total assets (positive sign)
- ROIC = after-tax operating income / invested capital (positive)
- accruals = (net income - operating cash flow) / assets (negative)
- Piotroski F-score (positive)

Quality-Minus-Junk (profitability, growth, safety, payout) is **deferred**; the composite above covers its profitability and part of its safety leg.

Moat durability has no formula. The measurable evidence is the level and stability of gross margin and ROIC over many years.

## 4. How to interpret it

A high quality percentile says the company is more profitable and more cash-backed than sector peers today. It is not a moat verdict. The platform never labels a company as having a moat: it shows the margin and ROIC history and leaves that judgment to the reader. Popularity or a familiar brand is not evidence.

## 5. Data requirements

Multi-year SEC fundamentals. Market share, retention, pricing trends and customer concentration are not in XBRL company facts and are not available from the free sources.

## 6. Practical application

Quality has a 15% starting weight. On a stock page, read the "Financial statements as filed" table downward: a gross margin and ROIC that stay high across years and through 2020 and 2022 is the pattern consistent with a durable advantage.

## 7. Limitations

- ROIC is distorted by buybacks, goodwill and large cash balances. Apple's ROIC above 80% is an arithmetic consequence of a small equity base, not a statement about incremental returns.
- No incremental ROIC, no return on tangible capital, no margin-stability score yet.
- Qualitative moat sources (switching costs, network effects) cannot be measured from statements.
- In the Stage 1 backtest the quality factor had the best information coefficient among fundamental factors (t about 1.8) but the top-30 quality portfolio did not beat the equal-weight universe.

## 8. Sources

- Novy-Marx, R. (2013). The other side of value: the gross profitability premium. *Journal of Financial Economics*.
- Asness, C., Frazzini, A. and Pedersen, L. (2019). Quality minus junk. *Review of Accounting Studies*.
- Fama, E. and French, K. (2015). A five-factor asset pricing model. *Journal of Financial Economics*.
- Greenwald, B. and Kahn, J. (2005). *Competition Demystified*.
- Mauboussin, M. and Callahan, D. Measuring the Moat (Credit Suisse / Morgan Stanley research notes).
- Buffett, W. Berkshire Hathaway shareholder letters.

## 9. Implementation status

| Item | Status |
|---|---|
| Quality composite and percentile | Implemented (`research/factors.py`) |
| Margin and ROIC history on the stock page | Implemented |
| Moat scoring, incremental ROIC, margin stability, QMJ | Deferred |
| Fisher-style qualitative assessment | Out of scope for automated scoring |

## 10. Associated tests

- `tests/test_panel.py::test_factor_composites_handle_missing_inputs`
- `tests/test_screen_score_signal.py::test_score_is_bounded_and_weights_renormalise_when_data_missing`
- `tests/test_fundamentals.py::test_real_apple_filing_values`

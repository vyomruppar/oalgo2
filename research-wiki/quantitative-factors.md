# Quantitative factors

## 1. Definition

A factor is a measurable stock characteristic associated with differences in average returns across stocks. The platform builds composite factors from several related metrics, ranks stocks within the screened universe, and tests each factor on its own before combining them.

## 2. Why it matters

A small set of independently documented characteristics is more reliable than a large collection of indicators. Testing each one separately shows which actually carry information in the data the platform has.

## 3. Mathematical formula

For each date, each input `x` is winsorised at the 2nd and 98th percentiles and standardised: `z = (x - mean) / std`. Accounting-based inputs are standardised within sector (sectors with fewer than five names fall back to the whole universe). A composite is the mean of its available input z-scores, signed so that higher is better.

| Composite | Inputs (sign) | Sector-neutral |
|---|---|---|
| Value | earnings yield, EBIT/EV, book-to-market, FCF yield (+) | yes |
| Momentum | 12-1 month and 6-1 month total return (+) | no |
| Quality | gross profitability, ROIC (+), accruals (-), Piotroski (+) | yes |
| Investment | asset growth (-) | yes |
| Low volatility | 1-year realised volatility (-) | no |
| Earnings momentum | SUE, quarterly revenue growth y/y (+) | yes |
| Size | log market cap (-) | no |
| Short-term reversal | prior 1-month return (-) | no |
| Financial strength | interest coverage, current ratio (+), net debt/EBITDA (-) | yes |

Momentum 12-1 = `P(t-21) / P(t-252) - 1` on total-return prices, skipping the latest month.

Rank information coefficient (IC) for a month = Spearman correlation between the factor z-score and the next 21-trading-day return, entered at the next open. Reported as mean, t-statistic and share of positive months.

Research score = weighted mean of component percentiles (0 to 100) over components that have data; weights are re-normalised when a component is missing, and the missing share lowers the data-quality grade (A to D).

Factor regressions (CAPM alpha and beta against SPY) are implemented. Per-stock Fama-French three-, five- and Carhart four-factor loadings are **deferred**; the Ken French daily factors are downloaded and currently supply the risk-free rate.

## 4. How to interpret it

- A percentile says where a stock ranks today among screened peers. It is not a forecast and not a probability.
- An IC of 0.02 to 0.05 with a t-statistic above 2 would be meaningful for a monthly factor. Most factors do not reach that in the Stage 1 data.
- Factors are cyclical. A factor that fails for a decade can still be real, and one that worked in-sample can be noise.

## 5. Data requirements

Daily total-return prices (at least 252 bars), point-in-time SEC fundamentals, sector classification, and a universe large enough for cross-sectional ranks.

## 6. Practical application

The Strategies & Factors page shows each factor's IC table and monthly IC series, the factor correlation heatmap, and a top-N long-only backtest per factor. The stock page shows each component's percentile and its contribution in points.

Strategy classification follows the evidence: multifactor, value, momentum, quality, low volatility, investment, earnings momentum and trend following are evidence-backed in the literature; short-term reversal, the 50/200 crossover and the 52-week-high breakout are labelled "needs validation".

## 7. Limitations

- The universe is today's most liquid surviving stocks. Momentum in particular is flattered: the first run showed it far ahead of everything else, which is what selecting past winners into the universe produces.
- About 130 monthly cross-sections of roughly 200 stocks is a small sample.
- Published anomalies shrink after publication and after costs (see sources). Many do not replicate.
- Earnings momentum uses a seasonal random-walk surprise on net income, not analyst consensus, because estimates are not available from the free sources.
- Sector neutrality uses SIC-based sectors.
- No short side: every strategy is long-only, so results mix the factor with market exposure.

## 8. Sources

- Fama, E. and French, K. (1993). Common risk factors in the returns on stocks and bonds. *Journal of Financial Economics*.
- Fama, E. and French, K. (2015). A five-factor asset pricing model. *Journal of Financial Economics*.
- Carhart, M. (1997). On persistence in mutual fund performance. *Journal of Finance*.
- Jegadeesh, N. and Titman, S. (1993). Returns to buying winners and selling losers. *Journal of Finance*.
- Jegadeesh, N. (1990). Evidence of predictable behavior of security returns. *Journal of Finance*.
- Ang, A., Hodrick, R., Xing, Y. and Zhang, X. (2006). The cross-section of volatility and expected returns. *Journal of Finance*.
- Frazzini, A. and Pedersen, L. (2014). Betting against beta. *Journal of Financial Economics*.
- Moskowitz, T., Ooi, Y. and Pedersen, L. (2012). Time series momentum. *Journal of Financial Economics*.
- George, T. and Hwang, C. (2004). The 52-week high and momentum investing. *Journal of Finance*.
- Hou, K., Xue, C. and Zhang, L. (2020). Replicating anomalies. *Review of Financial Studies*.
- Patton, A. and Weller, B. (2020). What you see is not what you get: the costs of trading market anomalies. *Journal of Financial Economics*.
- Kenneth R. French Data Library.

## 9. Implementation status

| Item | Status | Where |
|---|---|---|
| Nine factor composites, winsorising, sector-neutral z-scores | Implemented | `backend/app/research/factors.py` |
| Point-in-time panel shared by scoring, backtests and ML | Implemented | `research/panel.py` |
| Configurable 0-100 score with contributions | Implemented | `research/scoring.py` |
| Factor IC, correlation, per-factor backtests | Implemented | `jobs/pipeline.py`, `backtest/strategies.py` |
| CAPM alpha/beta | Implemented | `backtest/metrics.py` |
| FF3/FF5/Carhart loadings per stock, APT | Deferred |
| News headline sentiment (FinBERT or word list) as a score component | Implemented, weight 0 by default: no test history | `research/sentiment.py` |
| Analyst revisions, QMJ, pairs/cointegration, Kalman | Deferred |

## 10. Associated tests

- `tests/test_panel.py::test_panel_has_no_lookahead`
- `tests/test_panel.py::test_zscore_winsorize_percentile`, `test_sector_neutral_zscore_removes_sector_level`
- `tests/test_panel.py::test_forward_returns_start_at_next_open`
- `tests/test_screen_score_signal.py::test_score_is_bounded_and_weights_renormalise_when_data_missing`
- `tests/test_screen_score_signal.py::test_changing_weights_changes_ranking_input`
- `tests/test_backtest_engine.py::test_build_targets_top_n_and_cash_remainder`
- `tests/test_indicators.py` (all technical indicators, including a causality test)

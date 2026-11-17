# Statistical validation

## 1. Definition

The controls that separate a real effect from an artefact of the data or of the testing process, and the statistics used to say how confident a result deserves to be.

## 2. Why it matters

It is easy to produce a backtest that looks excellent and means nothing. Testing many ideas on the same history guarantees that some look good by chance. Validation is mandatory for every strategy and model on the platform, and results that do not survive it are downgraded in the interface rather than hidden.

## 3. Mathematical formula

**Timing.** Features at date `t` use prices through the close of `t` and filings filed strictly before `t`. Trades fill at the open of `t+1`. Forward-return labels run from the open of `t+1`.

**Costs.** Commission plus slippage in basis points of traded notional, each way (default 1 + 9). Sensitivity is reported at 0, 10, 25 and 50 bps.

**Segments.** The evaluation window is split chronologically 50% / 25% / 25% into train, validation and out-of-sample. Rule-based strategies have no fitted parameters, so these are sub-period stability checks.

**Walk-forward (ML).** Expanding window, retrained every 12 months; the last 12 months of each training window are held out as validation; a one-month purge separates the last training label from the first test date so overlapping 21-day labels cannot leak.

**Stationary bootstrap** (Politis and Romano): resample blocks of geometric length (mean 21 days) to keep autocorrelation; report the 2.5% and 97.5% quantiles of the resampled Sharpe ratio.

**Probabilistic Sharpe Ratio:** `PSR = Phi( (SR - SR0) * sqrt(n - 1) / sqrt(1 - skew * SR + (kurt - 1)/4 * SR^2) )`, per-period Sharpe.

**Deflated Sharpe Ratio:** PSR with `SR0` set to the expected maximum Sharpe of `N` unskilled trials: `SR0 = sqrt(V) * ((1 - g) * Phi^-1(1 - 1/N) + g * Phi^-1(1 - 1/(N e)))`, `V` the variance of the trials' Sharpe ratios, `g` the Euler-Mascheroni constant.

**Excess-return test:** two-sided test that the mean daily return over the equal-weight universe is zero, Newey-West standard error with five lags.

**Benjamini-Hochberg:** sort the `m` p-values; adjusted `p_(i) = min over j >= i of p_(j) * m / j`; a strategy is a discovery if adjusted p is at most 0.10.

**Model validation rule:** out-of-sample rank IC positive with t-statistic above 2; gradient boosting must also beat the logistic baseline.

**Drift:** Population Stability Index `sum((a_i - e_i) * ln(a_i / e_i))` over training-quantile bins.

## 4. How to interpret it

- Status "supported" requires all of: positive excess over the equal-weight universe after costs, positive excess in the out-of-sample segment, FDR-adjusted significance, and a Deflated Sharpe Ratio of at least 0.95.
- The yardstick is the equal-weight universe, not SPY. The universe is built from today's liquid survivors, so every strategy on it beats SPY for reasons unrelated to skill.
- A Sharpe interval that includes zero means the result is not distinguishable from noise.
- A large gap between training and out-of-sample model metrics is the size of the overfit.

## 5. Data requirements

Long price history, point-in-time fundamentals, a record of how many strategies were tried, and ideally delisted securities (not available from the free sources).

## 6. Practical application

Every strategy on the Strategies page carries a hypothesis, definition, benchmark, assumptions and validation status with reasons. The Model Monitor shows train, validation and out-of-sample metrics side by side, calibration, accuracy by year, and drift. In the first full run no ML model validated, so none contributes to scores.

## 7. Limitations

- **Survivorship bias is disclosed, not solved.** Delisted companies are missing and the universe is chosen by today's liquidity. Absolute backtest returns are overstated.
- The Deflated Sharpe counts only the strategies in the code. Ideas discarded during design are not counted, so it is still optimistic.
- Probability of Backtest Overfitting (combinatorially symmetric cross-validation) is deferred.
- Costs are a flat rate; there is no market-impact model or borrow cost, and no intraday execution modelling.
- Corporate actions rely on the provider's split and dividend adjustments; a validator flags daily moves above 60% as possible unadjusted actions.
- About eleven years of history covers few distinct market regimes.

## 8. Sources

- Bailey, D. and López de Prado, M. (2014). The deflated Sharpe ratio. *Journal of Portfolio Management*.
- Bailey, D. and López de Prado, M. (2012). The Sharpe ratio efficient frontier. *Journal of Risk*.
- Benjamini, Y. and Hochberg, Y. (1995). Controlling the false discovery rate. *Journal of the Royal Statistical Society B*.
- Politis, D. and Romano, J. (1994). The stationary bootstrap. *Journal of the American Statistical Association*.
- Harvey, C., Liu, Y. and Zhu, H. (2016). ... and the cross-section of expected returns. *Review of Financial Studies*.
- Newey, W. and West, K. (1987). A simple, positive semi-definite, heteroskedasticity and autocorrelation consistent covariance matrix. *Econometrica*.
- López de Prado, M. (2018). *Advances in Financial Machine Learning* (purging and embargo).
- Hou, K., Xue, C. and Zhang, L. (2020). Replicating anomalies. *Review of Financial Studies*.

## 9. Implementation status

| Item | Status | Where |
|---|---|---|
| Next-open execution, costs, cost sensitivity | Implemented | `backend/app/backtest/engine.py`, `runner.py` |
| Chronological segments, rolling Sharpe, performance by regime | Implemented | `backtest/runner.py` |
| Bootstrap interval, PSR, DSR, Benjamini-Hochberg, Newey-West test | Implemented | `backtest/validation.py` |
| Walk-forward ML with purge, calibration, PSI drift | Implemented | `research/ml.py` |
| In-progress daily bar excluded | Implemented | `data/yahoo.py::parse_chart` |
| Probability of Backtest Overfitting | Deferred |
| Survivorship-free universe | Not possible with free data |

## 10. Associated tests

- `tests/test_panel.py::test_panel_has_no_lookahead` (truncating future data leaves past features unchanged)
- `tests/test_indicators.py::test_indicators_are_causal`
- `tests/test_backtest_engine.py::test_trades_at_next_open_not_at_signal_close`
- `tests/test_backtest_engine.py::test_costs_are_charged_on_traded_notional`
- `tests/test_backtest_engine.py::test_segments_are_chronological_and_disjoint`
- `tests/test_validation.py` (Benjamini-Hochberg textbook case, PSR, expected maximum Sharpe, DSR, bootstrap, Newey-West)
- `tests/test_ml.py::test_walk_forward_is_chronological_with_purge`
- `tests/test_ml.py::test_pure_noise_is_not_validated_and_not_used`
- `tests/test_ml.py::test_planted_signal_is_found_and_validated`
- `tests/test_providers.py::test_parse_chart_drops_bar_of_open_session`

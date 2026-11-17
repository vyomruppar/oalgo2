# Portfolio and risk

## 1. Definition

The mathematics for measuring how a portfolio has behaved, how much it could lose, where its risk comes from, and how large a position should be.

## 2. Why it matters

Potential losses have to be evaluated alongside potential returns. A strategy with a higher return and a much deeper drawdown is not obviously better, and a position's weight understates or overstates its share of portfolio risk.

## 3. Mathematical formula

Daily returns `r`, 252 trading days per year.

| Metric | Formula |
|---|---|
| CAGR | `prod(1 + r)^(252/n) - 1` |
| Volatility | `std(r) * sqrt(252)` |
| Sharpe ratio | `mean(r - rf) / std(r - rf) * sqrt(252)` |
| Downside deviation | `sqrt(mean(min(r, 0)^2)) * sqrt(252)` |
| Sortino ratio | `mean(r - rf) * 252 / downside deviation` |
| Maximum drawdown | `min(equity / running peak - 1)`, the peak starting at initial capital |
| Calmar ratio | `CAGR / |max drawdown|` |
| Beta, alpha | OLS of `r - rf` on `benchmark - rf`; alpha annualised |
| Tracking error | `std(r - benchmark) * sqrt(252)` |
| Information ratio | `mean(r - benchmark) * 252 / tracking error` |
| Historical VaR at level `a` | minus the `(1 - a)` quantile of `r` |
| Historical CVaR | minus the mean of returns at or below that quantile |
| Parametric VaR | `-(mu + z_{1-a} * sigma)` under a normal distribution |
| Profit factor | gross profit / gross loss on closed positions |
| Turnover | one-way traded notional / average equity / years |

Covariance: Ledoit-Wolf shrinkage of the sample covariance of daily returns.

Risk contribution of position `i`: `RC_i = w_i * (Sigma w)_i / sigma_p`; the shares `RC_i / sigma_p` sum to one.

Concentration: Herfindahl index `sum(w^2)`; effective number of positions `1 / sum(w^2)`.

Position size: `w = risk budget / (annual volatility * sqrt(21/252))`, capped by a maximum weight (default 10%) and by 5% of average daily dollar volume.

Stop reference: `price - 2.5 * ATR(14)`. Scenario range over the holding period: `price * exp(+/- k * sigma * sqrt(63/252))`.

## 4. How to interpret it

- VaR is a threshold, not a worst case. CVaR is the average loss beyond it. Both assume the look-back window is representative.
- A stop does not cap a loss: prices gap. The portfolio page shows what each position's worst day of the last year would cost.
- Scenario ranges are volatility-based dispersion, labelled as such, and are not forecasts.

## 5. Data requirements

Daily total-return prices for positions and a benchmark, sector for each position, ATR and average dollar volume, a risk-free series (Ken French daily RF).

## 6. Practical application

Portfolio & Risk shows the paper portfolio's equity curve against the benchmark, allocation, sector exposure, VaR/CVaR, beta, risk contributions, correlation, stop and gap scenarios, days to liquidate, and warnings for concentration above 15%, a sector above 35% and pairs correlated above 0.70. The paper ticket on each stock page suggests a volatility-scaled size and names the binding constraint.

## 7. Limitations

- Portfolio risk is a historical simulation at current weights over one year; it will understate risk after a calm year.
- Parametric VaR assumes normal returns, which understates tails.
- Correlations rise in sell-offs, so diversification is weakest when it is needed.
- The paper benchmark is the S&P 500 price index and excludes dividends.
- Optimisers are deferred: no mean-variance, minimum-variance, maximum-Sharpe, risk-parity or Black-Litterman allocation. Portfolios are equal-weighted, which avoids the unstable extreme weights that unconstrained optimisation produces.
- No volatility targeting at portfolio level.

## 8. Sources

- Markowitz, H. (1952). Portfolio selection. *Journal of Finance*.
- Sharpe, W. (1994). The Sharpe ratio. *Journal of Portfolio Management*.
- Sortino, F. and Price, L. (1994). Performance measurement in a downside risk framework. *Journal of Investing*.
- Rockafellar, R. and Uryasev, S. (2000). Optimization of conditional value-at-risk. *Journal of Risk*.
- Ledoit, O. and Wolf, M. (2004). A well-conditioned estimator for large-dimensional covariance matrices. *Journal of Multivariate Analysis*.
- Black, F. and Litterman, R. (1992). Global portfolio optimization. *Financial Analysts Journal*. (deferred)
- scikit-learn documentation, `sklearn.covariance.LedoitWolf`.

## 9. Implementation status

| Item | Status | Where |
|---|---|---|
| All metrics in the table above | Implemented | `backend/app/backtest/metrics.py` |
| Ledoit-Wolf covariance, risk contributions, concentration, sector exposure, scenarios | Implemented | `backend/app/risk/portfolio.py` |
| Volatility-scaled position sizing with caps | Implemented | `risk/portfolio.py::vol_scaled_size` |
| Paper ledger: fills, costs, dividends, splits, P&L, equity marks | Implemented | `backend/app/paper/ledger.py` |
| Optimisers, Black-Litterman, risk parity, volatility targeting, Kelly | Deferred |

## 10. Associated tests

- `tests/test_metrics.py` (total return, CAGR, Sharpe, Sortino, drawdown, Calmar, VaR/CVaR, alpha/beta, trade statistics)
- `tests/test_risk_paper_alerts.py::test_risk_contributions_sum_to_one`
- `tests/test_risk_paper_alerts.py::test_position_sizing_caps`, `test_portfolio_analysis`
- `tests/test_risk_paper_alerts.py::test_paper_order_fills_at_next_open_with_costs`
- `tests/test_risk_paper_alerts.py::test_paper_dividends_splits_and_realized_pnl`
- `tests/test_risk_paper_alerts.py::test_paper_rejections_and_no_shorting`

# Concept-to-feature map

Where each concept from the research brief lives in the platform. **Built** means implemented and covered by tests. **Partial** means a usable subset exists. **Deferred** means documented only.

## Universe and data

| Concept | Status | Code | Dashboard |
|---|---|---|---|
| NYSE/NASDAQ verification; OTC exclusion | Built | `backend/app/data/nasdaq_trader.py` | Overview, stock header |
| Configurable screener with reasons | Built | `universe/screener.py` | Settings, stock page |
| Bid-ask spread screen | Deferred (no spread data) | | |
| Caching, retries, rate limits, stale detection, provider health | Built | `data/http.py`, `data/validate.py` | Overview, Settings |
| Point-in-time fundamentals | Built | `research/fundamentals.py`, `research/panel.py` | Stock page |

## Strategies and factors

| Concept | Status | Code |
|---|---|---|
| Value, momentum, quality, profitability, investment, low volatility, size | Built | `research/factors.py` |
| Earnings momentum and post-earnings drift (SUE) | Built | `research/fundamentals.py::sue_from_quarters` |
| Relative strength vs benchmark | Built | `research/indicators.py::relative_strength` |
| Multifactor composite | Built | `backtest/strategies.py`, `research/scoring.py` |
| CAPM alpha and beta | Built | `backtest/metrics.py::alpha_beta` |
| Fama-French 3/5 and Carhart loadings, APT | Deferred (factor data is downloaded) | `data/french.py` |
| Cross-sectional momentum | Built | strategy `momentum` |
| Time-series momentum / trend following with market filter | Built | strategy `trend` |
| Moving-average crossover, breakout | Built, labelled "needs validation" | strategies `ma_cross`, `breakout` |
| Short-term reversal | Built, labelled "needs validation" | strategy `reversal` |
| Bollinger z-score, RSI as mean-reversion signals | Partial: indicators built, no standalone strategy | `research/indicators.py` |
| Pairs, cointegration, spread trading, Kalman | Deferred | |
| Realised volatility, breadth, risk-on/off regime | Built | `research/regime.py` |
| GARCH, hidden Markov models | Deferred | |
| RSI, MACD, SMA, EMA, Bollinger, ATR, OBV, MFI, VWAP (daily approximation), Ichimoku | Built | `research/indicators.py` |
| Revenue and earnings growth, margins, FCF, leverage | Built | `research/fundamentals.py` |
| Earnings surprises | Partial (seasonal random walk, no consensus) | |
| Analyst revisions, insider and institutional data, guidance | Deferred (no free source) | |
| Piotroski | Partial (8 of 9 signals) | `fundamentals.py::piotroski` |
| Altman Z, Greenblatt rank | Built | `fundamentals.py`, `factors.py` |
| Beneish M-score, Quality-Minus-Junk | Deferred | |
| Graham screens | Partial (thresholds via screener and red flags) | |
| DCF, EPV, DDM, NCAV, owner earnings, moat and capital-allocation scores | Deferred | |

## Machine learning

| Concept | Status | Code |
|---|---|---|
| Logistic regression baseline | Built | `research/ml.py` |
| Gradient boosting (scikit-learn histogram GBM) | Built | `research/ml.py` |
| Walk-forward validation with purge, calibration, importance, drift | Built | `research/ml.py` |
| Validation gate before a model affects scores | Built | `ml.train_and_report`, `pipeline.py` |
| Random forest, XGBoost, SVM, neural networks, LSTM, ensembles | Deferred: the baseline did not beat noise, so more complex models are not justified yet | |
| Reinforcement learning, genetic algorithms | Deferred (experimental) | |

## Scoring and signals

| Concept | Status | Code |
|---|---|---|
| 0-100 score, adjustable weights, missing-data handling, double-count control | Built | `research/scoring.py` |
| STRONG BUY / BUY / HOLD / SELL / WATCHLIST / no action | Built | `research/signals.py` |
| Explanation payload (breakdown, entry, exit, invalidation, scenarios, events, sources) | Built | `signals.build_payload` |

## Backtesting, risk, paper trading

| Concept | Status | Code |
|---|---|---|
| Portfolio backtests with costs and next-open fills | Built | `backtest/engine.py` |
| Single-stock buy and hold | Built | `engine.buy_and_hold` |
| Train / validation / out-of-sample, rolling windows, regimes | Built | `backtest/runner.py` |
| Benchmarks: SPY, QQQ, equal-weight universe | Built | `runner.py` |
| Sharpe, Sortino, drawdown, Calmar, win rate, profit factor, turnover, exposure | Built | `backtest/metrics.py` |
| Bootstrap intervals, Deflated Sharpe, FDR | Built | `backtest/validation.py` |
| Probability of Backtest Overfitting | Deferred | |
| VaR, CVaR, beta, alpha, risk contribution, concentration, sector exposure, correlation | Built | `risk/portfolio.py` |
| Position sizing under risk constraints | Built | `risk/portfolio.py::vol_scaled_size` |
| Ledoit-Wolf shrinkage | Built | `risk/portfolio.py` |
| Mean-variance, minimum variance, risk parity, Black-Litterman, Kelly, volatility targeting | Deferred | |
| Paper ledger with dividends and splits | Built | `paper/ledger.py` |
| Real-money execution | Never | |

## Automation and interface

| Concept | Status | Code |
|---|---|---|
| Scheduled scans, background processing | Built | `jobs/scheduler.py`, `jobs/pipeline.py` |
| Server-Sent Events with polling fallback | Built | `api/main.py`, `frontend/lib/live.tsx` |
| Alerts with deduplication | Built | `alerts/engine.py` |
| In-app and desktop notifications; optional e-mail | Built (e-mail untested against a live SMTP server) | `alerts/engine.py`, `frontend/lib/live.tsx` |
| Messaging integrations | Deferred | |
| Seven dashboard sections plus Settings | Built | `frontend/app/` |

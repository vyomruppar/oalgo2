# oalgo2 — quantitative stock research platform

A research and paper-trading workstation for NYSE- and NASDAQ-listed stocks. It verifies listings, screens and scores companies on evidence-backed factors, explains every signal, backtests strategies with costs, measures risk, and shows its own activity in a live dashboard.

**Research and paper trading only. It cannot place a real order, and nothing here is investment advice.**

## Quick start

Requirements: Python 3.11+, [uv](https://docs.astral.sh/uv/), Node 20+, [pnpm](https://pnpm.io/).

```bash
make install
```

```bash
make backend
```

```bash
make frontend
```

For AI headline sentiment, also install the free local FinBERT model once (about 1.5 GB with PyTorch; without it a built-in word list is used and labelled as such):

```bash
make install-ai
```

Open http://localhost:3000 and press **Run scan now**. The dashboard server forwards `/api` to the backend, so only port 3000 needs to be reachable: to use it from another device on your network, open `http://<this-computer's-address>:3000`. The first scan of 300 stocks takes about ten minutes (the free data sources are rate limited); later scans reuse the cache. After that, a scan runs automatically on weekdays at 22:30 UTC while the backend is running.

Optional settings go in `backend/.env` (see `.env.example`). Setting `OALGO_SEC_USER_AGENT` to your own contact string is recommended, as the SEC asks automated clients to identify themselves.

## Hosting on the web (free)

GitHub Actions runs the research engine every weekday and publishes to a password-protected Vercel site. No credit card, no server. Changes you make on the dashboard are applied by the next update, about 5 minutes later. Follow [`docs/deploy.md`](docs/deploy.md): two tokens, five repository secrets, one click.

## What it does

| Area | What you get |
|---|---|
| Universe | About 8,500 exchange-directory entries reduced to about 4,800 eligible NYSE/NASDAQ common stocks and ADRs, each exclusion with a reason |
| Screener | Price, market cap, dollar volume, history, volatility, fundamentals availability, sector, data quality; thresholds editable in the dashboard; pass/fail reason per rule |
| Fundamentals | Point-in-time from SEC filings: nothing is used before its filing date |
| Factors | Value, momentum, quality, investment, low volatility, earnings momentum, size, reversal, financial strength; sector-neutral where appropriate |
| Score and signals | 0-100 score with adjustable weights; STRONG BUY, BUY, HOLD, SELL, WATCHLIST or no action, with reasons, entry and exit conditions, invalidation, scenarios and sources |
| Backtesting | Eleven strategies, next-open fills, costs, train/validation/out-of-sample, cost sensitivity, bootstrap intervals, Deflated Sharpe, false-discovery control, benchmarks |
| Machine learning | Logistic and gradient-boosting baselines with purged walk-forward validation; a model affects scores only if it passes out-of-sample |
| Risk | VaR and CVaR, beta, risk contributions, concentration, sector exposure, correlation, stop and gap scenarios, position sizing |
| Paper trading | Hypothetical orders filled at the next open with costs; dividends and splits; P&L and equity curve |
| Alerts | New and changed signals, score moves, risk flags, exit conditions, unusual volume or volatility, filings, regime changes, provider failures; deduplicated; in-app, desktop, optional e-mail |
| My portfolio | Record the stocks you own (or import a CSV) and track value over time against the same dollars in SPY, gains, allocation, risk, signals and news. Tracking only: it never places an order |
| News and sentiment | Recent headlines for your holdings and for buy and watchlist names, scored for tone by a local FinBERT model (or a word list), with a recency- and relevance-weighted average per stock |
| Dashboard | Command (an interactive star map of the scanned universe with your holdings ringed), My portfolio, Market, a Quant lab split into Factors, Momentum and trend, Mean reversion, Volatility and regime, Machine learning and Validation, Stock explorer, News, Alerts, Scans and data, Settings; live updates over Server-Sent Events with polling fallback |

## What to know before trusting a number

- Prices are **end-of-day and delayed**. Nothing is real-time.
- Backtests carry **survivorship bias**: the free price source has no delisted companies and the universe is today's liquid stocks. Results are judged against the equal-weight universe for that reason.
- In the runs made during development, **most strategies did not beat the equal-weight universe after costs, and no machine-learning model passed validation**. The dashboard reports that as it is.
- A score ranks stocks. It is not a probability of profit.
- Sentiment reads **headlines only** and has no test history, so its weight in the score is zero unless you change it.

Full detail: [`docs/limitations.md`](docs/limitations.md).

## Layout

```
backend/        FastAPI service, research engine, tests (pytest)
frontend/       Next.js dashboard (TypeScript, Tailwind, ECharts, Lightweight Charts)
research-wiki/  Concepts, formulas, sources, implementation status
docs/           Data providers, limitations, concept-to-feature map
data/           Created at runtime: SQLite database, price and fundamentals files, HTTP cache (not committed)
```

## Tests

```bash
make test
```

Backend: 122 tests covering every indicator and metric against hand calculations, point-in-time and look-ahead checks, the backtester's fill timing and costs, validation statistics, the paper ledger, the holdings tracker, news parsing and sentiment, alert deduplication, parsers on recorded real responses, and the API. Frontend: type check, formatting tests and star-map layout tests.

## Data sources

Nasdaq Trader symbol directory, SEC EDGAR, Yahoo Finance chart endpoint (unofficial), Kenneth French Data Library, FRED. All free, no API keys. See [`docs/data-providers.md`](docs/data-providers.md) for limits, licensing and what a paid provider would add.

## Not built yet

Intrinsic-value models (DCF, earnings power, dividend discount, net-net), owner earnings, moat and capital-allocation scoring, Beneish M-score, Fama-French loadings per stock, pairs and cointegration, GARCH and hidden Markov regimes, neural networks, portfolio optimisers, paid-data adapters. See [`docs/concept-map.md`](docs/concept-map.md).

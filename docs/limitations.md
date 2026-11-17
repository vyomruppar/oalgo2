# Limitations

Read this before relying on any number the platform shows.

## What this platform is

A research and paper-trading workstation. It ranks and explains; it does not predict. It cannot place a real order: there is no broker dependency, credential, or code path for execution, and a test asserts that.

## Data

- **Prices are end-of-day and delayed.** The bar of a session still in progress is discarded. Nothing is real-time.
- **Survivorship bias.** No delisted companies. The scanned universe is today's most liquid listings. Every backtest overstates what was achievable, momentum-type strategies most of all.
- **Coverage.** A scan covers the most liquid eligible stocks first (300 by default, configurable up to the full list of about 4,800). Breadth and sector statistics describe the scanned set, not the whole market.
- **Fundamentals** come from us-gaap XBRL only. IFRS filers and companies with non-standard tags have gaps; they fail the fundamentals screen rather than being scored on partial data.
- **Share counts.** Multi-class companies can report one class only. Where price times shares is implausibly small (under 1% of both revenue and assets), market cap is treated as unknown and the stock is not ranked. Berkshire Hathaway class B is an example.
- **Sectors** are grouped from SEC SIC codes and do not match GICS.
- **No analyst estimates, earnings calendar, article text, transcripts, insider or institutional data.** Next-report dates are estimates. News is headlines only.
- **The price source is unofficial** and may be throttled or changed.

## Holdings tracker

- Tracking only. Recording a holding never creates an order, real or paper.
- Only securities in the NYSE/NASDAQ directory can be tracked. NYSE Arca ETFs such as SPY, mutual funds, options, bonds and cash are not supported.
- Purchases are tracked; sales, cash balances and fees are not. To record a sale, edit or remove the lot.
- Value history uses split-adjusted closes. Dividends are added as cash, not reinvested. The benchmark puts the same dollars into SPY on each purchase date.
- A holding outside the scanned set is valued but has no score until the next scan picks it up.

## News and sentiment

- Headlines come from an unofficial Yahoo Finance endpoint. Only the headline is read, never the article.
- A search for a ticker also returns market round-ups that merely mention it. These get a low relevance weight but still appear, marked "mentions only".
- FinBERT is a general finance-tone model. It can misread sarcasm, questions and headlines about a different company. The word-list fallback is cruder and is not AI.
- Sentiment has no backtest. Its weight in the research score is zero by default and it is never shown as a forecast.
- Headlines are kept for 21 days.

## Research

- **The score is not a probability.** It is a weighted percentile rank. The default weights are starting values, not optimised.
- **Signals are rules on top of the score**, with gates for trend, regime, data quality and red flags. "No action" is a valid outcome.
- **Red flags are diagnostics**, not findings of distress or manipulation. Altman Z is not computed for financials.
- **Piotroski** is evaluated on eight of nine signals.
- **Technical state** is part of the live score but not of the backtested multifactor strategy.
- **Scenario ranges** are historical-volatility dispersion, not forecasts.
- **Market regime** is a transparent rule set, not a statistical model.

## Validation

- Rule-based strategies have no fitted parameters, so train / validation / out-of-sample are sub-period checks.
- The Deflated Sharpe Ratio counts only the eleven coded strategies.
- Costs are a flat basis-point rate with no market impact.
- About eleven years of history spans few market regimes.
- Long-only portfolios: factor results include market exposure.
- In the runs made during development, most strategies did not beat the equal-weight universe after costs and no machine-learning model passed validation. The interface shows this as it is.

## Paper trading

- Fills at the next session's open with fixed slippage and commission; no partial fills, no liquidity limits on the fill itself, no short selling, no margin.
- Daily equity marks between scans use the positions held at the time of the mark.
- The benchmark on the portfolio page is the S&P 500 price index, without dividends.

## Operations

- Single local user, no authentication. Anyone who can reach port 3000 can see your holdings and change settings, so do not expose it to a network you do not control or to the public internet without adding a login in front of it.
- Desktop notifications require the dashboard to be open in a browser tab; e-mail needs SMTP settings.
- The scheduler runs inside the backend process; scans happen only while it is running.

## Not built yet

Discounted cash flow and other intrinsic-value models, margin of safety, owner earnings, moat and capital-allocation scoring, Beneish M-score, Fama-French loadings per stock, pairs and cointegration, Kalman filters, GARCH, hidden Markov regimes, neural networks, portfolio optimisers, paid-data adapters, intraday timeframes.

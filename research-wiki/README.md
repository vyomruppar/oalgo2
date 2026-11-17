# Research wiki

The knowledge base behind the platform. Each page states what a concept is, why it earns a place, how it is calculated here, what it cannot tell you, and whether it is actually implemented and tested.

A concept is only listed as **Implemented** if code exists and a test covers it. **Deferred** means it is documented but not built. Nothing here is a promise of returns: historical evidence describes the past.

| Page | Covers |
|---|---|
| [value-investing.md](value-investing.md) | Graham, Buffett/Munger, Fisher, Greenblatt and others; margin of safety; screens |
| [intrinsic-valuation.md](intrinsic-valuation.md) | DCF, earnings power, asset value, dividend models, relative valuation |
| [financial-statement-analysis.md](financial-statement-analysis.md) | Point-in-time fundamentals, profitability, strength, cash-flow and earnings quality |
| [business-quality-and-moats.md](business-quality-and-moats.md) | Moat evidence, ROIC durability, quality factor |
| [capital-allocation.md](capital-allocation.md) | Reinvestment, buybacks, dividends, dilution |
| [quantitative-factors.md](quantitative-factors.md) | Factor definitions, composites, information coefficients, strategies |
| [portfolio-and-risk.md](portfolio-and-risk.md) | Return and risk metrics, VaR/CVaR, sizing, covariance shrinkage |
| [statistical-validation.md](statistical-validation.md) | Look-ahead and survivorship controls, walk-forward, bootstrap, DSR, FDR |
| [research-sources.md](research-sources.md) | Data providers, curated links, licensing notes |

## Page format

Every page uses the same ten headings: Definition, Why it matters, Mathematical formula, How to interpret it, Data requirements, Practical application, Limitations, Sources, Implementation status, Associated tests.

## Status summary (Stage 1)

| Area | Status |
|---|---|
| Exchange verification, screener | Implemented, tested |
| Point-in-time fundamentals from SEC XBRL | Implemented, tested (us-gaap only) |
| Factors: value, momentum, quality, investment, low volatility, size, reversal, earnings momentum, financial strength | Implemented, tested |
| Piotroski F-score | Implemented on 8 of 9 signals (share-dilution signal not evaluated) |
| Altman Z-score, Greenblatt rank | Implemented, tested |
| Technical indicators | Implemented, tested |
| Backtester, costs, walk-forward ML, bootstrap, Deflated Sharpe, FDR | Implemented, tested |
| Risk engine, paper trading, alerts | Implemented, tested |
| DCF, earnings power value, dividend discount, net-net, sum-of-the-parts | Deferred |
| Owner earnings with maintenance-capex range, moat scoring, capital-allocation scoring | Deferred |
| Beneish M-score, Quality-Minus-Junk composite, analyst revisions | Deferred |
| Pairs/cointegration, Kalman, GARCH, HMM, LSTM, reinforcement learning | Deferred |
| Black-Litterman, risk parity, mean-variance optimisation | Deferred (Ledoit-Wolf covariance and volatility sizing are implemented) |

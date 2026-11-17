# Research sources

## 1. Definition

The data providers the platform reads from, and a curated library of primary references. The library is a starting point for study, not a claim that any source endorses any strategy.

## 2. Why it matters

Every research conclusion has to name its source and date. Each stock page lists the sources used and their as-of dates; each backtest lists its disclosures.

## 3. Mathematical formula

Not applicable. Freshness rules: prices are stale when the last completed bar is more than four business days old; fundamentals are treated as missing 200 days after their filing date.

## 4. How to interpret it

Three labels are used throughout the interface and are never mixed: **end-of-day** (delayed prices), **as filed** (SEC data, by filing date) and **historical** (research series). Nothing is labelled real-time, because nothing is.

## 5. Data requirements

Network access to the seven hosts listed below. No API keys.

## 6. Practical application

### Data providers in use

| Provider | Host | Used for | Notes |
|---|---|---|---|
| Nasdaq Trader symbol directory | `www.nasdaqtrader.com` | NYSE/NASDAQ listing verification | Public daily files. Current listings only. |
| SEC EDGAR | `data.sec.gov`, `www.sec.gov` | Fundamentals, filings, filing dates, SIC codes | Public domain. Fair-access policy: at most 10 requests per second and a declared User-Agent (set `OALGO_SEC_USER_AGENT`). |
| Yahoo Finance chart endpoint | `query2.finance.yahoo.com` | Daily prices, dividends, splits, index levels | Unofficial and undocumented. Personal research use. Rate limited. No delisted securities. |
| Kenneth R. French Data Library | `mba.tuck.dartmouth.edu` | Risk-free rate, factor returns | Free for research; cite the library. |
| FRED | `fred.stlouisfed.org` | Treasury yields | Public CSV export; individual series may carry their own terms. |

A full comparison with paid providers is in [`docs/data-providers.md`](../docs/data-providers.md).

### Curated library

Value investing and valuation
- Columbia Business School, [History of Value Investing](https://business.columbia.edu/heilbrunn/about/valueinvestinghistory)
- Berkshire Hathaway, [Owner's Manual](https://www.berkshirehathaway.com/2001ar/ownersmanual.html)
- Aswath Damodaran, [valuation resources](https://pages.stern.nyu.edu/~adamodar/) and [data](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/data.html)

Quantitative factors
- [Kenneth R. French Data Library](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html)
- [AQR Research](https://www.aqr.com/Insights/Research)
- [Journal of Financial Economics](https://www.sciencedirect.com/journal/journal-of-financial-economics)
- Hou, Xue and Zhang (2020), [Replicating Anomalies](https://academic.oup.com/rfs/article/33/5/2019/5236964)
- Patton and Weller (2020), [What You See Is Not What You Get](https://doi.org/10.1016/j.jfineco.2020.02.012)

Financial statements and filings
- [SEC EDGAR full-text search](https://www.sec.gov/edgar/search/) and [API documentation](https://www.sec.gov/edgar/sec-api-documentation)
- [FASB](https://www.fasb.org/)

Risk and portfolio research
- [CFA Institute Research and Policy Center](https://rpc.cfainstitute.org/)
- [Portfolio Visualizer](https://www.portfoliovisualizer.com/)
- [FRED](https://fred.stlouisfed.org/)

Statistics and software
- [Penn State online statistics](https://online.stat.psu.edu/)
- [SciPy](https://docs.scipy.org/doc/scipy/), [scikit-learn](https://scikit-learn.org/stable/), [Statsmodels](https://www.statsmodels.org/stable/)

## 7. Limitations

- The Yahoo endpoint can change or be withdrawn without notice. It is the weakest link and the first thing a paid provider would replace.
- No source provides delisted-company prices, analyst estimates, a confirmed earnings calendar, news, transcripts, insider or institutional holdings.
- The Wikipedia links in the original research library are orientation reading; the platform's formulas follow the primary papers cited on each wiki page.
- Three of the academic links in the original brief (volatility-managed factors, long-run factor investing) were not used in Stage 1 because volatility management is not implemented.

## 8. Sources

The provider documentation and the links above.

## 9. Implementation status

All five providers are implemented with on-disk caching, retries with backoff, rate limiting, health tracking and failure alerts (`backend/app/data/`). Paid-provider adapters are deferred.

## 10. Associated tests

- `tests/test_listings.py` (exchange classification on real directory samples)
- `tests/test_providers.py` (parsers on recorded real responses; stale and bad-data detection)
- `tests/test_risk_paper_alerts.py::test_regime_and_provider_alerts` (failure and recovery notices)

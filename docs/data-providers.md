# Data providers

What the platform uses today, what each source cannot do, and what a paid provider would add. Plan names, prices and quotas change often; the paid-provider rows describe the general shape of each service as last documented by the vendor and must be checked on the vendor's site before buying. No pricing figure here was verified at build time.

## In use (all free)

| Provider | Data | Exchange coverage | History | Freshness | Limits | Licence |
|---|---|---|---|---|---|---|
| Nasdaq Trader symbol directory | Listings, ETF and test-issue flags, Nasdaq financial-status flag | NASDAQ, NYSE and other US venues (only NASDAQ and NYSE are kept) | Current listings only | Daily file | None stated; fetched at most twice a day | Public files |
| SEC EDGAR (`data.sec.gov`) | XBRL company facts, filing index, SIC code | Every SEC registrant | XBRL from about 2009 | As filed | 10 requests per second; declared User-Agent | Public domain |
| Yahoo Finance chart endpoint | Daily OHLCV, dividends, splits, index levels | US listed, currently trading | Decades for most stocks | End of day; latest bar delayed and partial during the session | Undocumented throttling; the platform uses about 2 requests per second | Unofficial; personal research use |
| Yahoo Finance search endpoint | News headlines (title, publisher, time, link) | US listed | Recent days only | Minutes to hours | Same host and throttling as prices | Unofficial; personal research use |
| Kenneth French Data Library | Daily factor returns, risk-free rate | US market aggregates | From 1926 | Monthly update, about two months behind | None | Free for research with attribution |
| FRED | Treasury yields | Macro | Decades | Daily, one-day lag | None on CSV export | Public; series-specific terms |

### What the free stack cannot do

1. **No delisted securities.** Backtests see only survivors. This is the largest weakness and cannot be fixed without paid data.
2. **No real-time or intraday prices.** The dashboard labels everything end-of-day.
3. **No analyst estimates or revisions**, so earnings surprise is measured against a seasonal random walk.
4. **No confirmed earnings calendar.** Next-report dates are estimated from last year's filing date and labelled as estimates.
5. **No news, transcripts, insider or institutional data** in structured form. Form 4 and proxy filings are linked, not parsed.
6. **No bid-ask spreads**, so the screener has no spread rule and costs use a flat basis-point assumption.
7. **IFRS filers** have no parsed fundamentals.
8. The Yahoo endpoint has no service guarantee.

## Paid options evaluated

| Provider | Would add | Typical constraints | Fit |
|---|---|---|---|
| Financial Modeling Prep | Standardised statements, analyst estimates, earnings calendar, delisted companies, insider and institutional data, news | Free tier is a small daily request quota with limited history; real-time and bulk endpoints need paid plans; redistribution restricted | Best single upgrade for fundamentals and events |
| Polygon | Clean adjusted aggregates, delisted tickers, corporate actions, intraday and real-time (plan dependent) | Free tier is end-of-day with a low per-minute request limit; real-time needs paid plans and exchange agreements | Best upgrade for prices and survivorship-free backtests |
| Alpha Vantage | Prices, fundamentals, technical indicators, some news sentiment | Free tier allows only a few dozen requests per day, which cannot cover a universe scan; premium is rate-tiered | Too limited on the free tier for scanning |
| Nasdaq Data Link | Curated datasets, including point-in-time fundamentals (Sharadar) with delisted companies | Most useful datasets are separate paid subscriptions | Strongest research-grade option; highest cost |
| Tiingo | End-of-day prices with delisted history on paid plans, fundamentals add-on | Free tier caps symbols per month | Reasonable low-cost price source |

Real-time US equity data from any vendor also requires accepting exchange terms; it is never free for redistribution.

## Adding a provider

Providers sit behind `HttpProvider` in `backend/app/data/http.py`, which supplies the cache, retries, rate limit and health record. A new adapter needs a parser that returns the same frames as `yahoo.parse_chart` (prices) or the same snapshot columns as `fundamentals.build_snapshots`, plus recorded-response tests. API keys must come from environment variables and must never reach the frontend or logs.

## Pipelines

| Pipeline | Source | Stored at | Validation |
|---|---|---|---|
| Listings | Nasdaq Trader | `securities` table | Type classification with a recorded exclusion reason |
| Liquidity ranking | Yahoo multi-symbol endpoint | `securities.avg_dollar_volume` | Symbols without data are not ranked |
| Prices, dividends, splits | Yahoo | `data/prices/*.parquet` | Non-positive and null rows dropped; OHLC consistency, 60% moves, gaps, zero volume, staleness flagged; open-session bar excluded |
| Fundamentals and filings | SEC EDGAR | `data/fundamentals/*.parquet`, `*.filings.json` | Point-in-time by filing date; stale after 200 days |
| Factors and risk-free | Ken French | cache | Missing-value codes removed |
| Macro | FRED | key-value store | Non-numeric observations dropped |
| Indexes | Yahoo (`^GSPC`, `^IXIC`, `^NDX`, `^VIX`) plus SPY and QQQ as total-return benchmarks | `data/prices/` | Same as prices |

A 404 from a provider (for example a foreign filer with no XBRL document) is recorded as "no data", not as an outage. Three consecutive real failures raise a provider alert; recovery raises one notice.

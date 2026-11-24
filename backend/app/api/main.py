"""FastAPI application: REST endpoints plus a Server-Sent Events stream.

Research and paper trading only. There is no endpoint, dependency or configuration that can place a
real order."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import hmac
import json
import logging
import re
from contextlib import asynccontextmanager
from typing import Any

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from ..alerts import engine as alerts
from ..backtest.strategies import STRATEGIES
from .. import updater
from ..config import get_settings
from ..data.quotes import Quotes
from ..data.yahoo import INDEX_SYMBOLS, YahooPrices, last_bar_age_days
from ..db import Alert, PaperPosition, ProviderHealth, ScanRun, ScoreHistory, Security, StockResult, init_db, kv_get, kv_set, session
from ..jobs import pipeline, scheduler
from ..jobs.events import bus, sse_format
from ..paper import ledger
from ..portfolio import holdings
from ..research import news_service, sentiment
from ..research.regime import regime_series
from ..research import indicators as ind
from ..research.scoring import COMPONENT_LABELS, ScoreConfig
from ..risk import portfolio as risk
from ..universe.screener import ScreenConfig

log = logging.getLogger(__name__)
SYMBOL_RE = re.compile(r"^[A-Z]{1,5}(-[A-Z])?$")
DISCLAIMER = "Research and paper trading only. Not investment advice. No real orders are ever placed."

PROVIDERS = [
    {"key": "nasdaq_trader", "name": "Nasdaq Trader symbol directory", "use": "NYSE/NASDAQ listing verification", "freshness": "daily file",
     "cost": "free", "limits": "Lists current listings only; no history of delisted symbols."},
    {"key": "sec_edgar", "name": "SEC EDGAR (submissions, XBRL company facts)", "use": "fundamentals, filings, filing dates", "freshness": "as filed",
     "cost": "free", "limits": "10 requests/second; us-gaap taxonomy only in this stage (IFRS filers have no fundamentals)."},
    {"key": "yahoo", "name": "Yahoo Finance chart endpoint (unofficial)", "use": "daily prices, dividends, splits, indexes", "freshness": "end of day / delayed",
     "cost": "free", "limits": "Unofficial and rate limited; personal research use; no delisted securities (survivorship bias); not real-time."},
    {"key": "yahoo_news", "name": "Yahoo Finance search endpoint (unofficial)", "use": "news headlines for sentiment", "freshness": "minutes to hours",
     "cost": "free", "limits": "Unofficial; headlines only, no article text; includes round-ups that merely mention the ticker."},
    {"key": "ken_french", "name": "Ken French Data Library", "use": "risk-free rate and factor returns", "freshness": "monthly update, about two months lag",
     "cost": "free", "limits": "Research benchmarks only."},
    {"key": "fred", "name": "FRED", "use": "Treasury yields", "freshness": "daily, one-day lag", "cost": "free", "limits": "Macro series only."},
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    scheduler.start()
    yield
    scheduler.stop()


app = FastAPI(title="oalgo2 quantitative research platform", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=get_settings().cors_origins, allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def require_backend_key(request, call_next):
    """In a hosted deployment only the dashboard server, which holds the key, may call the API."""
    key = get_settings().api_key
    path = request.url.path
    if key and path.startswith("/api") and path != "/api/health" and request.method != "OPTIONS":
        given = request.headers.get("x-backend-key", "")
        if not hmac.compare_digest(given.encode(), key.encode()):
            return JSONResponse({"detail": "missing or invalid backend key"}, status_code=401)
    return await call_next(request)


def _sym(symbol: str) -> str:
    s = symbol.upper().replace(".", "-")
    if not SYMBOL_RE.match(s):
        raise HTTPException(400, "invalid symbol")
    return s


def _scan_dict(r: ScanRun | None) -> dict[str, Any] | None:
    if r is None:
        return None
    return {"id": r.id, "started_at": r.started_at.isoformat(), "finished_at": r.finished_at.isoformat() if r.finished_at else None,
            "status": r.status, "stage": r.stage, "progress": r.progress, "stats": r.stats, "error": (r.error or "")[:300] or None}


def _row(r: StockResult) -> dict[str, Any]:
    p = r.payload or {}
    comps = {c["component"]: c["component_score"] for c in p.get("components", [])}
    return {"symbol": r.symbol, "company": p.get("company"), "exchange": p.get("exchange"), "sector": p.get("sector"),
            "price": r.price, "price_date": r.price_date, "score": r.score, "signal": r.signal, "data_quality": r.data_quality,
            "screen_pass": r.screen_pass, "fail_reasons": [d["detail"] for d in r.screen_detail if not d["passed"]],
            "components": comps, "n_red_flags": len(p.get("red_flags") or []), "market_cap": (p.get("fundamentals") or {}).get("market_cap"),
            "as_of": r.as_of.isoformat()}


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "disclaimer": DISCLAIMER}


# ---- overview -----------------------------------------------------------------------------------------
@app.get("/api/overview")
def overview() -> dict[str, Any]:
    with session() as s:
        last = s.scalars(select(ScanRun).order_by(ScanRun.id.desc()).limit(1)).first()
        last_ok = s.scalars(select(ScanRun).where(ScanRun.status == "ok").order_by(ScanRun.id.desc()).limit(1)).first()
        top = s.scalars(select(StockResult).where(StockResult.score.is_not(None)).order_by(StockResult.score.desc()).limit(15)).all()
        sig_counts = dict(s.execute(select(StockResult.signal, func.count()).group_by(StockResult.signal)).all())
        n_sec = s.scalar(select(func.count()).select_from(Security)) or 0
        n_elig = s.scalar(select(func.count()).select_from(Security).where(Security.eligible.is_(True))) or 0
        health_rows = s.scalars(select(ProviderHealth)).all()
        recent_alerts = s.scalars(select(Alert).where(Alert.kind == "signal").order_by(Alert.id.desc()).limit(10)).all()
        unread = s.scalar(select(func.count()).select_from(Alert).where(Alert.read.is_(False))) or 0
        ml_rep = kv_get("ml:report") or {}
        bt = kv_get("backtests") or {}
        nxt = scheduler.next_scan_time()
        return {
            "disclaimer": DISCLAIMER,
            "scan": {"running": pipeline.is_running(), "last": _scan_dict(last), "last_success": _scan_dict(last_ok),
                     "next_scheduled": nxt.isoformat() if nxt else None},
            "universe": {"listed": n_sec, "eligible_listings": n_elig, "scanned": (last_ok.stats.get("scanned") if last_ok else None),
                         "passed": (last_ok.stats.get("passed") if last_ok else None), "failed": (last_ok.stats.get("failed") if last_ok else None),
                         "screen_fail_reasons": (last_ok.stats.get("screen_fail_reasons") if last_ok else None),
                         "listing_exclusions": (last_ok.stats.get("listing_exclusions") if last_ok else None),
                         "coverage_note": "The scan covers the most liquid eligible listings first; raise the scan size in Settings to widen it."},
            "signals": {str(k): v for k, v in sig_counts.items()},
            "top": [_row(r) for r in top],
            "new_signals": [alerts.to_dict(a) for a in recent_alerts],
            "unread_alerts": unread,
            "regime": kv_get("regime"),
            "strategies": [{"key": st.key, "name": st.name, "family": st.family, "evidence": st.evidence,
                            "status": ((bt.get("results") or {}).get(st.key, {}).get("validation_status") or {}).get("status")} for st in STRATEGIES],
            "models": [{"name": k, "validated": v.get("validated"), "active": ml_rep.get("active_model") == k,
                        "oos_rank_ic": (v.get("out_of_sample") or {}).get("rank_ic_mean")} for k, v in (ml_rep.get("models") or {}).items()],
            "ml_status": ml_rep.get("status"), "ml_version": ml_rep.get("version"),
            "providers": _providers(health_rows),
            "data_freshness": "End-of-day prices (delayed). Nothing on this dashboard is real-time.",
        }


def _providers(rows: list[ProviderHealth]) -> list[dict[str, Any]]:
    by = {r.provider: r for r in rows}
    out = []
    for p in PROVIDERS:
        r = by.get(p["key"])
        status = "unknown" if r is None else ("failing" if r.consecutive_failures >= 3 else "degraded" if r.consecutive_failures > 0 else "ok")
        out.append({**p, "status": status, "last_success": r.last_success.isoformat() if r and r.last_success else None,
                    "last_failure": r.last_failure.isoformat() if r and r.last_failure else None, "last_error": r.last_error if r and r.consecutive_failures else None,
                    "success_count": r.success_count if r else 0, "failure_count": r.failure_count if r else 0})
    return out


@app.get("/api/providers")
def providers() -> list[dict[str, Any]]:
    with session() as s:
        return _providers(list(s.scalars(select(ProviderHealth)).all()))


# ---- scans --------------------------------------------------------------------------------------------
class ScanRequest(BaseModel):
    fetch: bool = True
    max_symbols: int | None = Field(None, ge=20, le=6000)
    force_research: bool = False


@app.get("/api/scans")
def scans(limit: int = 20) -> list[dict[str, Any]]:
    with session() as s:
        return [_scan_dict(r) for r in s.scalars(select(ScanRun).order_by(ScanRun.id.desc()).limit(min(limit, 100))).all()]


@app.post("/api/scans", status_code=202)
def start_scan(req: ScanRequest) -> dict[str, Any]:
    if not pipeline.start_scan_thread(req.fetch, req.max_symbols, req.force_research):
        raise HTTPException(409, "a scan is already running")
    return {"started": True}


# ---- stocks -------------------------------------------------------------------------------------------
@app.get("/api/stocks")
def stocks(signal: str | None = None, passed: bool | None = None, sector: str | None = None, q: str | None = None,
           sort: str = "score", limit: int = Query(100, le=1000), offset: int = 0) -> dict[str, Any]:
    with session() as s:
        stmt = select(StockResult)
        if signal:
            stmt = stmt.where(StockResult.signal == signal)
        if passed is not None:
            stmt = stmt.where(StockResult.screen_pass.is_(passed))
        rows = s.scalars(stmt).all()
        out = [_row(r) for r in rows]
    if sector:
        out = [r for r in out if r["sector"] == sector]
    if q:
        ql = q.lower()
        out = [r for r in out if ql in r["symbol"].lower() or ql in (r["company"] or "").lower()]
    key = sort.lstrip("-")
    if key in ("score", "price", "market_cap"):
        out.sort(key=lambda r: (r[key] is None, -(r[key] or 0)))
    elif key == "symbol":
        out.sort(key=lambda r: r["symbol"])
    elif key in COMPONENT_LABELS:
        out.sort(key=lambda r: (r["components"].get(key) is None, -(r["components"].get(key) or 0)))
    if sort.startswith("-"):
        out.reverse()
    return {"total": len(out), "items": out[offset: offset + limit], "sectors": sorted({r["sector"] for r in out if r["sector"]})}


@app.get("/api/stocks/{symbol}")
def stock(symbol: str) -> dict[str, Any]:
    sym = _sym(symbol)
    with session() as s:
        sec = s.get(Security, sym)
        res = s.get(StockResult, sym)
        if sec is None:
            raise HTTPException(404, "not a verified NYSE/NASDAQ listing in the current symbol directory")
        hist = s.scalars(select(ScoreHistory).where(ScoreHistory.symbol == sym).order_by(ScoreHistory.id.desc()).limit(120)).all()
        return {
            "security": {"symbol": sec.symbol, "name": sec.name, "exchange": sec.exchange, "eligible": sec.eligible, "exclusion_reason": sec.exclusion_reason,
                         "security_type": sec.security_type, "sector": sec.sector, "industry": sec.industry, "cik": sec.cik,
                         "listing_source": sec.listing_source, "listing_as_of": sec.listing_as_of.isoformat() if sec.listing_as_of else None},
            "researched": res is not None,
            "result": {"as_of": res.as_of.isoformat(), "scan_id": res.scan_id, "screen_pass": res.screen_pass, "screen": res.screen_detail,
                       "score": res.score, "signal": res.signal, "data_quality": res.data_quality, **(res.payload or {})} if res else None,
            "score_history": [{"as_of": h.as_of.isoformat(), "score": h.score, "signal": h.signal} for h in reversed(hist)],
            "ml": _ml_for(sym),
            "disclaimer": DISCLAIMER,
        }


def _ml_for(sym: str) -> dict[str, Any]:
    rep = kv_get("ml:report") or {}
    rank = kv_get("ml:rank") or {}
    return {"active_model": rep.get("active_model"), "model_score": rank.get(sym), "status": rep.get("status"),
            "note": "Shown only when a model passed out-of-sample validation. A model score ranks stocks; it is not a probability of profit."}


RANGES = {"3m": 63, "6m": 126, "1y": 252, "2y": 504, "5y": 1260, "max": 100000}


def _nan_none(v: Any) -> Any:
    return None if v is None or (isinstance(v, float) and not np.isfinite(v)) else v


@app.get("/api/stocks/{symbol}/prices")
def stock_prices(symbol: str, range: str = "1y") -> dict[str, Any]:
    sym = _sym(symbol)
    y = YahooPrices()
    df = y.load(sym)
    if df is None or df.empty:
        raise HTTPException(404, "no price history stored for this symbol (it has not been scanned)")
    spy = y.load("SPY")
    iv = ind.compute_all(df, spy["adj_close"] if spy is not None else None)
    n = RANGES.get(range, 252)
    d, i = df.tail(n), iv.tail(n)
    cols = ["sma_20", "sma_50", "sma_200", "ema_12", "ema_26", "ema_50", "bb_upper", "bb_lower", "bb_mid", "rsi_14", "macd", "macd_signal",
            "macd_hist", "atr_14", "obv", "mfi_14", "vwap_20", "ichi_tenkan", "ichi_kijun", "ichi_span_a", "ichi_span_b", "rel_strength", "rvol_21"]
    age = last_bar_age_days(df)
    return {
        "symbol": sym, "source": "Yahoo Finance chart endpoint (unofficial)", "freshness": "end_of_day",
        "freshness_note": "Daily bars of completed sessions only, delayed. Prices are split-adjusted; a session still in progress is not shown.",
        "last_bar": df.index[-1].date().isoformat(), "last_bar_age_business_days": age, "stale": age > 4,
        "dates": [x.date().isoformat() for x in d.index],
        "ohlcv": {k: [_nan_none(float(v)) for v in d[k]] for k in ("open", "high", "low", "close", "volume")},
        "dividends": [[x.date().isoformat(), float(v)] for x, v in d["dividend"][d["dividend"] > 0].items()],
        "splits": [[x.date().isoformat(), float(v)] for x, v in d["split"][d["split"] != 1].items()],
        "indicators": {c: [_nan_none(round(float(v), 6)) if np.isfinite(v) else None for v in i[c]] for c in cols if c in i},
        "indicator_notes": {"vwap_20": "Rolling 20-day VWAP on daily typical price: an approximation, not intraday session VWAP.",
                            "rel_strength": "Total-return ratio to SPY, rebased to 1 at the start of the stored history."},
    }


FIN_COLS = ["period_end", "ttm_basis", "revenue_ttm", "gross_profit_ttm", "operating_income_ttm", "net_income_ttm", "ocf_ttm", "capex_ttm", "fcf_ttm",
            "assets", "liabilities", "equity", "cash", "total_debt", "net_debt", "shares_diluted", "gross_margin", "operating_margin", "net_margin",
            "roe", "roic", "current_ratio", "debt_to_equity", "interest_coverage", "accruals", "asset_growth", "revenue_growth", "piotroski", "piotroski_n", "sue"]


@app.get("/api/stocks/{symbol}/fundamentals")
def stock_fundamentals(symbol: str) -> dict[str, Any]:
    sym = _sym(symbol)
    st = get_settings()
    pq, fj = st.fundamentals_dir / f"{sym}.parquet", st.fundamentals_dir / f"{sym}.filings.json"
    filings = json.loads(fj.read_text()).get("filings", []) if fj.exists() else []
    if not pq.exists():
        return {"symbol": sym, "available": False, "reason": "No us-gaap XBRL fundamentals stored (not scanned, IFRS filer, or no filings).",
                "filings": filings, "source": "SEC EDGAR"}
    snap = pd.read_parquet(pq)
    rows = []
    for filed, r in snap.tail(24).iloc[::-1].iterrows():
        row: dict[str, Any] = {"filed": filed.date().isoformat()}
        for c in FIN_COLS:
            v = r.get(c)
            if isinstance(v, pd.Timestamp):
                row[c] = v.date().isoformat()
            elif isinstance(v, str) or v is None:
                row[c] = v
            else:
                row[c] = _nan_none(float(v)) if pd.notna(v) else None
        rows.append(row)
    return {"symbol": sym, "available": True, "source": "SEC EDGAR XBRL company facts (us-gaap)", "rows": rows, "filings": filings,
            "note": "Each row is what was publicly known on its filing date. TTM = fiscal year + year-to-date - prior year-to-date."}


# ---- universe -----------------------------------------------------------------------------------------
@app.get("/api/universe")
def universe(q: str | None = None, eligible: bool | None = None, limit: int = Query(100, le=500), offset: int = 0) -> dict[str, Any]:
    with session() as s:
        stmt = select(Security)
        if eligible is not None:
            stmt = stmt.where(Security.eligible.is_(eligible))
        if q:
            like = f"%{q.upper()}%"
            stmt = stmt.where(Security.symbol.like(like) | func.upper(Security.name).like(like))
        total = s.scalar(select(func.count()).select_from(stmt.subquery()))
        rows = s.scalars(stmt.order_by(Security.avg_dollar_volume.desc().nulls_last(), Security.symbol).limit(limit).offset(offset)).all()
        by_exch = dict(s.execute(select(Security.exchange, func.count()).where(Security.eligible.is_(True)).group_by(Security.exchange)).all())
        return {"total": total, "eligible_by_exchange": by_exch,
                "items": [{"symbol": r.symbol, "name": r.name, "exchange": r.exchange, "eligible": r.eligible, "exclusion_reason": r.exclusion_reason,
                           "security_type": r.security_type, "sector": r.sector, "last_price": r.last_price, "dollar_volume": r.avg_dollar_volume} for r in rows]}


# ---- market -------------------------------------------------------------------------------------------
@app.get("/api/market/indexes")
def market_indexes(range: str = "1y") -> dict[str, Any]:
    y = YahooPrices()
    n = RANGES.get(range, 252)
    out = {}
    names = {"SP500": "S&P 500", "NASDAQ_COMPOSITE": "NASDAQ Composite", "NASDAQ_100": "NASDAQ-100", "VIX": "CBOE Volatility Index"}
    for key, ys in INDEX_SYMBOLS.items():
        df = y.load(ys)
        if df is None or df.empty:
            out[key] = {"name": names[key], "available": False}
            continue
        d = df.tail(n)
        c = df["close"]
        out[key] = {"name": names[key], "available": True, "last": float(c.iloc[-1]), "last_bar": df.index[-1].date().isoformat(),
                    "change_1d": float(c.iloc[-1] / c.iloc[-2] - 1) if len(c) > 1 else None,
                    "change_range": float(d["close"].iloc[-1] / d["close"].iloc[0] - 1),
                    "dates": [x.date().isoformat() for x in d.index],
                    "ohlc": {k: [float(v) for v in d[k]] for k in ("open", "high", "low", "close")},
                    "volume": [float(v) for v in d["volume"]],
                    "realized_vol_21": [_nan_none(float(v)) for v in ind.realized_vol(df["close"], 21).tail(n)]}
    return {"freshness": "end_of_day", "source": "Yahoo Finance chart endpoint (unofficial); price-return index levels", "indexes": out}


@app.get("/api/market/summary")
def market_summary() -> dict[str, Any]:
    return {"regime": kv_get("regime"), "breadth": kv_get("market:breadth"), "sectors": kv_get("market:sectors"), "macro": kv_get("macro")}


# ---- strategies / factors / ML ------------------------------------------------------------------------
@app.get("/api/strategies")
def strategies() -> dict[str, Any]:
    bt = kv_get("backtests")
    if not bt:
        return {"available": False, "strategies": [{"key": s.key, "name": s.name, "family": s.family, "evidence": s.evidence,
                                                   "hypothesis": s.hypothesis, "definition": s.definition} for s in STRATEGIES]}
    slim = {k: {kk: vv for kk, vv in v.items() if kk not in ("equity", "drawdown", "rolling_sharpe")} for k, v in bt["results"].items()}
    return {"available": True, "label": bt["label"], "generated_at": bt["generated_at"], "disclosures": bt["disclosures"], "config": bt["config"],
            "strategies": bt["strategies"], "results": slim, "correlation": bt["correlation"],
            "benchmarks": {k: v["metrics"] for k, v in bt["benchmarks"].items()}, "universe_count": bt.get("universe_count")}


@app.get("/api/strategies/curves")
def strategy_curves(keys: str = "multifactor") -> dict[str, Any]:
    bt = kv_get("backtests")
    if not bt:
        raise HTTPException(404, "no backtests available yet")
    out = {}
    for k in keys.split(","):
        if k in bt["results"]:
            out[k] = {x: bt["results"][k][x] for x in ("equity", "drawdown", "rolling_sharpe")}
        elif k in bt["benchmarks"]:
            out[k] = {x: bt["benchmarks"][k][x] for x in ("equity", "drawdown")}
    return {"label": "backtested", "curves": out}


@app.get("/api/factors")
def factors() -> dict[str, Any]:
    return kv_get("factors:research") or {"available": False}


@app.get("/api/ml")
def ml_report() -> dict[str, Any]:
    return kv_get("ml:report") or {"status": "not_trained"}


# ---- paper portfolio and risk -------------------------------------------------------------------------
class OrderRequest(BaseModel):
    symbol: str
    side: str = Field(pattern="^(BUY|SELL|buy|sell)$")
    quantity: float = Field(gt=0)
    note: str | None = Field(None, max_length=500)


@app.get("/api/portfolio")
def portfolio() -> dict[str, Any]:
    return ledger.snapshot(YahooPrices().load)


@app.post("/api/portfolio/orders", status_code=201)
def paper_order(req: OrderRequest) -> dict[str, Any]:
    """Records a HYPOTHETICAL order in the paper ledger. Nothing is sent to any broker."""
    sym = _sym(req.symbol)
    y = YahooPrices()
    with session() as s:
        sec = s.get(Security, sym)
        if sec is None or not sec.eligible:
            raise HTTPException(400, "paper orders are limited to verified, eligible NYSE/NASDAQ listings")
    df = y.load(sym)
    if df is None or df.empty:
        raise HTTPException(400, "no stored price history for this symbol; it must be in the scanned set")
    try:
        oid = ledger.place_order(sym, req.side, req.quantity, df.index[-1].date().isoformat(), req.note)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    ledger.process(y.load, _spx_close(y))
    bus.publish("portfolio", {"order_id": oid})
    return {"order_id": oid, "status": "pending until the next session's open is available", "paper": True}


@app.post("/api/portfolio/reset")
def paper_reset(initial_cash: float = Query(100_000.0, gt=0, le=1e9)) -> dict[str, Any]:
    ledger.reset(initial_cash)
    return {"reset": True, "cash": initial_cash}


def _spx_close(y: YahooPrices) -> pd.Series | None:
    df = y.load("^GSPC")
    return df["close"] if df is not None else None


@app.get("/api/portfolio/risk")
def portfolio_risk() -> dict[str, Any]:
    y = YahooPrices()
    with session() as s:
        pos = s.scalars(select(PaperPosition)).all()
        symbols = [p.symbol for p in pos]
        qty = {p.symbol: p.quantity for p in pos}
        secs = {x.symbol: x.sector or "Unknown" for x in s.scalars(select(Security).where(Security.symbol.in_(symbols))).all()}
        res = {r.symbol: r.payload for r in s.scalars(select(StockResult).where(StockResult.symbol.in_(symbols))).all()}
    if not symbols:
        return {"empty": True, "message": "No open paper positions.", "label": "paper portfolio"}
    frames = {sym: y.load(sym) for sym in symbols}
    frames = {k: v for k, v in frames.items() if v is not None and len(v)}
    positions = pd.DataFrame({"quantity": {s_: qty[s_] for s_ in frames}, "price": {s_: float(v["close"].iloc[-1]) for s_, v in frames.items()}})
    adj = pd.DataFrame({s_: v["adj_close"] for s_, v in frames.items()})
    spy = y.load("SPY")
    atr = {s_: (res.get(s_, {}).get("risk") or {}).get("atr_14") for s_ in frames}
    adv = {s_: (res.get(s_, {}).get("risk") or {}).get("adv_dollar_63") for s_ in frames}
    out = risk.analyze(positions, adj, spy["adj_close"] if spy is not None else None, secs, atr, adv, ledger.get_cash())
    out["label"] = "paper portfolio; historical simulation at current weights"
    return pipeline._clean(out)


@app.get("/api/portfolio/size/{symbol}")
def position_size(symbol: str, risk_budget: float = Query(0.01, gt=0, le=0.05), max_weight: float = Query(0.10, gt=0, le=1)) -> dict[str, Any]:
    sym = _sym(symbol)
    with session() as s:
        r = s.get(StockResult, sym)
        if r is None or r.price is None:
            raise HTTPException(404, "symbol has not been researched")
        rk = (r.payload or {}).get("risk") or {}
    snap = ledger.snapshot(YahooPrices().load)
    out = risk.vol_scaled_size(rk.get("volatility_1y") or float("nan"), snap["equity"], r.price, risk_budget, max_weight, rk.get("adv_dollar_63"))
    out.update({"symbol": sym, "price": r.price, "equity": snap["equity"],
                "method": "weight = risk budget / one-month volatility, capped by maximum weight and 5% of average daily dollar volume"})
    return out


# ---- real holdings (tracking only) --------------------------------------------------------------------
class HoldingRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=12)
    shares: float = Field(gt=0)
    cost: float = Field(ge=0)
    purchase_date: str
    note: str | None = Field(None, max_length=300)


class HoldingUpdate(BaseModel):
    shares: float = Field(gt=0)
    cost: float = Field(ge=0)
    purchase_date: str
    note: str | None = Field(None, max_length=300)


class CsvImport(BaseModel):
    csv: str = Field(max_length=200_000)


def _research_map(symbols: list[str]) -> dict[str, dict[str, Any]]:
    with session() as s:
        res = {r.symbol: {"company": (r.payload or {}).get("company"), "sector": (r.payload or {}).get("sector"), "signal": r.signal,
                          "score": r.score, "risk": (r.payload or {}).get("risk") or {}}
               for r in s.scalars(select(StockResult).where(StockResult.symbol.in_(symbols))).all()}
        for sec in s.scalars(select(Security).where(Security.symbol.in_(symbols))).all():
            res.setdefault(sec.symbol, {"company": sec.name, "sector": sec.sector, "signal": None, "score": None, "risk": {}})
            res[sec.symbol]["company"] = res[sec.symbol]["company"] or sec.name
    return res


def _holdings_summary() -> dict[str, Any]:
    syms = holdings.symbols()
    out = holdings.summary(YahooPrices().load, _research_map(syms))
    sent = news_service.sentiment_by_symbol(syms) if syms else {}
    for p in out["positions"]:
        p["sentiment"] = sent.get(p["symbol"])
    return pipeline._clean(out)


@app.get("/api/holdings")
def get_holdings() -> dict[str, Any]:
    return _holdings_summary()


def _ensure_prices(sym: str) -> None:
    """A newly recorded holding may not have been scanned yet: fetch its history once so it can be valued."""
    y = YahooPrices()
    if y.load(sym) is None:
        try:
            y.fetch(sym)
        except Exception as e:
            log.warning("could not fetch prices for new holding %s: %s", sym, e)


@app.post("/api/holdings", status_code=201)
def add_holding(req: HoldingRequest) -> dict[str, Any]:
    """Records a lot the user already owns. This is bookkeeping: no order of any kind is created."""
    try:
        hid = holdings.add(req.symbol, req.shares, req.cost, req.purchase_date, req.note)
    except holdings.HoldingError as e:
        raise HTTPException(400, str(e)) from e
    _ensure_prices(_sym(req.symbol))
    bus.publish("portfolio", {"holding_id": hid})
    return {"id": hid}


@app.put("/api/holdings/{holding_id}")
def edit_holding(holding_id: int, req: HoldingUpdate) -> dict[str, Any]:
    try:
        holdings.update(holding_id, req.shares, req.cost, req.purchase_date, req.note)
    except holdings.HoldingError as e:
        raise HTTPException(404 if "not found" in str(e) else 400, str(e)) from e
    bus.publish("portfolio", {"holding_id": holding_id})
    return {"saved": True}


@app.delete("/api/holdings/{holding_id}")
def remove_holding(holding_id: int) -> dict[str, Any]:
    if not holdings.delete(holding_id):
        raise HTTPException(404, "holding not found")
    bus.publish("portfolio", {"holding_id": holding_id})
    return {"deleted": True}


@app.post("/api/holdings/import")
def import_holdings(req: CsvImport) -> dict[str, Any]:
    out = holdings.import_csv(req.csv)
    if out["errors"]:
        raise HTTPException(400, "; ".join(out["errors"][:8]))
    for sym in holdings.symbols():
        _ensure_prices(sym)
    bus.publish("portfolio", {"imported": out["imported"]})
    return out


@app.get("/api/holdings/history")
def holdings_history(range: str = "all") -> dict[str, Any]:
    y = YahooPrices()
    spy = y.load("SPY")
    return holdings.history(y.load, spy["adj_close"] if spy is not None else None, range)


@app.get("/api/holdings/risk")
def holdings_risk() -> dict[str, Any]:
    y = YahooPrices()
    summ = holdings.summary(y.load, _research_map(holdings.symbols()))
    pos = [p for p in summ["positions"] if p["price"] is not None]
    if not pos:
        return {"empty": True, "message": "No priced holdings to analyse.", "label": "your holdings"}
    frames = {p["symbol"]: y.load(p["symbol"]) for p in pos}
    positions = pd.DataFrame({"quantity": {p["symbol"]: p["shares"] for p in pos}, "price": {p["symbol"]: p["price"] for p in pos}})
    adj = pd.DataFrame({k: v["adj_close"] for k, v in frames.items()})
    spy = y.load("SPY")
    rmap = _research_map(list(frames))
    out = risk.analyze(positions, adj, spy["adj_close"] if spy is not None else None,
                       {k: (v.get("sector") or "Unknown") for k, v in rmap.items()},
                       {k: v["risk"].get("atr_14") for k, v in rmap.items()}, {k: v["risk"].get("adv_dollar_63") for k, v in rmap.items()}, 0.0)
    out["label"] = "your holdings; historical simulation at current weights"
    return pipeline._clean(out)


# ---- news and sentiment -------------------------------------------------------------------------------
@app.get("/api/news")
def news(symbol: str | None = None, scope: str = "holdings", limit: int = Query(60, le=300), min_relevance: float = 0.0) -> dict[str, Any]:
    if symbol:
        syms: list[str] | None = [_sym(symbol)]
    elif scope == "holdings":
        syms = holdings.symbols()
    else:
        syms = None
    items = news_service.items_for(syms, limit=limit * 3, min_relevance=min_relevance) if syms is None or syms else []
    return {"engine": sentiment.engine_status(), "scope": symbol or scope, "items": news_service.public(items)[:limit],
            "sentiment": pipeline._clean(news_service.sentiment_by_symbol(syms) if syms is None or syms else {}),
            "source": "Yahoo Finance search endpoint (unofficial); headlines only"}


@app.post("/api/news/refresh")
def news_refresh(symbol: str | None = None) -> dict[str, Any]:
    syms = [_sym(symbol)] if symbol else holdings.symbols()
    if not syms:
        return {"new": 0, "failed": 0, "symbols": 0}
    with session() as s:
        names = {x.symbol: x.name for x in s.scalars(select(Security).where(Security.symbol.in_(syms))).all()}
    if not names:
        raise HTTPException(404, "not a verified NYSE/NASDAQ listing")
    return news_service.refresh(names, ttl_seconds=300.0)


@app.get("/api/quotes")
def quotes(symbols: str = Query("", max_length=600)) -> dict[str, Any]:
    """Live prices, delayed about 15 minutes, for holdings (default) or the listed symbols."""
    want = [_sym(x) for x in symbols.split(",") if x.strip()] if symbols else holdings.symbols()
    want = list(dict.fromkeys(want))[:60]
    got = Quotes().get(want) if want else {}
    open_now = any(q["market_open"] for q in got.values())
    return {"quotes": got, "requested": len(want), "returned": len(got), "market_open": open_now,
            "delay": "about 15 minutes", "source": "Yahoo Finance (unofficial), delayed",
            "fetched_at": datetime.now(timezone.utc).isoformat()}


# ---- software updates (desktop install only) ---------------------------------------------------------
def _update_status(force: bool = False) -> dict[str, Any]:
    if not updater.enabled():
        return {"enabled": False}
    info = updater.check(force=force)
    return {"enabled": True, **info, "job": dict(updater.job), "scan_running": pipeline.is_running(),
            "restart_pending": (updater.UPDATES / "restart.flag").exists()}


@app.get("/api/update/status")
def update_status() -> dict[str, Any]:
    return _update_status()


@app.post("/api/update/check")
def update_check() -> dict[str, Any]:
    return _update_status(force=True)


@app.post("/api/update/install", status_code=202)
def update_install() -> dict[str, Any]:
    """Download the newest version, then restart into it. One click from the dashboard."""
    if not updater.enabled():
        raise HTTPException(400, "Updates are only available in the desktop app.")
    if pipeline.is_running():
        raise HTTPException(409, "A scan is running. Wait for it to finish, then update.")
    info = updater.check(force=True)
    if info.get("error"):
        raise HTTPException(502, info["error"])
    if not info.get("latest_sha"):
        raise HTTPException(502, "Could not find the newest version.")
    if not info.get("update_available"):
        raise HTTPException(409, "You already have the newest version.")
    if not updater.start_install(info["latest_sha"]):
        raise HTTPException(409, "An update is already in progress.")
    return {"started": True}


@app.post("/api/update/dismiss")
def update_dismiss() -> dict[str, Any]:
    if updater.job["state"] in ("error", "staged"):
        updater.reset_job()
    return {"ok": True}


# ---- dashboard and quant-lab data ---------------------------------------------------------------------
@app.get("/api/dashboard")
def dashboard() -> dict[str, Any]:
    """Everything the Command page needs in one call: holdings, the star map of the scanned universe, regime."""
    held = set(holdings.symbols())
    with session() as s:
        stars = []
        for r in s.scalars(select(StockResult)).all():
            p = r.payload or {}
            stars.append({"symbol": r.symbol, "company": p.get("company"), "sector": p.get("sector") or "Unknown", "score": r.score,
                          "signal": r.signal, "price": r.price, "market_cap": (p.get("fundamentals") or {}).get("market_cap"),
                          "ret_1d": (p.get("unusual") or {}).get("ret_1d"), "held": r.symbol in held, "screen_pass": r.screen_pass})
        last_ok = s.scalars(select(ScanRun).where(ScanRun.status == "ok").order_by(ScanRun.id.desc()).limit(1)).first()
        unread = s.scalar(select(func.count()).select_from(Alert).where(Alert.read.is_(False))) or 0
        recent = s.scalars(select(Alert).order_by(Alert.id.desc()).limit(8)).all()
        return {"holdings": _holdings_summary(), "stars": stars, "regime": kv_get("regime"),
                "scan": {"running": pipeline.is_running(), "last_success": _scan_dict(last_ok)},
                "unread_alerts": unread, "recent_alerts": [alerts.to_dict(a) for a in recent],
                "engine": sentiment.engine_status(), "disclaimer": DISCLAIMER}


@app.get("/api/lab/mean-reversion")
def lab_mean_reversion() -> dict[str, Any]:
    """Cross-section of short-term stretch: Bollinger z-score, RSI and one-month return for every scored stock."""
    with session() as s:
        rows = []
        for r in s.scalars(select(StockResult).where(StockResult.score.is_not(None))).all():
            t = (r.payload or {}).get("technicals") or {}
            if t.get("bb_z") is None or t.get("rsi_14") is None:
                continue
            rows.append({"symbol": r.symbol, "company": (r.payload or {}).get("company"), "sector": (r.payload or {}).get("sector"),
                         "bb_z": t["bb_z"], "rsi_14": t["rsi_14"], "ret_1m": t.get("ret_1m"), "ret_1d": t.get("ret_1d"),
                         "score": r.score, "signal": r.signal})
    return {"as_of": (kv_get("regime") or {}).get("as_of"), "items": rows,
            "note": "A stretched reading is a description, not a trade signal: in the backtests here the short-term reversal strategy "
                    "did not beat the equal-weight universe after costs."}


@app.get("/api/lab/regime-history")
def lab_regime_history(years: int = Query(5, ge=1, le=12)) -> dict[str, Any]:
    y = YahooPrices()
    spx, vix = y.load("^GSPC"), y.load("^VIX")
    if spx is None:
        return {"available": False}
    rs = regime_series(spx["close"], vix["close"] if vix is not None else None).dropna(subset=["score"]).tail(252 * years)
    counts = rs["regime"].value_counts(normalize=True).to_dict()
    return {"available": True, "method": "rule-based: trend, volatility percentile, VIX level (index data only)",
            "dates": [d.date().isoformat() for d in rs.index], "close": [round(float(v), 2) for v in rs["close"]],
            "score": [float(v) for v in rs["score"]], "regime": list(rs["regime"]),
            "realized_vol": [None if not np.isfinite(v) else round(float(v), 4) for v in rs["realized_vol_21"]],
            "share_of_days": {k: float(v) for k, v in counts.items()}}


# ---- alerts -------------------------------------------------------------------------------------------
@app.get("/api/alerts")
def list_alerts(unread: bool = False, kind: str | None = None, limit: int = Query(100, le=500)) -> dict[str, Any]:
    with session() as s:
        stmt = select(Alert)
        if unread:
            stmt = stmt.where(Alert.read.is_(False))
        if kind:
            stmt = stmt.where(Alert.kind == kind)
        rows = s.scalars(stmt.order_by(Alert.id.desc()).limit(limit)).all()
        n_unread = s.scalar(select(func.count()).select_from(Alert).where(Alert.read.is_(False))) or 0
        return {"unread": n_unread, "items": [alerts.to_dict(a) for a in rows]}


@app.post("/api/alerts/read")
def mark_read(alert_id: int | None = None) -> dict[str, Any]:
    with session() as s:
        stmt = select(Alert).where(Alert.read.is_(False))
        if alert_id is not None:
            stmt = stmt.where(Alert.id == alert_id)
        n = 0
        for a in s.scalars(stmt).all():
            a.read = True
            n += 1
    return {"marked": n}


# ---- configuration ------------------------------------------------------------------------------------
@app.get("/api/config")
def get_config() -> dict[str, Any]:
    st = get_settings()
    return {"screen": pipeline.get_screen_config().model_dump(), "score": pipeline.get_score_config().model_dump(),
            "scan_max_symbols": int(kv_get("config:scan_max_symbols", st.scan_max_symbols)),
            "component_labels": COMPONENT_LABELS,
            "screen_schema": {k: v.description for k, v in ScreenConfig.model_fields.items()},
            "email_configured": bool(st.smtp_host and st.alert_email_to),
            "weights_note": "Initial research weights, not empirically optimised. Changing them re-scores stocks from stored data."}


class ConfigUpdate(BaseModel):
    screen: ScreenConfig | None = None
    score: ScoreConfig | None = None
    scan_max_symbols: int | None = Field(None, ge=20, le=6000)
    rescore: bool = True


@app.put("/api/config")
def put_config(req: ConfigUpdate) -> dict[str, Any]:
    if req.score is not None:
        w = req.score.weights
        if any(v < 0 for v in w.values()) or sum(w.values()) <= 0:
            raise HTTPException(400, "weights must be non-negative and sum to more than zero")
        if not (req.score.sell < req.score.buy <= req.score.strong_buy):
            raise HTTPException(400, "thresholds must satisfy sell < buy <= strong_buy")
        unknown = set(w) - set(COMPONENT_LABELS)
        if unknown:
            raise HTTPException(400, f"unknown components: {sorted(unknown)}")
        kv_set("config:score", req.score.model_dump())
    if req.screen is not None:
        kv_set("config:screen", req.screen.model_dump())
    if req.scan_max_symbols is not None:
        kv_set("config:scan_max_symbols", req.scan_max_symbols)
    started = pipeline.start_scan_thread(fetch=False) if req.rescore else False
    return {"saved": True, "rescore_started": started}


# ---- live updates -------------------------------------------------------------------------------------
@app.get("/api/events")
async def events() -> StreamingResponse:
    async def gen():
        q = bus.subscribe()
        try:
            yield "retry: 5000\n\n"
            while True:
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=15.0)
                    yield sse_format(ev)
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            bus.unsubscribe(q)
    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/events/recent")
def events_recent(after: int = 0) -> list[dict[str, Any]]:
    """Polling fallback for clients without EventSource."""
    return [e for e in list(bus.recent) if e["id"] > after]

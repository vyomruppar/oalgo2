"""The research scan: listings -> liquidity ranking -> prices -> fundamentals -> panel -> screen ->
score -> signals -> regime -> backtests -> ML -> paper marks -> alerts. Runs in a background thread;
progress is published on the event bus and persisted on the ScanRun row."""
from __future__ import annotations

import json
import logging
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import select

from ..alerts import engine as alerts
from ..backtest.runner import run_all
from ..config import get_settings
from ..data.fred import Fred
from ..data.french import KenFrench
from ..data.http import ProviderError
from ..data.nasdaq_trader import NasdaqTrader
from ..data.sec import SecEdgar, norm_ticker, sic_to_sector
from ..data.validate import validate_prices
from ..data.yahoo import INDEX_SYMBOLS, YahooPrices, last_bar_age_days
from ..db import PaperPosition, PaperTrade, ScanRun, ScoreHistory, Security, StockResult, kv_get, kv_set, session, utcnow
from ..paper import ledger
from ..research import indicators as ind
from ..research import ml
from ..research.factors import FACTOR_DEFS, panel_factor_scores
from ..research.fundamentals import build_snapshots
from ..research.panel import build_matrices, build_panel, forward_returns, month_end_dates
from ..research.regime import breadth_series, current_regime
from ..research.scoring import ScoreConfig, score_universe
from ..research.signals import build_payload, classify, estimate_next_report, red_flags
from ..universe.screener import ScreenConfig, eligibility_mask, passes, screen_row
from .events import bus

log = logging.getLogger(__name__)
BENCHMARKS = ["SPY", "QQQ"]
_scan_lock = threading.Lock()


def get_screen_config() -> ScreenConfig:
    return ScreenConfig(**(kv_get("config:screen") or {}))


def get_score_config() -> ScoreConfig:
    return ScoreConfig(**(kv_get("config:score") or {}))


def is_running() -> bool:
    return _scan_lock.locked()


class Scan:
    def __init__(self, fetch: bool = True, max_symbols: int | None = None, force_research: bool = False):
        self.st = get_settings()
        self.fetch = fetch
        self.max_symbols = max_symbols or int(kv_get("config:scan_max_symbols", self.st.scan_max_symbols))
        self.force_research = force_research
        self.yahoo = YahooPrices()
        self.sec = SecEdgar()
        self.scan_id = 0
        self.stats: dict[str, Any] = {}

    # ---- progress -------------------------------------------------------------------------------------
    def stage(self, name: str, progress: float, **extra: Any) -> None:
        with session() as s:
            row = s.get(ScanRun, self.scan_id)
            row.stage, row.progress, row.stats = name, progress, dict(self.stats)
        bus.publish("scan_progress", {"scan_id": self.scan_id, "stage": name, "progress": round(progress, 3), "stats": self.stats, **extra})

    # ---- steps ----------------------------------------------------------------------------------------
    def refresh_listings(self) -> None:
        listings = NasdaqTrader().listings(ttl_seconds=12 * 3600 if self.fetch else None)
        try:
            tmap = self.sec.ticker_map()
        except ProviderError:
            tmap = {}
        seen = set()
        with session() as s:
            existing = {x.symbol: x for x in s.scalars(select(Security)).all()}
            for L in listings:
                sym = norm_ticker(L.symbol)
                if sym in seen:
                    continue
                seen.add(sym)
                row = existing.get(sym)
                if row is None:
                    row = Security(symbol=sym, name=L.name, exchange=L.exchange, listing_source=L.source, listing_as_of=L.as_of,
                                   security_type=L.security_type, eligible=L.eligible, exclusion_reason=L.exclusion_reason)
                    s.add(row)
                else:
                    row.name, row.exchange, row.listing_source, row.listing_as_of = L.name, L.exchange, L.source, L.as_of
                    row.security_type, row.eligible, row.exclusion_reason = L.security_type, L.eligible, L.exclusion_reason
                row.cik = tmap.get(sym) or row.cik
            for sym, row in existing.items():   # no longer in the exchange directory -> not verifiable -> ineligible
                if sym not in seen:
                    row.eligible, row.exclusion_reason = False, "no longer in the Nasdaq Trader NYSE/NASDAQ symbol directory"
        self.stats["listed"] = len(seen)
        self.stats["eligible_listings"] = sum(1 for L in listings if L.eligible)
        reasons: dict[str, int] = {}
        for L in listings:
            if not L.eligible:
                reasons[L.exclusion_reason or "other"] = reasons.get(L.exclusion_reason or "other", 0) + 1
        self.stats["listing_exclusions"] = dict(sorted(reasons.items(), key=lambda kv: -kv[1]))

    def rank_liquidity(self) -> list[str]:
        with session() as s:
            elig = [x.symbol for x in s.scalars(select(Security).where(Security.eligible.is_(True))).all()]
        if self.fetch:
            liq = self.yahoo.liquidity_snapshot(elig, progress=lambda f: self.stage("liquidity", 0.05 + 0.05 * f))
            with session() as s:
                for sym, v in liq.items():
                    row = s.get(Security, sym)
                    if row is not None:
                        row.last_price, row.avg_dollar_volume, row.liquidity_as_of = v["price"], v["avg_dollar_volume"], utcnow()
        with session() as s:
            rows = s.scalars(select(Security).where(Security.eligible.is_(True), Security.avg_dollar_volume.is_not(None))
                             .order_by(Security.avg_dollar_volume.desc())).all()
            ranked = [r.symbol for r in rows if (r.last_price or 0) >= 1.0]
            held = [p.symbol for p in s.scalars(select(PaperPosition)).all()]
            # stocks with a pending paper order must stay in the scan so the order can fill
            held += [t.symbol for t in s.scalars(select(PaperTrade).where(PaperTrade.status == "pending")).all() if t.symbol not in held]
        self.stats["liquidity_ranked"] = len(ranked)
        pick = ranked[: self.max_symbols]
        return pick + [h for h in held if h not in pick]

    def load_prices(self, symbols: list[str]) -> dict[str, pd.DataFrame]:
        out: dict[str, pd.DataFrame] = {}
        failures: dict[str, str] = {}

        def one(sym: str) -> tuple[str, pd.DataFrame | None, str | None]:
            try:
                if self.fetch:
                    return sym, self.yahoo.fetch(sym), None
                return sym, self.yahoo.load(sym), None
            except Exception as e:  # provider failure for one symbol must not abort the scan
                cached = self.yahoo.load(sym)
                return sym, cached, f"{type(e).__name__}: {e}"

        with ThreadPoolExecutor(4) as ex:
            for k, (sym, df, err) in enumerate(ex.map(one, symbols)):
                if df is not None and len(df):
                    out[sym] = df
                if err:
                    failures[sym] = err
                if k % 20 == 0:
                    self.stage("prices", 0.10 + 0.25 * k / max(len(symbols), 1), symbol=sym)
        self.stats["price_failures"] = len(failures)
        self.price_failures = failures
        return out

    def load_fundamentals(self, symbols: list[str]) -> tuple[dict[str, pd.DataFrame], dict[str, list[dict[str, Any]]]]:
        snaps: dict[str, pd.DataFrame] = {}
        filings: dict[str, list[dict[str, Any]]] = {}
        with session() as s:
            ciks = {x.symbol: x.cik for x in s.scalars(select(Security).where(Security.symbol.in_(symbols))).all()}
        fdir = self.st.fundamentals_dir
        meta_updates: dict[str, tuple[str | None, str | None]] = {}
        fails = 0

        def one(sym: str) -> tuple[str, pd.DataFrame | None, list[dict[str, Any]] | None, tuple | None, bool]:
            cik = ciks.get(sym)
            pq, fj = fdir / f"{sym}.parquet", fdir / f"{sym}.filings.json"
            if not cik:
                return sym, None, None, None, False
            try:
                if self.fetch:
                    prof = self.sec.profile(cik)
                    fl = [f for f in prof.filings if f["form"] in ("10-K", "10-Q", "8-K", "10-K/A", "10-Q/A", "20-F", "6-K", "DEF 14A", "4")][:120]
                    fj.write_text(json.dumps({"sic": prof.sic, "industry": prof.industry, "filings": fl}))
                    snap = build_snapshots(self.sec.company_facts(cik))
                    if not snap.empty:
                        snap.to_parquet(pq)
                    elif pq.exists():
                        pq.unlink()
                    return sym, snap, fl, (prof.sic, prof.industry), False
            except Exception as e:
                log.warning("fundamentals failed for %s: %s", sym, e)
                failed = True
            else:
                failed = False
            snap = pd.read_parquet(pq) if pq.exists() else None
            meta = json.loads(fj.read_text()) if fj.exists() else None
            return sym, snap, (meta or {}).get("filings"), ((meta or {}).get("sic"), (meta or {}).get("industry")) if meta else None, failed

        with ThreadPoolExecutor(4) as ex:
            for k, (sym, snap, fl, meta, failed) in enumerate(ex.map(one, symbols)):
                if snap is not None and not snap.empty:
                    snaps[sym] = snap
                if fl is not None:
                    filings[sym] = fl
                if meta:
                    meta_updates[sym] = meta
                fails += int(failed)
                if k % 20 == 0:
                    self.stage("fundamentals", 0.35 + 0.25 * k / max(len(symbols), 1), symbol=sym)
        with session() as s:
            for sym, (sic, industry) in meta_updates.items():
                row = s.get(Security, sym)
                if row is not None:
                    row.sic, row.industry, row.sector = sic, industry, sic_to_sector(sic)
        self.stats["fundamentals_failures"] = fails
        self.stats["with_fundamentals"] = len(snaps)
        return snaps, filings

    # ---- main -----------------------------------------------------------------------------------------
    def run(self) -> int:
        with session() as s:
            row = ScanRun(status="running", stage="starting", progress=0.0, stats={})
            s.add(row)
            s.flush()
            self.scan_id = row.id
        bus.publish("scan_started", {"scan_id": self.scan_id})
        try:
            self._run()
            with session() as s:
                row = s.get(ScanRun, self.scan_id)
                row.status, row.stage, row.progress, row.finished_at, row.stats = "ok", "complete", 1.0, utcnow(), dict(self.stats)
            bus.publish("scan_finished", {"scan_id": self.scan_id, "status": "ok", "stats": self.stats})
        except Exception as e:
            log.exception("scan failed")
            with session() as s:
                row = s.get(ScanRun, self.scan_id)
                row.status, row.finished_at, row.error, row.stats = "failed", utcnow(), f"{e}\n{traceback.format_exc()[-1500:]}", dict(self.stats)
            alerts.emit("scan_failure", None, "Scan failed", str(e)[:400], {"scan": self.scan_id}, "critical")
            bus.publish("scan_finished", {"scan_id": self.scan_id, "status": "failed", "error": str(e)})
        finally:
            try:
                alerts.evaluate_providers()
            except Exception:
                log.exception("provider alert evaluation failed")
        return self.scan_id

    def _run(self) -> None:
        self.stage("listings", 0.02)
        self.refresh_listings()
        self.stage("liquidity", 0.05)
        symbols = self.rank_liquidity()
        if not symbols:
            raise RuntimeError("no eligible symbols with liquidity data; check the Yahoo provider")
        self.stats["scanned"] = len(symbols)
        self.stage("prices", 0.10)
        aux = BENCHMARKS + list(INDEX_SYMBOLS.values())
        prices_all = self.load_prices(symbols + aux)
        bench = {b: prices_all.pop(b)["adj_close"] for b in BENCHMARKS if b in prices_all}
        idx = {k: prices_all.pop(v) for k, v in INDEX_SYMBOLS.items() if v in prices_all}
        prices = prices_all
        if "SP500" not in idx or not prices:
            raise RuntimeError("index or stock price data unavailable")
        self.stage("fundamentals", 0.35)
        snaps, filings = self.load_fundamentals(list(prices))
        self.stage("panel", 0.62)
        with session() as s:
            secs = {x.symbol: {"name": x.name, "exchange": x.exchange, "sector": x.sector or "Unknown", "industry": x.industry,
                               "listing_source": x.listing_source, "listing_as_of": x.listing_as_of.isoformat() if x.listing_as_of else None}
                    for x in s.scalars(select(Security).where(Security.symbol.in_(list(prices)))).all()}
            held = {p.symbol: p.avg_cost for p in s.scalars(select(PaperPosition)).all()}
        sectors = {k: v["sector"] for k, v in secs.items()}
        calendar = idx["SP500"].index
        pm = build_matrices(prices, calendar)
        dates = month_end_dates(calendar)
        panel = build_panel(pm, snaps, dates, sectors)
        last = dates[-1]
        cross = panel.xs(last, level="date").copy()
        screen_cfg, score_cfg = get_screen_config(), get_score_config()
        # ---- regime / breadth / market summaries ----------------------------------------------------
        vix = idx["VIX"]["close"] if "VIX" in idx else None
        breadth = breadth_series(pm.close, pm.adj)
        regime = current_regime(idx["SP500"]["close"], vix, breadth)
        old_regime = kv_get("regime")
        kv_set("regime", regime)
        kv_set("market:breadth", {"as_of": str(last.date()), "universe": f"{len(prices)} scanned stocks",
                                  "series": [[d.date().isoformat(), *[None if not np.isfinite(x) else round(float(x), 2) for x in r]]
                                             for d, r in zip(breadth.index[-756:], breadth[["pct_above_50", "pct_above_200", "ad_line", "new_highs", "new_lows"]].to_numpy()[-756:])],
                                  "columns": ["pct_above_50", "pct_above_200", "ad_line", "new_highs", "new_lows"]})
        kv_set("market:sectors", self._sector_performance(pm, sectors, bench.get("SPY")))
        # ---- per-stock indicators, screen, score ------------------------------------------------------
        self.stage("screening", 0.68)
        extra, atr, issues, ages = {}, {}, {}, {}
        for sym, df in prices.items():
            iv = ind.compute_all(df).iloc[-1]
            extra[sym] = {"macd_hist": iv["macd_hist"], "rsi_14": iv["rsi_14"]}
            atr[sym] = float(iv["atr_14"]) if np.isfinite(iv["atr_14"]) else None
            issues[sym] = validate_prices(df)
            ages[sym] = last_bar_age_days(df)
        cross = cross.join(pd.DataFrame(extra).T.astype(float))
        screen = {sym: screen_row(cross.loc[sym], screen_cfg, issues.get(sym), ages.get(sym)) for sym in cross.index if sym in prices}
        passed = [s for s, d in screen.items() if passes(d)]
        self.stats.update({"passed": len(passed), "failed": len(screen) - len(passed)})
        fail_reasons: dict[str, int] = {}
        for d in screen.values():
            for r in d:
                if not r["passed"]:
                    fail_reasons[r["rule"]] = fail_reasons.get(r["rule"], 0) + 1
        self.stats["screen_fail_reasons"] = dict(sorted(fail_reasons.items(), key=lambda kv: -kv[1]))
        # ---- research: backtests + ML (cached; refreshed daily or on demand) --------------------------
        bt = kv_get("backtests")
        mlrep = kv_get("ml:report")
        stale = self.force_research or bt is None or mlrep is None or \
            (pd.Timestamp.now(tz="UTC") - pd.Timestamp(bt["generated_at"])) > timedelta(hours=20) or bt["config"].get("screen") != screen_cfg.model_dump()
        ml_rank = None
        elig = eligibility_mask(panel, screen_cfg)
        factors_hist = panel_factor_scores(panel, elig)
        if stale:
            self.stage("backtests", 0.72)
            rf = None
            try:
                ff = KenFrench().factors()
                rf = ff["RF"]
                kv_set("french:as_of", str(ff.index[-1].date()))
            except Exception as e:
                log.warning("Ken French factors unavailable: %s", e)
            try:
                bt = run_all(pm, panel, screen_cfg, bench, idx["SP500"]["close"], vix, rf, top_n=min(30, max(10, len(passed) // 5)),
                             progress=lambda name, p: self.stage(name, 0.72 + 0.13 * p))
                bt["config"]["screen"] = screen_cfg.model_dump()
                kv_set("backtests", bt)
                self.stats["backtests"] = "ok"
            except Exception as e:
                log.exception("backtests failed")
                self.stats["backtests"] = f"failed: {e}"
            self.stage("machine_learning", 0.86)
            try:
                fwd = forward_returns(pm, dates, 21)
                mlrep, ml_rank = ml.train_and_report(factors_hist, fwd)
                kv_set("ml:report", mlrep)
                kv_set("ml:rank", ml_rank.to_dict() if ml_rank is not None else None)
                self.stats["ml"] = mlrep.get("status")
            except Exception as e:
                log.exception("ML training failed")
                self.stats["ml"] = f"failed: {e}"
            try:
                kv_set("factors:research", self._factor_research(panel, factors_hist, pm, dates))
            except Exception:
                log.exception("factor research failed")
            try:
                kv_set("macro", self._macro())
            except Exception as e:
                log.warning("macro series unavailable: %s", e)
        else:
            r = kv_get("ml:rank")
            ml_rank = pd.Series(r) if r else None
        # ---- scoring ----------------------------------------------------------------------------------
        self.stage("scoring", 0.90)
        scored = score_universe(cross.loc[passed], score_cfg, regime["regime"], ml_rank) if len(passed) >= 10 else pd.DataFrame()
        perf = None
        if bt and "multifactor" in bt.get("results", {}):
            m = bt["results"]["multifactor"]
            perf = {"label": "backtested", "strategy": "Multifactor composite (top-N, monthly, after costs)",
                    "cagr": m["metrics"].get("cagr"), "sharpe": m["metrics"].get("sharpe"), "max_drawdown": m["metrics"].get("max_drawdown"),
                    "excess_cagr_vs_spy": m["metrics"].get("excess_cagr"),
                    "excess_cagr_vs_universe": (m.get("vs_universe") or {}).get("excess_cagr"),
                    "out_of_sample_excess_cagr_vs_universe": ((m.get("vs_universe") or {}).get("segments") or {}).get("out_of_sample"),
                    "validation_status": m["validation_status"]["status"], "period": [m["metrics"].get("start"), m["metrics"].get("end")],
                    "caveat": "Backtest of the factor portion of the score on today's liquid, surviving stocks: overstated by survivorship bias."}
        now = utcnow()
        counts: dict[str, int] = {}
        with session() as s:
            old_rows = {r.symbol: r for r in s.scalars(select(StockResult)).all()}
            first_scan = len(old_rows) == 0
            old_payloads = {k: dict(v.payload or {}) for k, v in old_rows.items()}
            for sym in screen:
                df = prices[sym]
                row = cross.loc[sym].copy()
                pdate = df.index[-1].date().isoformat()
                fl = filings.get(sym) or []
                latest_periodic = next((f for f in fl if f["form"] in ("10-K", "10-Q", "8-K")), None)
                base = {"symbol": sym, "company": secs.get(sym, {}).get("name"), "exchange": secs.get(sym, {}).get("exchange"),
                        "sector": sectors.get(sym), "price": float(row["price"]) if np.isfinite(row["price"]) else None, "price_date": pdate,
                        "latest_filing": latest_periodic, "screen": screen[sym]}
                sig, score, dq = None, None, None
                if sym in scored.index:
                    srow = pd.concat([row, scored.loc[sym]])
                    flags = red_flags(srow, [i for i in issues[sym] if i["code"] != "stale"])
                    sig, gates = classify(srow, score_cfg, regime["regime"], flags)
                    snap = snaps.get(sym)
                    src = [{"name": "Nasdaq Trader symbol directory", "as_of": secs[sym]["listing_as_of"], "use": "exchange verification"},
                           {"name": "Yahoo Finance chart (unofficial, end-of-day)", "as_of": pdate, "use": "prices, dividends, splits"}]
                    if snap is not None and len(snap):
                        usable = snap[snap.index < last]
                        if len(usable):
                            src.append({"name": "SEC EDGAR XBRL company facts", "as_of": usable.index[-1].date().isoformat(), "use": "fundamentals (filing date)"})
                    payload = build_payload(sym, secs.get(sym, {}), srow, score_cfg, regime, flags, sig, gates, atr.get(sym), perf,
                                            estimate_next_report(fl, pdate), pdate, src)
                    payload.update({"screen": screen[sym], "latest_filing": latest_periodic})
                    score, dq = payload["score"], payload["data_quality"]
                else:
                    payload = dict(base)
                    payload["signal"] = None
                    payload["reasons"] = ["Did not pass the screener" if not passes(screen[sym]) else "Too few passing stocks to rank"]
                sigma_d = float(row["vol_63"]) / np.sqrt(252) if np.isfinite(row.get("vol_63", np.nan)) else None
                r1 = float(row["ret_1d"]) if np.isfinite(row.get("ret_1d", np.nan)) else None
                payload["unusual"] = {
                    "volume_ratio": float(row["vol_ratio_20"]) if np.isfinite(row.get("vol_ratio_20", np.nan)) else None,
                    "ret_1d": r1, "move_sigma": (r1 / sigma_d) if r1 is not None and sigma_d else None,
                    "below_200": bool(row["price"] < row["sma_200"]) if np.isfinite(row.get("sma_200", np.nan)) else None,
                    "entry_stop": (held[sym] - 2.5 * atr[sym]) if sym in held and atr.get(sym) else None}
                oldp = old_payloads.get(sym)
                if oldp and latest_periodic and (oldp.get("latest_filing") or {}).get("accession") not in (None, latest_periodic["accession"]):
                    payload["new_filing"] = latest_periodic
                payload = _clean(payload)
                counts[sig or "SCREENED_OUT"] = counts.get(sig or "SCREENED_OUT", 0) + 1
                res = old_rows.get(sym)
                if res is None:
                    res = StockResult(symbol=sym, scan_id=self.scan_id, as_of=now)
                    s.add(res)
                res.scan_id, res.as_of, res.price_date, res.price = self.scan_id, now, pdate, payload.get("price")
                res.screen_pass, res.screen_detail = passes(screen[sym]), screen[sym]
                res.score, res.signal, res.data_quality, res.payload = score, sig, dq, payload
                if score is not None:
                    s.add(ScoreHistory(symbol=sym, scan_id=self.scan_id, as_of=now, score=score, signal=sig))
            for sym, res in old_rows.items():   # dropped out of the scanned set
                if sym not in screen:
                    s.delete(res)
            new_payloads = {sym: s.get(StockResult, sym).payload for sym in screen}
        self.stats["signals"] = counts
        self.stats["price_as_of"] = str(last.date())
        # ---- paper ledger marks and alerts --------------------------------------------------------------
        self.stage("alerts", 0.96)
        try:
            ledger.process(self.yahoo.load, idx["SP500"]["close"] if "SP500" in idx else None)
        except Exception:
            log.exception("paper ledger processing failed")
        n_alerts = 0
        for sym, p in new_payloads.items():
            n_alerts += len(alerts.evaluate_stock(sym, old_payloads.get(sym), p, score_cfg.score_change_alert, first_scan, sym in held))
        if alerts.evaluate_regime(old_regime, regime):
            n_alerts += 1
        self.stats["alerts_generated"] = n_alerts

    # ---- research summaries -------------------------------------------------------------------------
    @staticmethod
    def _sector_performance(pm, sectors: dict[str, str], spy: pd.Series | None) -> dict[str, Any]:
        adj = pm.adj
        out = []
        horizons = {"1d": 1, "1w": 5, "1m": 21, "3m": 63, "6m": 126, "1y": 252}
        sp = spy.reindex(adj.index).ffill() if spy is not None else None
        for sec in sorted(set(sectors.values())):
            cols = [s for s in adj.columns if sectors.get(s) == sec]
            if len(cols) < 3:
                continue
            row: dict[str, Any] = {"sector": sec, "n": len(cols)}
            for k, h in horizons.items():
                r = (adj[cols].iloc[-1] / adj[cols].shift(h).iloc[-1] - 1).dropna()
                row[k] = float(r.mean()) if len(r) else None
                if sp is not None and row[k] is not None:
                    row[f"rs_{k}"] = row[k] - float(sp.iloc[-1] / sp.shift(h).iloc[-1] - 1)
            out.append(row)
        return {"as_of": str(adj.index[-1].date()), "method": "equal-weight average return of scanned stocks per SIC-based sector; rs_* = minus SPY",
                "sectors": out}

    @staticmethod
    def _factor_research(panel: pd.DataFrame, factors: pd.DataFrame, pm, dates: pd.DatetimeIndex) -> dict[str, Any]:
        names = list(FACTOR_DEFS)
        fwd = forward_returns(pm, dates, 21)
        df = factors[names].join(fwd, how="inner").dropna(subset=["fwd_21"])
        ic = {}
        for n in names:
            series = df.groupby(level="date").apply(lambda g: g[n].corr(g["fwd_21"], method="spearman") if g[n].notna().sum() >= 20 else np.nan).dropna()
            t = float(series.mean() / series.std(ddof=1) * np.sqrt(len(series))) if len(series) > 2 and series.std(ddof=1) > 0 else None
            ic[n] = {"mean": float(series.mean()) if len(series) else None, "t_stat": t, "hit_rate": float((series > 0).mean()) if len(series) else None,
                     "n_months": int(len(series)), "series": [[d.date().isoformat(), round(float(v), 4)] for d, v in series.items()]}
        last = factors.index.get_level_values("date").max()
        cur = factors.xs(last, level="date")[names]
        return {"label": "backtested (information coefficients on historical data; survivorship-biased universe)",
                "as_of": str(last.date()), "factors": names,
                "definitions": {k: [f"{'+' if sgn > 0 else '-'}{c}" for c, sgn in v] for k, v in FACTOR_DEFS.items()},
                "ic": ic, "correlation": cur.corr(method="spearman").round(3).fillna(0).values.tolist(),
                "ic_note": "Rank IC = Spearman correlation between the factor z-score and the next 21-day return (entered at the next open), by month."}

    @staticmethod
    def _macro() -> dict[str, Any]:
        fred = Fred()
        out = {}
        for sid in ("DGS10", "DGS3MO", "T10Y2Y"):
            s = fred.series(sid).tail(756)
            out[sid] = {"last": float(s.iloc[-1]), "as_of": s.index[-1].date().isoformat(),
                        "series": [[d.date().isoformat(), float(v)] for d, v in s.items()]}
        return {"source": "FRED (Federal Reserve Bank of St. Louis)", "series": out}


def _clean(o: Any) -> Any:
    """Make a payload JSON-safe: NaN/inf -> None, numpy scalars -> Python, timestamps -> ISO strings."""
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, (np.floating, float)):
        return None if not np.isfinite(o) else float(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, (pd.Timestamp,)):
        return o.isoformat()
    if o is pd.NaT:
        return None
    return o


def run_scan(fetch: bool = True, max_symbols: int | None = None, force_research: bool = False) -> int | None:
    """Run one scan unless another is in progress. Returns the scan id, or None if skipped."""
    if not _scan_lock.acquire(blocking=False):
        return None
    try:
        return Scan(fetch, max_symbols, force_research).run()
    finally:
        _scan_lock.release()


def start_scan_thread(fetch: bool = True, max_symbols: int | None = None, force_research: bool = False) -> bool:
    if is_running():
        return False
    threading.Thread(target=run_scan, args=(fetch, max_symbols, force_research), daemon=True, name="scan").start()
    return True

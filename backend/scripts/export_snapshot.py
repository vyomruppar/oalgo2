"""Export a read-only data snapshot for the static (artifact) build of the dashboard.

Calls the API in-process against the current data directory and writes one JSON file per view.
No network access and no changes to stored data. Usage:
    uv run --inexact python scripts/export_snapshot.py ../frontend/snapshot/dist/data
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

os.environ.setdefault("OALGO_SCHEDULER_ENABLED", "false")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app.api.main import app  # noqa: E402
from app.portfolio import holdings  # noqa: E402
from app.research import news_service, sentiment  # noqa: E402


def compact(o: Any) -> Any:
    """Round floats so the files stay small; values keep more precision than any chart or table shows."""
    if isinstance(o, float):
        a = abs(o)
        return round(o, 2) if a >= 1000 else round(o, 4) if a >= 1 else round(o, 6)
    if isinstance(o, dict):
        return {k: compact(v) for k, v in o.items()}
    if isinstance(o, list):
        return [compact(v) for v in o]
    return o


def main(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "stock").mkdir(exist_ok=True)
    sizes: dict[str, int] = {}

    def write(name: str, data: Any) -> None:
        p = out / name
        p.write_text(json.dumps(compact(data), separators=(",", ":"), default=str))
        sizes[name] = p.stat().st_size

    with TestClient(app) as c:
        def get(path: str, **params: Any) -> Any:
            r = c.get(path, params=params)
            r.raise_for_status()
            return r.json()

        simple = {"overview": "/api/overview", "dashboard": "/api/dashboard", "holdings": "/api/holdings", "holdings-risk": "/api/holdings/risk",
                  "strategies": "/api/strategies", "factors": "/api/factors", "ml": "/api/ml", "market-summary": "/api/market/summary",
                  "mean-reversion": "/api/lab/mean-reversion", "config": "/api/config", "providers": "/api/providers", "scans": "/api/scans",
                  "paper": "/api/portfolio", "paper-risk": "/api/portfolio/risk"}
        for name, path in simple.items():
            write(f"{name}.json", get(path))
        write("alerts.json", get("/api/alerts", limit=300))
        for r in ("1m", "3m", "6m", "1y", "2y", "all"):
            write(f"holdings-history-{r}.json", get("/api/holdings/history", range=r))
        for r in ("3m", "6m", "1y", "2y", "5y", "max"):
            write(f"indexes-{r}.json", get("/api/market/indexes", range=r))
        for y in (2, 5, 10):
            write(f"regime-{y}.json", get("/api/lab/regime-history", years=y))
        strat = get("/api/strategies")
        if strat.get("available"):
            keys = list(strat["results"]) + list(strat["benchmarks"])
            write("curves.json", get("/api/strategies/curves", keys=",".join(keys)))
        stocks = get("/api/stocks", limit=1000)
        write("stocks.json", stocks)
        items = news_service.items_for(None, limit=5000)
        write("news.json", {"engine": sentiment.engine_status(), "items": news_service.public(items),
                            "sentiment": news_service.sentiment_by_symbol(None), "holdings": holdings.symbols(),
                            "source": "Yahoo Finance search endpoint (unofficial); headlines only"})
        n = 0
        for row in stocks["items"]:
            sym = row["symbol"]
            try:
                bundle = {"detail": get(f"/api/stocks/{sym}"), "prices": get(f"/api/stocks/{sym}/prices", range="2y"),
                          "fundamentals": get(f"/api/stocks/{sym}/fundamentals")}
            except Exception as e:  # a stock without stored prices still gets its research page
                print("skip prices for", sym, e)
                bundle = {"detail": get(f"/api/stocks/{sym}"), "prices": None, "fundamentals": get(f"/api/stocks/{sym}/fundamentals")}
            write(f"stock/{sym}.json", bundle)
            n += 1
        ov = get("/api/overview")
        last = (ov.get("scan") or {}).get("last_success") or {}
        write("meta.json", {"snapshot_at": last.get("finished_at"), "price_as_of": (last.get("stats") or {}).get("price_as_of"),
                            "stocks": n, "note": "Read-only snapshot. Holdings shown are sample data."})
    total = sum(sizes.values())
    big = sorted(sizes.items(), key=lambda kv: -kv[1])[:6]
    print(f"{len(sizes)} files, {total / 1e6:.1f} MB; largest: " + ", ".join(f"{k} {v / 1e3:.0f}KB" for k, v in big))


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "../frontend/snapshot/dist/data"))

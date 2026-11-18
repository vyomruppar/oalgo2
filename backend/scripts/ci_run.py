"""One update cycle of the free hosted deployment (run by .github/workflows/update.yml).

1. Replay queued dashboard changes (decrypted from the queue directory), in order.
2. Run a full scan when scheduled or when someone pressed "Run scan now"; otherwise re-score from
   stored data if settings changed.
3. Refresh headlines for the stocks owned.
4. Export the read-only data files the dashboard serves.

Prints only counts: the repository and its logs are public, so nothing about holdings is logged.
Details of each change (applied or rejected, with the reason) go to ops-log.json, which is published
behind the dashboard password.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("OALGO_SCHEDULER_ENABLED", "false")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
logging.basicConfig(level=logging.ERROR)
for noisy in ("httpx", "app", "apscheduler", "transformers"):
    logging.getLogger(noisy).setLevel(logging.ERROR)

from fastapi.testclient import TestClient  # noqa: E402

from app import queue  # noqa: E402
from app.api.main import app  # noqa: E402
from app.jobs import pipeline  # noqa: E402
from app.portfolio import holdings  # noqa: E402
from app.research import news_service  # noqa: E402


def describe(op: dict) -> str:
    m, p = op.get("method"), op.get("path", "")
    body = op.get("body") or {}
    if p == "/api/scans":
        return "Run a scan"
    if p == "/api/holdings" and m == "POST":
        return f"Add {str(body.get('symbol', '')).upper()} holding"
    if p.startswith("/api/holdings/") and m == "PUT":
        return "Edit a holding"
    if p.startswith("/api/holdings/") and m == "DELETE":
        return "Remove a holding"
    if p == "/api/holdings/import":
        return "Import holdings"
    if p == "/api/config":
        return "Save settings"
    if p.startswith("/api/news/refresh"):
        return "Fetch headlines"
    return f"{m} {p}"


def wait_for_scan(timeout: float = 3600) -> None:
    t = time.time()
    time.sleep(0.5)
    while pipeline.is_running() and time.time() - t < timeout:
        time.sleep(2)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--queue", type=Path, required=True, help="directory of encrypted change files")
    ap.add_argument("--out", type=Path, required=True, help="where to write the exported data files")
    ap.add_argument("--scheduled", action="store_true", help="always run a full scan")
    args = ap.parse_args()

    key = queue.derive(os.environ["OALGO_SECRET"], queue.QUEUE_PURPOSE)
    files = sorted(args.queue.glob("*.enc")) if args.queue.exists() else []
    log_path = args.out / "ops-log.json"
    previous = []
    prior = Path(os.environ.get("OALGO_DATA_DIR", "data")) / "ops-log.json"
    if prior.exists():
        previous = json.loads(prior.read_text())

    entries, want_scan, want_rescore, processed = [], args.scheduled, False, []
    already = {e.get("file") for e in previous}
    with TestClient(app) as c:
        for f in files:
            processed.append(f.name)
            if f.name in already:  # applied by an earlier run whose clean-up did not finish
                continue
            entry = {"file": f.name, "at": datetime.now(timezone.utc).isoformat()}
            try:
                op = queue.decrypt(f.read_text(), key)
                entry.update({"queued_at": op.get("ts"), "what": describe(op)})
                method, path, body = op["method"], op["path"], op.get("body")
                if not queue.allowed(method, path):
                    raise ValueError("this kind of change is not allowed")
                if path == "/api/scans":
                    want_scan, entry["status"] = True, "applied"
                elif path == "/api/config":
                    body = {**(body or {}), "rescore": False}
                    r = c.request(method, path, json=body)
                    r.raise_for_status()
                    want_rescore, entry["status"] = True, "applied"
                else:
                    r = c.request(method, path, json=body)
                    if r.status_code >= 400:
                        entry.update({"status": "rejected", "reason": r.json().get("detail", r.text)})
                    else:
                        entry["status"] = "applied"
            except Exception as e:  # a bad file must not stop the update
                entry.update({"status": "rejected", "reason": f"{type(e).__name__}: {e}"[:300]})
            entries.append(entry)

        if want_scan:
            pipeline.run_scan(fetch=True)
        elif want_rescore:
            pipeline.run_scan(fetch=False)
        wait_for_scan()

        owned = holdings.symbols()
        if owned:
            from app.db import Security, session
            with session() as s:
                names = {x.symbol: x.name for x in s.query(Security).filter(Security.symbol.in_(owned)).all()}
            try:
                news_service.refresh(names, ttl_seconds=600)
            except Exception:
                pass

    log = (entries + previous)[:100]
    prior.parent.mkdir(parents=True, exist_ok=True)
    prior.write_text(json.dumps(log))

    from scripts.export_snapshot import main as export
    export(args.out)
    log_path.write_text(json.dumps({"updated_at": datetime.now(timezone.utc).isoformat(), "entries": log}))
    (args.out / "processed.txt").write_text("\n".join(processed))
    applied = sum(e.get("status") == "applied" for e in entries)
    print(f"changes: {len(entries)} ({applied} applied, {len(entries) - applied} rejected); "
          f"full scan: {'yes' if want_scan else 'no'}; re-score: {'yes' if want_rescore and not want_scan else 'no'}")


if __name__ == "__main__":
    main()

import json
import sys
from pathlib import Path

import pytest

from app import queue

SECRET = "s" * 40


def test_encrypt_roundtrip_and_tamper_detection():
    key = queue.derive(SECRET, queue.QUEUE_PURPOSE)
    blob = queue.encrypt({"method": "POST", "path": "/api/scans"}, key)
    assert queue.decrypt(blob, key) == {"method": "POST", "path": "/api/scans"}
    assert "scans" not in blob                                   # nothing readable in the public queue file
    with pytest.raises(Exception):
        queue.decrypt(blob, queue.derive("t" * 40, queue.QUEUE_PURPOSE))
    raw = bytearray(__import__("base64").b64decode(blob))
    raw[20] ^= 1
    with pytest.raises(Exception):
        queue.decrypt(__import__("base64").b64encode(bytes(raw)).decode(), key)
    with pytest.raises(ValueError):
        queue.derive("short", queue.QUEUE_PURPOSE)


def test_decrypts_a_message_written_by_the_dashboard():
    # produced by frontend/lib/ops.ts encryptOp() with OALGO_SECRET = "s" * 40 (see frontend/tests/ops.test.ts)
    blob = Path(__file__).with_name("fixtures").joinpath("queue_from_node.txt").read_text()
    op = queue.decrypt(blob, queue.derive(SECRET, queue.QUEUE_PURPOSE))
    assert op["method"] == "POST" and op["path"] == "/api/holdings" and op["body"]["symbol"] == "AAPL"


def test_only_known_changes_are_allowed():
    assert queue.allowed("POST", "/api/scans")
    assert queue.allowed("DELETE", "/api/holdings/12")
    assert queue.allowed("POST", "/api/news/refresh?symbol=BRK-B")
    assert not queue.allowed("POST", "/api/portfolio/orders")       # paper trading is off in the free setup
    assert not queue.allowed("POST", "/api/portfolio/reset")
    assert not queue.allowed("GET", "/api/holdings")
    assert not queue.allowed("PUT", "/api/holdings/1/../../x")


def test_ci_run_replays_queue_in_order_and_logs_without_leaking(tmp_env, tmp_path, monkeypatch, capsys):
    from app.data.yahoo import YahooPrices
    from app.db import Security, session, utcnow
    from app.jobs import pipeline
    from app.research import news_service
    from tests.conftest import make_prices

    with session() as s:
        s.add(Security(symbol="AAA", name="Aaa Corp Common Stock", exchange="NYSE", listing_source="x", listing_as_of=utcnow(),
                       security_type="common", eligible=True, sector="Technology"))
    make_prices(300, seed=1, start="2025-09-01").to_parquet(YahooPrices().path("AAA"))
    make_prices(300, seed=2, start="2025-09-01").to_parquet(YahooPrices().path("SPY"))
    scans = []
    monkeypatch.setattr(pipeline, "run_scan", lambda fetch=True, **k: scans.append(fetch))
    monkeypatch.setattr(news_service, "refresh", lambda names, ttl_seconds=0: {"new": 0})
    monkeypatch.setenv("OALGO_SECRET", SECRET)

    key = queue.derive(SECRET, queue.QUEUE_PURPOSE)
    qdir = tmp_path / "queue"
    qdir.mkdir()
    ops = [
        {"method": "POST", "path": "/api/holdings", "body": {"symbol": "AAA", "shares": 10, "cost": 50, "purchase_date": "2025-10-01"}},
        {"method": "POST", "path": "/api/holdings", "body": {"symbol": "ZZZZ", "shares": 1, "cost": 1, "purchase_date": "2025-10-01"}},
        {"method": "POST", "path": "/api/portfolio/reset"},
        {"method": "PUT", "path": "/api/config", "body": {"scan_max_symbols": 120}},
    ]
    for i, op in enumerate(ops):
        (qdir / f"{1000 + i}-x.enc").write_text(queue.encrypt({**op, "ts": "2026-11-18T00:00:00Z"}, key))
    (qdir / "1999-bad.enc").write_text("not encrypted")

    out = tmp_path / "out"
    sys.argv = ["ci_run", "--queue", str(qdir), "--out", str(out)]
    from scripts import ci_run
    ci_run.main()

    log = json.loads((out / "ops-log.json").read_text())["entries"]
    assert [e["status"] for e in log] == ["applied", "rejected", "rejected", "applied", "rejected"]
    assert "not in the verified" in log[1]["reason"] and "not allowed" in log[2]["reason"]
    assert scans == [False]                                          # settings changed -> re-score from stored data
    from app.portfolio import holdings
    assert holdings.symbols() == ["AAA"]
    from app.api.main import get_config
    assert get_config()["scan_max_symbols"] == 120
    assert (out / "holdings.json").exists() and (out / "listings.json").exists() and (out / "meta.json").exists()
    assert json.loads((out / "listings.json").read_text()) == [["AAA", "Aaa Corp Common Stock"]]
    assert (out / "processed.txt").read_text().split() == sorted(p.name for p in qdir.glob("*.enc"))
    printed = capsys.readouterr().out
    assert "AAA" not in printed and "ZZZZ" not in printed            # public CI log carries counts only
    assert "5 (2 applied, 3 rejected)" in printed

    sys.argv = ["ci_run", "--queue", str(tmp_path / "none"), "--out", str(out), "--scheduled"]
    ci_run.main()
    assert scans == [False, True]                                    # scheduled run always scans
    assert len(json.loads((out / "ops-log.json").read_text())["entries"]) == 5   # history kept

    # if clearing the queue failed, the same files come back: they must not be applied twice
    sys.argv = ["ci_run", "--queue", str(qdir), "--out", str(out)]
    ci_run.main()
    assert holdings.symbols() == ["AAA"] and len(holdings.lots()) == 1
    assert len(json.loads((out / "ops-log.json").read_text())["entries"]) == 5


def test_compact_keeps_six_significant_digits():
    from scripts.export_snapshot import compact
    assert compact({"a": [123456.789, 0.000123456789, 352.78341, -1.23456789]}) == {"a": [123457.0, 0.000123457, 352.783, -1.23457]}
    assert compact(float("nan")) is None

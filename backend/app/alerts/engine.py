"""Alert generation with deduplication.

An alert is stored only when its (kind, symbol) state changes: the same condition observed on
consecutive scans does not notify again. A cooldown re-arms long-lived conditions after 7 days.
"""
from __future__ import annotations

import hashlib
import json
import logging
import smtplib
from datetime import timedelta
from email.message import EmailMessage
from typing import Any

from sqlalchemy import select

from ..config import get_settings
from ..db import Alert, ProviderHealth, session, utcnow
from ..jobs.events import bus

log = logging.getLogger(__name__)
COOLDOWN = timedelta(days=7)
ACTIONABLE = {"STRONG BUY", "BUY"}


def state_hash(state: Any) -> str:
    return hashlib.sha256(json.dumps(state, sort_keys=True, default=str).encode()).hexdigest()[:32]


def emit(kind: str, symbol: str | None, title: str, message: str, state: Any, severity: str = "info",
         payload: dict[str, Any] | None = None, notify: bool = True, key: str | None = None) -> int | None:
    """Store an alert unless the latest alert with the same dedup key has the same state (within cooldown)."""
    key = key or f"{kind}:{symbol or '-'}"
    h = state_hash(state)
    with session() as s:
        last = s.scalars(select(Alert).where(Alert.dedup_key == key).order_by(Alert.id.desc()).limit(1)).first()
        if last is not None and last.state_hash == h:
            created = last.created_at if last.created_at.tzinfo else last.created_at.replace(tzinfo=utcnow().tzinfo)
            if utcnow() - created < COOLDOWN:
                return None
        a = Alert(kind=kind, severity=severity, symbol=symbol, title=title, message=message, dedup_key=key,
                  state_hash=h, payload=payload or {})
        s.add(a)
        s.flush()
        aid = a.id
        data = to_dict(a)
    bus.publish("alert", data)
    if notify and severity in ("high", "critical"):
        send_email(title, message)
    return aid


def to_dict(a: Alert) -> dict[str, Any]:
    return {"id": a.id, "created_at": a.created_at.isoformat(), "kind": a.kind, "severity": a.severity, "symbol": a.symbol,
            "title": a.title, "message": a.message, "payload": a.payload, "read": a.read}


def send_email(subject: str, body: str) -> bool:
    st = get_settings()
    if not (st.smtp_host and st.alert_email_to):
        return False
    try:
        msg = EmailMessage()
        msg["Subject"], msg["From"], msg["To"] = f"[oalgo2] {subject}", st.smtp_user or "oalgo2@localhost", st.alert_email_to
        msg.set_content(body + "\n\nResearch and paper trading only. Not investment advice; no orders are placed.")
        with smtplib.SMTP(st.smtp_host, st.smtp_port, timeout=20) as srv:
            srv.starttls()
            if st.smtp_user and st.smtp_password:
                srv.login(st.smtp_user, st.smtp_password)
            srv.send_message(msg)
        return True
    except Exception:
        log.exception("e-mail notification failed")
        return False


def _summary(p: dict[str, Any]) -> dict[str, Any]:
    return {"company": p.get("company"), "exchange": p.get("exchange"), "signal": p.get("signal"), "score": p.get("score"),
            "price": p.get("price"), "price_date": p.get("price_date"), "reasons": p.get("reasons"),
            "entry_conditions": p.get("entry_conditions"), "exit_conditions": p.get("exit_conditions"),
            "risk": p.get("risk"), "red_flags": p.get("red_flags"), "data_quality": p.get("data_quality")}


def evaluate_stock(symbol: str, old: dict[str, Any] | None, new: dict[str, Any], score_change: float = 10.0,
                   first_scan: bool = False, held: bool = False) -> list[int]:
    """Compare the previous and new research payload for one stock and emit alerts for meaningful changes."""
    ids: list[int | None] = []
    sig, old_sig = new.get("signal"), (old or {}).get("signal")
    score, old_score = new.get("score"), (old or {}).get("score")
    name = new.get("company") or symbol
    px = f"{new.get('price'):.2f}" if new.get("price") is not None else "n/a"
    if sig != old_sig and not (first_scan and sig not in ACTIONABLE | {"SELL"}):
        if sig in ACTIONABLE:
            ids.append(emit("signal", symbol, f"{sig}: {symbol} ({name})",
                            f"Score {score:.0f}/100 at {px} on {new.get('price_date')}. " + "; ".join(new.get("reasons") or []),
                            {"signal": sig}, "high" if sig == "STRONG BUY" else "medium", _summary(new)))
        elif sig == "SELL" and (old_sig is not None or held):
            ids.append(emit("signal", symbol, f"SELL: {symbol} ({name})",
                            f"Score {score:.0f}/100 at {px}. " + "; ".join((new.get("weaknesses") or [])[:3]),
                            {"signal": sig}, "high" if held else "medium", _summary(new)))
        elif old_sig in ACTIONABLE:
            ids.append(emit("signal", symbol, f"{symbol} downgraded from {old_sig} to {sig}",
                            f"Score {score:.0f}/100. " + "; ".join(new.get("gates") or []), {"signal": sig}, "medium", _summary(new)))
    if score is not None and old_score is not None and abs(score - old_score) >= score_change:
        ids.append(emit("score_change", symbol, f"{symbol} score {'up' if score > old_score else 'down'} {abs(score - old_score):.0f} points",
                        f"Score moved from {old_score:.0f} to {score:.0f}.", {"bucket": round(score / score_change)}, "info", _summary(new)))
    old_flags = {f["code"] for f in (old or {}).get("red_flags") or []}
    fresh = [f for f in new.get("red_flags") or [] if f["severity"] == "severe" and f["code"] not in old_flags]
    if fresh and (old is not None or held) and (held or sig in ACTIONABLE or old_sig in ACTIONABLE):
        ids.append(emit("risk", symbol, f"Risk warning: {symbol}", "; ".join(f["text"] for f in fresh),
                        {"flags": sorted(f["code"] for f in fresh)}, "high", _summary(new)))
    un = new.get("unusual") or {}
    if un.get("volume_ratio") and un["volume_ratio"] >= 3.0 and (held or sig in ACTIONABLE | {"WATCHLIST"}):
        ids.append(emit("unusual_volume", symbol, f"Unusual volume: {symbol}",
                        f"Volume on {new.get('price_date')} was {un['volume_ratio']:.1f}x the 20-day average; price change {un.get('ret_1d', 0):+.1%}.",
                        {"date": new.get("price_date")}, "info", _summary(new)))
    if un.get("move_sigma") and abs(un["move_sigma"]) >= 3.0 and (held or sig in ACTIONABLE | {"WATCHLIST"}):
        ids.append(emit("unusual_volatility", symbol, f"Unusual move: {symbol} {un.get('ret_1d', 0):+.1%}",
                        f"A {abs(un['move_sigma']):.1f}-sigma daily move on {new.get('price_date')}.", {"date": new.get("price_date")}, "info", _summary(new)))
    if held and un.get("entry_stop") and new.get("price") is not None and new["price"] <= un["entry_stop"]:
        ids.append(emit("exit_condition", symbol, f"Exit condition: {symbol} below its volatility stop",
                        f"Close {px} is at or below the stop reference {un['entry_stop']:.2f}.", {"stop": round(un["entry_stop"], 2)}, "high", _summary(new)))
    if held and new.get("price") is not None and un.get("below_200"):
        ids.append(emit("exit_condition", symbol, f"Exit condition: {symbol} closed below its 200-day average",
                        f"Close {px} on {new.get('price_date')}.", {"below_200": True}, "medium", _summary(new)))
    nf = new.get("new_filing")
    if nf and (held or sig in ACTIONABLE | {"WATCHLIST"}):
        ids.append(emit("filing", symbol, f"{symbol} filed {nf['form']}", f"{nf['form']} filed {nf['filing_date']} (SEC EDGAR).",
                        {"accession": nf["accession"]}, "info", {"url": nf.get("url"), **_summary(new)}))
    return [i for i in ids if i is not None]


def evaluate_regime(old: dict[str, Any] | None, new: dict[str, Any]) -> int | None:
    if old and old.get("regime") and old["regime"] != new.get("regime") and new.get("regime") != "unknown":
        return emit("regime_change", None, f"Market regime: {old['regime'].replace('_', '-')} -> {new['regime'].replace('_', '-')}",
                    "; ".join(f"{c['name']}: {c['reading']}" for c in new.get("components", [])), {"regime": new["regime"]}, "high", new)
    return None


def evaluate_providers(threshold: int = 3) -> list[int]:
    """Alert when a provider has failed `threshold` times in a row, and once more when it recovers."""
    ids = []
    with session() as s:
        states = [(r.provider, r.consecutive_failures, r.last_error) for r in s.scalars(select(ProviderHealth)).all()]
    for name, fails, err in states:
        key = f"provider:{name}"
        if fails >= threshold:
            i = emit("provider_failure", None, f"Data provider failing: {name}",
                     f"{fails} consecutive failures. Last error: {err}", {"failing": True}, "critical", key=key)
        else:
            with session() as s:
                last = s.scalars(select(Alert).where(Alert.dedup_key == key).order_by(Alert.id.desc()).limit(1)).first()
                was_failing = last is not None and last.state_hash == state_hash({"failing": True})
            i = emit("provider_recovered", None, f"Data provider recovered: {name}", "Requests are succeeding again.",
                     {"failing": False}, "info", key=key) if was_failing else None
        if i:
            ids.append(i)
    return ids

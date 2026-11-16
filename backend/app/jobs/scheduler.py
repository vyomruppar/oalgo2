"""Background scheduling (APScheduler, in-process). One daily full scan after the US close on
weekdays, plus a light hourly job that fills pending paper orders and checks provider health."""
from __future__ import annotations

import logging
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from ..alerts import engine as alerts
from ..config import get_settings
from ..data.yahoo import YahooPrices
from ..paper import ledger
from . import pipeline

log = logging.getLogger(__name__)
_scheduler: BackgroundScheduler | None = None


def _hourly() -> None:
    if pipeline.is_running():
        return
    try:
        y = YahooPrices()
        spx = y.load("^GSPC")
        ledger.process(y.load, spx["close"] if spx is not None else None)
        alerts.evaluate_providers()
    except Exception:
        log.exception("hourly maintenance failed")


def start() -> None:
    global _scheduler
    st = get_settings()
    if not st.scheduler_enabled or _scheduler is not None:
        return
    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_job(lambda: pipeline.run_scan(fetch=True), CronTrigger(day_of_week="mon-fri", hour=st.scan_cron_hour_utc, minute=st.scan_cron_minute),
                       id="daily_scan", max_instances=1, coalesce=True, misfire_grace_time=3600)
    _scheduler.add_job(_hourly, CronTrigger(minute=7), id="hourly_maintenance", max_instances=1, coalesce=True)
    _scheduler.start()


def stop() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None


def next_scan_time() -> datetime | None:
    if _scheduler is None:
        return None
    job = _scheduler.get_job("daily_scan")
    return job.next_run_time if job else None

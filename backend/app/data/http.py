"""Shared HTTP client: disk cache with TTL, token-bucket rate limiting, retries with backoff,
and per-provider health recording. Providers never fabricate data: a failed fetch raises ProviderError."""
from __future__ import annotations

import hashlib
import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

from ..config import get_settings
from ..db import ProviderHealth, session, utcnow

log = logging.getLogger(__name__)


class ProviderError(RuntimeError):
    def __init__(self, provider: str, message: str, status: int | None = None):
        super().__init__(f"[{provider}] {message}")
        self.provider = provider
        self.status = status


class RateLimiter:
    """Simple thread-safe spacing limiter (at most `rps` requests per second)."""

    def __init__(self, rps: float):
        self.interval = 1.0 / max(rps, 1e-6)
        self._lock = threading.Lock()
        self._next = 0.0

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            delay = self._next - now
            self._next = max(now, self._next) + self.interval
        if delay > 0:
            time.sleep(delay)


def record_health(provider: str, ok: bool, error: str | None = None) -> None:
    try:
        with session() as s:
            row = s.get(ProviderHealth, provider)
            if row is None:
                row = ProviderHealth(provider=provider, success_count=0, failure_count=0, consecutive_failures=0)
                s.add(row)
            if ok:
                row.last_success = utcnow()
                row.success_count += 1
                row.consecutive_failures = 0
            else:
                row.last_failure = utcnow()
                row.failure_count += 1
                row.consecutive_failures += 1
                row.last_error = (error or "")[:500]
    except Exception:  # health bookkeeping must never break a fetch
        log.exception("failed to record provider health")


@dataclass
class Fetched:
    content: bytes
    fetched_at: float  # epoch seconds when the bytes were retrieved from the provider
    from_cache: bool


class HttpProvider:
    def __init__(self, name: str, rps: float, user_agent: str | None = None, timeout: float = 45.0,
                 cache_dir: Path | None = None, max_retries: int = 4):
        st = get_settings()
        self.name = name
        self.limiter = RateLimiter(rps)
        self.max_retries = max_retries
        self.cache_dir = (cache_dir or st.cache_dir) / name
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.client = httpx.Client(
            timeout=timeout, follow_redirects=True,
            headers={"User-Agent": user_agent or st.http_user_agent, "Accept-Encoding": "gzip, deflate"},
        )

    def _cache_path(self, url: str) -> Path:
        return self.cache_dir / hashlib.sha256(url.encode()).hexdigest()[:32]

    def cached(self, url: str, ttl_seconds: float | None) -> Fetched | None:
        p = self._cache_path(url)
        if not p.exists():
            return None
        mtime = p.stat().st_mtime
        if ttl_seconds is not None and time.time() - mtime > ttl_seconds:
            return None
        return Fetched(p.read_bytes(), mtime, True)

    def get(self, url: str, ttl_seconds: float | None = 3600.0, allow_stale_on_error: bool = True) -> Fetched:
        """GET with cache. ttl_seconds=None means cache forever; 0 means always refetch."""
        if ttl_seconds != 0:
            hit = self.cached(url, ttl_seconds)
            if hit is not None:
                return hit
        last_err: str = "unknown"
        status: int | None = None
        for attempt in range(self.max_retries):
            self.limiter.wait()
            try:
                r = self.client.get(url)
                status = r.status_code
                if status == 200:
                    p = self._cache_path(url)
                    tmp = p.with_suffix(".tmp")
                    tmp.write_bytes(r.content)
                    tmp.replace(p)
                    record_health(self.name, True)
                    return Fetched(r.content, time.time(), False)
                last_err = f"HTTP {status}"
                if status in (400, 401, 403, 404):
                    break  # not retryable
                retry_after = r.headers.get("Retry-After")
                sleep = float(retry_after) if retry_after and retry_after.isdigit() else 1.5 * (2 ** attempt)
            except httpx.HTTPError as e:
                last_err = f"{type(e).__name__}: {e}"
                sleep = 1.5 * (2 ** attempt)
            if attempt < self.max_retries - 1:
                time.sleep(min(sleep, 30.0))
        # A 404 is an answer ("this resource does not exist"), not an outage: it must not trip the
        # provider-failure alert (e.g. foreign filers have no XBRL company-facts document).
        if status != 404:
            record_health(self.name, False, f"{last_err} for {url[:200]}")
        if allow_stale_on_error:
            stale = self.cached(url, None)
            if stale is not None:
                log.warning("%s: serving stale cache for %s after %s", self.name, url, last_err)
                return stale
        raise ProviderError(self.name, f"{last_err} for {url}", status)

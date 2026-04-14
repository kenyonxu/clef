"""Per-provider rate limiting via token bucket algorithm."""

import asyncio
import logging
import threading
import time
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

DEFAULT_RPM = 60
DEFAULT_BURST = 10


class ProviderRateLimiter:
    """Global rate limiter pool keyed by model alias.

    Uses token bucket algorithm: each provider gets a bucket with
    ``burst`` capacity that refills at ``rpm / 60`` tokens per second.
    Correctly handles RPM windows (not just concurrency).
    """

    class _TokenBucket:
        """Thread-safe token bucket for a single provider."""

        def __init__(self, capacity: int, refill_per_sec: float) -> None:
            self._capacity = capacity
            self._refill_per_sec = refill_per_sec
            self._tokens = float(capacity)
            self._last_refill = time.monotonic()
            self._lock = threading.Lock()

        def _refill(self) -> None:
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._tokens = min(
                self._capacity, self._tokens + elapsed * self._refill_per_sec
            )
            self._last_refill = now

        def try_acquire(self) -> bool:
            with self._lock:
                self._refill()
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return True
                return False

        def wait_time(self) -> float:
            """Seconds until next token is available."""
            with self._lock:
                self._refill()
                if self._tokens >= 1.0:
                    return 0.0
                return (1.0 - self._tokens) / self._refill_per_sec

    def __init__(self, configs: dict[str, dict] | None = None) -> None:
        """configs: {alias: {"rpm": int, "burst": int}}"""
        self._configs: dict[str, dict] = configs or {}
        self._buckets: dict[str, ProviderRateLimiter._TokenBucket] = {}

    def get_config(self, alias: str) -> dict:
        return self._configs.get(alias, {"rpm": DEFAULT_RPM, "burst": DEFAULT_BURST})

    def _get_bucket(self, alias: str) -> _TokenBucket:
        if alias not in self._buckets:
            cfg = self.get_config(alias)
            rpm = cfg.get("rpm", DEFAULT_RPM)
            burst = cfg.get("burst", DEFAULT_BURST)
            refill = rpm / 60.0  # tokens per second
            self._buckets[alias] = self._TokenBucket(
                capacity=burst, refill_per_sec=refill
            )
            logger.info(
                "Rate limiter for %s: rpm=%d, burst=%d, refill=%.1f/s",
                alias,
                rpm,
                burst,
                refill,
            )
        return self._buckets[alias]

    @asynccontextmanager
    async def acquire(self, alias: str):
        """Acquire a token for the given provider. Waits if bucket is empty."""
        bucket = self._get_bucket(alias)
        while not bucket.try_acquire():
            wait = bucket.wait_time()
            await asyncio.sleep(max(wait, 0.05))
        yield

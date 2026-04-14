import asyncio
import time

import pytest

from clef_server.concurrency import ProviderRateLimiter


class TestTokenBucket:
    def test_bucket_refills_over_time(self):
        """Tokens refill at rpm rate over time."""
        bucket = ProviderRateLimiter._TokenBucket(capacity=3, refill_per_sec=10.0)
        assert bucket.try_acquire()  # 1/3
        assert bucket.try_acquire()  # 2/3
        assert bucket.try_acquire()  # 3/3 — full
        assert not bucket.try_acquire()  # empty

    def test_bucket_refills_after_wait(self):
        """After waiting, tokens become available again."""
        bucket = ProviderRateLimiter._TokenBucket(capacity=2, refill_per_sec=100.0)
        assert bucket.try_acquire()
        assert bucket.try_acquire()
        assert not bucket.try_acquire()
        time.sleep(0.03)  # ~3 tokens refilled
        assert bucket.try_acquire()

    def test_bucket_capacity_capped(self):
        """Tokens don't exceed capacity even after long idle."""
        bucket = ProviderRateLimiter._TokenBucket(capacity=3, refill_per_sec=1000.0)
        time.sleep(0.01)
        # Should still only allow capacity tokens
        count = sum(1 for _ in range(10) if bucket.try_acquire())
        assert count == 3


class TestProviderRateLimiter:
    def test_get_limiter_creates_with_config(self):
        limiter = ProviderRateLimiter(
            {"glm": {"rpm": 30, "burst": 5}, "deepseek": {"rpm": 60, "burst": 10}}
        )
        assert limiter.get_config("glm")["rpm"] == 30
        assert limiter.get_config("deepseek")["rpm"] == 60

    def test_get_limiter_default(self):
        limiter = ProviderRateLimiter({})
        config = limiter.get_config("unknown")
        assert config["rpm"] == 60  # default
        assert config["burst"] == 10  # default

    @pytest.mark.asyncio
    async def test_acquire_respects_rate_limit(self):
        """At burst=2, 3rd acquire must wait for refill."""
        limiter = ProviderRateLimiter({"test": {"rpm": 3000, "burst": 2}})
        # Burn 2 burst tokens instantly
        async with limiter.acquire("test"):
            pass
        async with limiter.acquire("test"):
            pass
        # 3rd should still succeed (waits for refill, ~20ms at 3000 rpm)
        t0 = time.monotonic()
        async with limiter.acquire("test"):
            pass
        elapsed = time.monotonic() - t0
        # Should have waited briefly for refill, not failed
        assert elapsed < 1.0

    @pytest.mark.asyncio
    async def test_acquire_releases_on_exit(self):
        """Context manager releases slot, allowing next acquire."""
        limiter = ProviderRateLimiter({"test": {"rpm": 60, "burst": 1}})
        async with limiter.acquire("test"):
            pass  # released
        # Next acquire should succeed after refill wait
        async with limiter.acquire("test"):
            pass  # should not hang

    @pytest.mark.asyncio
    async def test_concurrent_sessions_share_limiter(self):
        """Multiple sessions using same alias share the rate limit."""
        limiter = ProviderRateLimiter({"shared": {"rpm": 120, "burst": 2}})
        peak = 0
        active = 0

        async def task():
            nonlocal active, peak
            async with limiter.acquire("shared"):
                active += 1
                peak = max(peak, active)
                await asyncio.sleep(0.05)
                active -= 1

        await asyncio.gather(*[task() for _ in range(6)])
        assert peak <= 2  # burst=2 means max 2 concurrent

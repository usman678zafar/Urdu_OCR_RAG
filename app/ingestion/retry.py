"""Retries with exponential backoff, and a concurrency limit that shrinks on rate limits.

Used around calls to outside OCR services, which fail transiently with 429
(rate limit), 5xx (overloaded) or timeouts.
"""

import logging
import random
import threading
import time
from collections.abc import Callable
from typing import TypeVar

log = logging.getLogger(__name__)

T = TypeVar("T")

RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}


def status_of(exc: BaseException) -> int | None:
    """HTTP status carried by the exception, if any (LLMError.status, SDK .code/.status_code)."""
    for attr in ("status", "status_code", "code"):
        value = getattr(exc, attr, None)
        if isinstance(value, int):
            return value
    return None


def is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return True
    name = type(exc).__name__  # SDK errors such as APITimeoutError, APIConnectionError
    if "Timeout" in name or "Connection" in name:
        return True
    status = status_of(exc)
    if status is not None:
        return status in RETRYABLE_STATUS
    return bool(getattr(exc, "retryable", False))


def backoff_delay(attempt: int, base: float, rng: Callable[[], float] = random.random) -> float:
    """Delay before retry number `attempt` (1-based): base * 2^(attempt-1), plus up to 50% jitter."""
    delay = base * 2 ** (attempt - 1)
    return delay + delay * 0.5 * rng()


def call_with_retry(
    fn: Callable[[], T],
    attempts: int,
    base_delay: float,
    on_retry: Callable[[BaseException, int], None] | None = None,
    sleep: Callable[[float], None] = time.sleep,
    rng: Callable[[], float] = random.random,
) -> T:
    """Call fn, retrying retryable errors up to `attempts` calls in total; re-raise the last error."""
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except Exception as e:
            if attempt == attempts or not is_retryable(e):
                raise
            delay = backoff_delay(attempt, base_delay, rng)
            log.warning("Attempt %d/%d failed (%s); retrying in %.1fs", attempt, attempts, e, delay)
            if on_retry:
                on_retry(e, attempt)
            sleep(delay)
    raise AssertionError("unreachable")


class AdaptiveLimiter:
    """A semaphore whose limit halves on a rate-limit error and creeps back up after
    a run of successes, so a burst of 429s slows everyone down instead of piling on."""

    def __init__(self, limit: int, recover_after: int = 10):
        self.max_limit = max(1, limit)
        self.limit = self.max_limit
        self.recover_after = recover_after
        self._active = 0
        self._successes = 0
        self._cond = threading.Condition()

    def __enter__(self):
        with self._cond:
            while self._active >= self.limit:
                self._cond.wait()
            self._active += 1
        return self

    def __exit__(self, *exc):
        with self._cond:
            self._active -= 1
            self._cond.notify_all()

    def rate_limited(self) -> None:
        with self._cond:
            self._successes = 0
            if self.limit > 1:
                self.limit = max(1, self.limit // 2)
                log.warning("Rate limited; lowering OCR concurrency to %d", self.limit)

    def succeeded(self) -> None:
        with self._cond:
            self._successes += 1
            if self._successes >= self.recover_after and self.limit < self.max_limit:
                self.limit += 1
                self._successes = 0
                self._cond.notify_all()

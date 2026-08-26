from __future__ import annotations

import math
import threading
from dataclasses import dataclass
from time import monotonic
from typing import Callable


@dataclass(frozen=True)
class BucketPolicy:
    capacity: float
    refill_per_second: float

    def __post_init__(self) -> None:
        if self.capacity <= 0:
            raise ValueError("bucket capacity must be positive")
        if self.refill_per_second <= 0:
            raise ValueError("bucket refill rate must be positive")


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    retry_after_seconds: int = 0


@dataclass
class _BucketState:
    tokens: float
    updated_at: float


class TokenBucketLimiter:
    def __init__(
        self,
        policies: dict[str, BucketPolicy],
        *,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self._policies = dict(policies)
        self._clock = clock
        self._states: dict[tuple[str, str], _BucketState] = {}
        self._lock = threading.Lock()

    def consume(self, bucket: str, key: str, *, cost: float = 1.0) -> RateLimitDecision:
        if cost <= 0:
            raise ValueError("rate-limit cost must be positive")
        policy = self._policies.get(bucket)
        if policy is None:
            raise ValueError(f"unknown rate-limit bucket: {bucket}")
        if not key:
            raise ValueError("rate-limit key must not be empty")

        now = self._clock()
        state_key = (bucket, key)
        with self._lock:
            state = self._states.get(state_key)
            if state is None:
                state = _BucketState(tokens=policy.capacity, updated_at=now)
                self._states[state_key] = state
            else:
                elapsed = max(0.0, now - state.updated_at)
                state.tokens = min(
                    policy.capacity,
                    state.tokens + elapsed * policy.refill_per_second,
                )
                state.updated_at = now

            if state.tokens >= cost:
                state.tokens -= cost
                return RateLimitDecision(allowed=True)

            deficit = cost - state.tokens
            retry = max(1, min(3600, math.ceil(deficit / policy.refill_per_second)))
            return RateLimitDecision(allowed=False, retry_after_seconds=retry)


def default_bucket_policies() -> dict[str, BucketPolicy]:
    return {
        "auth-bootstrap": BucketPolicy(capacity=3, refill_per_second=1 / 60),
        "auth-login": BucketPolicy(capacity=5, refill_per_second=1 / 30),
        "endpoint-enrollment": BucketPolicy(capacity=10, refill_per_second=1 / 30),
        "admin-read": BucketPolicy(capacity=120, refill_per_second=2),
        "admin-write": BucketPolicy(capacity=30, refill_per_second=0.5),
        "public-read": BucketPolicy(capacity=120, refill_per_second=2),
    }

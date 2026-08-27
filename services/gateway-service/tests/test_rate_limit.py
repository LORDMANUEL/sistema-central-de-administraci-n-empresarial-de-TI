from __future__ import annotations

from app.rate_limit import BucketPolicy, TokenBucketLimiter


class Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_token_bucket_is_deterministic_and_returns_bounded_retry_after():
    clock = Clock()
    limiter = TokenBucketLimiter(
        {"admin-write": BucketPolicy(capacity=2, refill_per_second=1.0)},
        clock=clock,
    )

    assert limiter.consume("admin-write", "user-1").allowed is True
    assert limiter.consume("admin-write", "user-1").allowed is True

    denied = limiter.consume("admin-write", "user-1")
    assert denied.allowed is False
    assert denied.retry_after_seconds == 1

    clock.advance(1.0)
    assert limiter.consume("admin-write", "user-1").allowed is True


def test_buckets_and_actor_keys_are_isolated():
    clock = Clock()
    limiter = TokenBucketLimiter(
        {
            "admin-write": BucketPolicy(capacity=1, refill_per_second=0.5),
            "admin-read": BucketPolicy(capacity=2, refill_per_second=1.0),
        },
        clock=clock,
    )

    assert limiter.consume("admin-write", "user-a").allowed
    assert not limiter.consume("admin-write", "user-a").allowed
    assert limiter.consume("admin-write", "user-b").allowed
    assert limiter.consume("admin-read", "user-a").allowed

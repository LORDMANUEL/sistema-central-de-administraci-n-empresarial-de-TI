from __future__ import annotations

from dataclasses import dataclass
import json
from secrets import token_urlsafe
from threading import RLock
from time import monotonic, time


@dataclass
class GuardianSession:
    access_token: str
    refresh_token: str
    csrf_token: str
    last_seen: float


class SessionStore:
    """Bounded in-memory store for tests and local development only."""

    def __init__(self, *, ttl_seconds: int, max_sessions: int):
        if ttl_seconds < 1 or max_sessions < 1:
            raise ValueError("session limits must be positive")
        self.ttl_seconds = ttl_seconds
        self.max_sessions = max_sessions
        self._items: dict[str, GuardianSession] = {}
        self._lock = RLock()

    def _prune(self, now: float) -> None:
        expired = [key for key, item in self._items.items() if now - item.last_seen > self.ttl_seconds]
        for key in expired:
            self._items.pop(key, None)
        while len(self._items) >= self.max_sessions:
            oldest = min(self._items, key=lambda key: self._items[key].last_seen)
            self._items.pop(oldest, None)

    def create(self, access_token: str, refresh_token: str) -> str:
        now = monotonic()
        with self._lock:
            self._prune(now)
            session_id = token_urlsafe(48)
            while session_id in self._items:
                session_id = token_urlsafe(48)
            self._items[session_id] = GuardianSession(access_token, refresh_token, token_urlsafe(32), now)
            return session_id

    def get(self, session_id: str | None) -> GuardianSession | None:
        if not session_id:
            return None
        now = monotonic()
        with self._lock:
            item = self._items.get(session_id)
            if item is None:
                return None
            if now - item.last_seen > self.ttl_seconds:
                self._items.pop(session_id, None)
                return None
            item.last_seen = now
            return item

    def replace_tokens(self, session_id: str, access_token: str, refresh_token: str) -> bool:
        now = monotonic()
        with self._lock:
            item = self._items.get(session_id)
            if item is None:
                return False
            item.access_token = access_token
            item.refresh_token = refresh_token
            item.last_seen = now
            return True

    def delete(self, session_id: str | None) -> None:
        if not session_id:
            return
        with self._lock:
            self._items.pop(session_id, None)

    def ready(self) -> bool:
        return True

    def close(self) -> None:
        return None


class RedisSessionStore:
    """Shared production store backed by Redis/Valkey with sliding TTL and bounded cardinality."""

    def __init__(self, client, *, ttl_seconds: int, max_sessions: int, prefix: str = "itg:web-session"):
        if ttl_seconds < 1 or max_sessions < 1:
            raise ValueError("session limits must be positive")
        self.client = client
        self.ttl_seconds = ttl_seconds
        self.max_sessions = max_sessions
        self.prefix = prefix.rstrip(":")
        self.index_key = f"{self.prefix}:index"

    def _key(self, session_id: str) -> str:
        return f"{self.prefix}:{session_id}"

    @staticmethod
    def _encode(access_token: str, refresh_token: str, csrf_token: str) -> str:
        return json.dumps({"access_token": access_token, "refresh_token": refresh_token, "csrf_token": csrf_token}, separators=(",", ":"))

    @staticmethod
    def _decode(raw: str, last_seen: float) -> GuardianSession:
        data = json.loads(raw)
        return GuardianSession(str(data["access_token"]), str(data["refresh_token"]), str(data["csrf_token"]), last_seen)

    def _evict(self, now: float) -> None:
        expired_ids = self.client.zrangebyscore(self.index_key, "-inf", now - self.ttl_seconds)
        if expired_ids:
            pipe = self.client.pipeline()
            for session_id in expired_ids:
                pipe.delete(self._key(str(session_id)))
            pipe.zrem(self.index_key, *expired_ids)
            pipe.execute()
        count = int(self.client.zcard(self.index_key))
        excess = max(0, count - self.max_sessions + 1)
        if excess:
            oldest = self.client.zrange(self.index_key, 0, excess - 1)
            if oldest:
                pipe = self.client.pipeline()
                for session_id in oldest:
                    pipe.delete(self._key(str(session_id)))
                pipe.zrem(self.index_key, *oldest)
                pipe.execute()

    def create(self, access_token: str, refresh_token: str) -> str:
        now = time()
        self._evict(now)
        csrf_token = token_urlsafe(32)
        for _ in range(8):
            session_id = token_urlsafe(48)
            if self.client.set(self._key(session_id), self._encode(access_token, refresh_token, csrf_token), ex=self.ttl_seconds, nx=True):
                self.client.zadd(self.index_key, {session_id: now})
                return session_id
        raise RuntimeError("unable to allocate unique session id")

    def get(self, session_id: str | None) -> GuardianSession | None:
        if not session_id:
            return None
        key = self._key(session_id)
        raw = self.client.get(key)
        if raw is None:
            self.client.zrem(self.index_key, session_id)
            return None
        now = time()
        pipe = self.client.pipeline()
        pipe.expire(key, self.ttl_seconds)
        pipe.zadd(self.index_key, {session_id: now})
        pipe.execute()
        try:
            return self._decode(str(raw), now)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            self.delete(session_id)
            return None

    def replace_tokens(self, session_id: str, access_token: str, refresh_token: str) -> bool:
        current = self.get(session_id)
        if current is None:
            return False
        now = time()
        self.client.set(self._key(session_id), self._encode(access_token, refresh_token, current.csrf_token), ex=self.ttl_seconds)
        self.client.zadd(self.index_key, {session_id: now})
        return True

    def delete(self, session_id: str | None) -> None:
        if not session_id:
            return
        pipe = self.client.pipeline()
        pipe.delete(self._key(session_id))
        pipe.zrem(self.index_key, session_id)
        pipe.execute()

    def ready(self) -> bool:
        return bool(self.client.ping())

    def close(self) -> None:
        close = getattr(self.client, "close", None)
        if close is not None:
            close()

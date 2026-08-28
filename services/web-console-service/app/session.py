from __future__ import annotations

from dataclasses import dataclass
from secrets import token_urlsafe
from threading import RLock
from time import monotonic


@dataclass
class GuardianSession:
    access_token: str
    refresh_token: str
    last_seen: float


class SessionStore:
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
            self._items[session_id] = GuardianSession(access_token, refresh_token, now)
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

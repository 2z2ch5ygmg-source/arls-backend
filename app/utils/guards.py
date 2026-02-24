from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from fastapi import HTTPException

from ..config import settings
from ..security import sha256_hex


class RateLimiter:
    def __init__(self):
        self._lock = threading.Lock()
        self._buckets: dict[tuple[str, str], deque[float]] = defaultdict(deque)

    def check(self, token: str, tenant_id: str) -> None:
        key = (tenant_id, token)
        now = time.time()
        window = 60
        limit = max(1, settings.rate_limit_per_minute)

        with self._lock:
            bucket = self._buckets[key]
            while bucket and now - bucket[0] > window:
                bucket.popleft()
            if len(bucket) >= limit:
                raise HTTPException(status_code=429, detail="rate limit exceeded")
            bucket.append(now)


class IdempotencyGuard:
    def __init__(self):
        self._lock = threading.Lock()
        self._seen: dict[tuple[str, str, str], float] = {}

    def seen(self, tenant_id: str, user_id: str, key: str) -> bool:
        if not key:
            return False
        composite = (tenant_id, str(user_id), key)
        now = time.time()
        ttl = max(1, settings.idempotency_ttl_minutes) * 60

        with self._lock:
            expire_at = self._seen.get(composite)
            if expire_at and expire_at > now:
                return True
            self._seen[composite] = now + ttl
            return False


RATE_LIMITER = RateLimiter()
IDEMPOTENCY = IdempotencyGuard()


def request_hash(body: str, method: str, path: str) -> str:
    return sha256_hex(f"{method}:{path}:{body}")

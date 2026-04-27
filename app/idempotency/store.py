from typing import Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta
import asyncio

@dataclass
class CachedResponse:
    response: Any
    created_at: datetime

class IdempotencyStore:
    def __init__(self, ttl_minutes: int = 30):
        self._cache: Dict[int, CachedResponse] = {}
        self.ttl = timedelta(minutes=ttl_minutes)
        self._lock = asyncio.Lock()

    async def get(self, update_id: int) -> Optional[Any]:
        """Returns the cached response if it exists and hasn't expired."""
        async with self._lock:
            self._cleanup()
            if update_id in self._cache:
                return self._cache[update_id].response
        return None

    async def set(self, update_id: int, response: Any):
        """Stores a response for a given update_id."""
        async with self._lock:
            self._cache[update_id] = CachedResponse(
                response=response,
                created_at=datetime.now()
            )

    def _cleanup(self):
        """Removes expired entries."""
        now = datetime.now()
        expired_keys = [
            k for k, v in self._cache.items() 
            if now - v.created_at > self.ttl
        ]
        for k in expired_keys:
            del self._cache[k]

# Global idempotency store
idempotency_store = IdempotencyStore()

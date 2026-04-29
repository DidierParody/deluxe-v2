import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from app.cache.redis_client import get_redis
from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class CachedResponse:
    response: Any
    created_at: datetime


class IdempotencyStore:
    def __init__(self, ttl_minutes: Optional[int] = None):
        configured_ttl = ttl_minutes or settings.REDIS_IDEMPOTENCY_TTL_MINUTES
        self._cache: Dict[int, CachedResponse] = {}
        self.ttl = timedelta(minutes=configured_ttl)

    async def get(self, update_id: int) -> Optional[Any]:
        """Returns the cached response if it exists and hasn't expired."""
        redis = await get_redis()
        if redis is not None:
            key = self._redis_key(update_id)
            try:
                payload = await redis.get(key)
                if payload is not None:
                    await redis.expire(key, int(self.ttl.total_seconds()))
                    return json.loads(payload)
            except Exception as exc:
                logger.warning(f"Fallo al leer idempotencia desde Redis. Se usa fallback local. Error: {exc}")

        self._cleanup()
        if update_id in self._cache:
            return self._cache[update_id].response
        return None

    async def set(self, update_id: int, response: Any):
        """Stores a response for a given update_id."""
        redis = await get_redis()
        if redis is not None:
            try:
                await redis.set(
                    self._redis_key(update_id),
                    json.dumps(response, ensure_ascii=False, default=str),
                    ex=int(self.ttl.total_seconds()),
                )
                return
            except Exception as exc:
                logger.warning(f"Fallo al escribir idempotencia en Redis. Se usa fallback local. Error: {exc}")

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

    def _redis_key(self, update_id: int) -> str:
        return f"idem:update:{update_id}"


# Global idempotency store
idempotency_store = IdempotencyStore()

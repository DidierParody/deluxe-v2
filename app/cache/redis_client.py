import json
import logging
from typing import Any, Protocol

import httpx
from redis.asyncio import Redis

from app.config import settings

logger = logging.getLogger(__name__)


class CacheClient(Protocol):
    async def ping(self) -> Any: ...
    async def get(self, key: str) -> Any: ...
    async def set(self, key: str, value: Any, ex: int | None = None) -> Any: ...
    async def expire(self, key: str, seconds: int) -> Any: ...
    async def delete(self, *keys: str) -> Any: ...
    async def lrange(self, key: str, start: int, end: int) -> Any: ...
    async def rpush(self, key: str, *values: Any) -> Any: ...
    async def ltrim(self, key: str, start: int, end: int) -> Any: ...
    async def aclose(self) -> None: ...


class UpstashRestClient:
    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip("/")
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=10.0,
        )

    async def ping(self) -> Any:
        return await self._command("PING")

    async def get(self, key: str) -> Any:
        return await self._command("GET", key)

    async def set(self, key: str, value: Any, ex: int | None = None) -> Any:
        args = ["SET", key, value]
        if ex is not None:
            args.extend(["EX", ex])
        return await self._command(*args)

    async def expire(self, key: str, seconds: int) -> Any:
        return await self._command("EXPIRE", key, seconds)

    async def delete(self, *keys: str) -> Any:
        return await self._command("DEL", *keys)

    async def lrange(self, key: str, start: int, end: int) -> Any:
        return await self._command("LRANGE", key, start, end)

    async def rpush(self, key: str, *values: Any) -> Any:
        return await self._command("RPUSH", key, *values)

    async def ltrim(self, key: str, start: int, end: int) -> Any:
        return await self._command("LTRIM", key, start, end)

    async def aclose(self) -> None:
        await self.client.aclose()

    async def _command(self, *parts: Any) -> Any:
        payload = [self._normalize_part(part) for part in parts]
        response = await self.client.post("/", json=payload)
        response.raise_for_status()

        data = response.json()
        if isinstance(data, dict):
            if "error" in data:
                raise RuntimeError(data["error"])
            return data.get("result")

        raise RuntimeError(f"Respuesta inesperada de Upstash REST: {data}")

    def _normalize_part(self, value: Any) -> Any:
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False)
        return value


_redis: CacheClient | None = None


async def init_redis() -> CacheClient | None:
    global _redis

    if _redis is not None:
        return _redis

    if settings.UPSTASH_REDIS_REST_URL and settings.UPSTASH_REDIS_REST_TOKEN:
        client = UpstashRestClient(
            base_url=settings.UPSTASH_REDIS_REST_URL,
            token=settings.UPSTASH_REDIS_REST_TOKEN,
        )
        try:
            await client.ping()
        except Exception as exc:
            logger.warning(
                f"No fue posible conectar con Upstash REST. Se usara fallback local. Error: {exc}"
            )
            await client.aclose()
            return None

        _redis = client
        logger.info("Upstash Redis REST inicializado correctamente.")
        return _redis

    if not settings.REDIS_URL:
        logger.info(
            "No hay REDIS_URL ni credenciales REST de Upstash. Se usara fallback local para memoria e idempotencia."
        )
        return None

    client = Redis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
        health_check_interval=30,
    )

    try:
        await client.ping()
    except Exception as exc:
        logger.warning(
            f"No fue posible conectar con Redis TCP. Se usara fallback local. Error: {exc}"
        )
        await client.aclose()
        return None

    _redis = client
    logger.info("Redis TCP inicializado correctamente.")
    return _redis


async def get_redis() -> CacheClient | None:
    if _redis is None:
        return await init_redis()
    return _redis


async def close_redis():
    global _redis

    if _redis is not None:
        await _redis.aclose()
        _redis = None
        logger.info("Conexion Redis cerrada.")

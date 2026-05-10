"""
Unit tests for the idempotency store (local in-memory fallback path).
"""
import pytest
from unittest.mock import patch, AsyncMock

with patch.dict("os.environ", {
    "DATABASE_URL": "postgresql://fake",
    "TELEGRAM_BOT_TOKEN_CS": "fake",
    "TELEGRAM_BOT_TOKEN_AM": "fake",
    "WEBHOOK_BASE_URL": "https://fake.example.com",
    "NVIDIA_API_KEY": "fake",
    "REDIS_MEMORY_ENABLED": "false",
}):
    from app.idempotency.store import IdempotencyStore


@pytest.mark.asyncio
async def test_local_store_set_and_get():
    store = IdempotencyStore()
    await store.set(42, "hello")
    result = await store.get(42)
    assert result == "hello"


@pytest.mark.asyncio
async def test_local_store_returns_none_for_missing_key():
    store = IdempotencyStore()
    result = await store.get(9999)
    assert result is None


@pytest.mark.asyncio
async def test_local_store_different_update_ids_are_independent():
    store = IdempotencyStore()
    await store.set(1, "response A")
    await store.set(2, "response B")
    assert await store.get(1) == "response A"
    assert await store.get(2) == "response B"

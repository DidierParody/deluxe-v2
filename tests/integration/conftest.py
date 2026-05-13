"""
Integration test fixtures.

Patches all external I/O (DB, Redis, Telegram, LangGraph) so the FastAPI app
can be started inside an httpx.AsyncClient without real network calls.
"""

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from httpx import ASGITransport

FAKE_ENV = {
    "DATABASE_URL": "postgresql://fake:fake@fake/fake",
    "TELEGRAM_BOT_TOKEN_CS": "1234567890:AAFakeTokenForCSBot",
    "TELEGRAM_BOT_TOKEN_AM": "0987654321:AAFakeTokenForAMBot",
    "WEBHOOK_BASE_URL": "http://fake.example.com",  # http:// intentional — skips set_webhook
    "NVIDIA_API_KEY": "nvapi-fake",
    "REDIS_MEMORY_ENABLED": "false",
    "WEBHOOK_SECRET_TOKEN": "test-secret",
}

# Import app.main (which triggers Settings() at module level) inside the env patch
# so pydantic-settings picks up the fake values.  Guard against re-import if the
# module is already loaded from a previous test session.
with patch.dict("os.environ", FAKE_ENV):
    # Remove any cached module so Settings() is evaluated with the patched env.
    for _mod in list(sys.modules.keys()):
        if _mod.startswith("app"):
            del sys.modules[_mod]

    from app.main import app, bot_am_app, bot_cs_app  # noqa: E402


@pytest.fixture(scope="function")
def fake_env():
    """Return the fake environment dict for tests that need token values."""
    return FAKE_ENV.copy()


@pytest.fixture
async def client():
    """
    Async httpx client backed by the FastAPI ASGI app.

    All external I/O is mocked so no real DB, Redis, or Telegram calls are made.
    """
    with (
        patch("app.db.pool.init_pool", new_callable=AsyncMock),
        patch("app.db.pool.close_pool", new_callable=AsyncMock),
        patch("app.cache.redis_client.init_redis", new_callable=AsyncMock, return_value=None),
        patch("app.cache.redis_client.close_redis", new_callable=AsyncMock),
        patch("app.agents.graph.compile_graph", return_value=MagicMock()),
        patch.object(bot_cs_app, "initialize", new_callable=AsyncMock),
        patch.object(bot_cs_app, "shutdown", new_callable=AsyncMock),
        patch.object(bot_cs_app.bot, "set_webhook", new_callable=AsyncMock),
        patch.object(bot_am_app, "initialize", new_callable=AsyncMock),
        patch.object(bot_am_app, "shutdown", new_callable=AsyncMock),
        patch.object(bot_am_app.bot, "set_webhook", new_callable=AsyncMock),
    ):
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac

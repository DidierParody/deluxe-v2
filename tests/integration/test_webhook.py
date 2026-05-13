"""
Integration tests for health and webhook endpoints.
"""

from unittest.mock import AsyncMock, patch

from tests.integration.conftest import bot_cs_app

VALID_UPDATE = {
    "update_id": 1,
    "message": {
        "message_id": 1,
        "date": 1700000000,
        "chat": {"id": 123, "type": "private"},
        "from": {"id": 123, "is_bot": False, "first_name": "Test"},
    },
}

VALID_HEADERS = {"X-Telegram-Bot-Api-Secret-Token": "test-secret"}


async def test_health_returns_ok(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


async def test_health_redis_not_configured(client):
    response = await client.get("/health")
    assert not response.json()["redis_configured"]


async def test_webhook_requires_valid_signature(client):
    response = await client.post("/webhook/deluxecs", json=VALID_UPDATE)
    assert response.status_code == 403


async def test_webhook_rejects_wrong_signature(client):
    response = await client.post(
        "/webhook/deluxecs",
        json=VALID_UPDATE,
        headers={"X-Telegram-Bot-Api-Secret-Token": "wrong-token"},
    )
    assert response.status_code == 403


async def test_webhook_accepts_valid_signature(client):
    with patch.object(bot_cs_app, "process_update", new_callable=AsyncMock):
        response = await client.post(
            "/webhook/deluxecs",
            json=VALID_UPDATE,
            headers=VALID_HEADERS,
        )
    assert response.status_code == 200


async def test_webhook_idempotency_same_update_id(client):
    with patch.object(bot_cs_app, "process_update", new_callable=AsyncMock) as mock_process:
        response1 = await client.post(
            "/webhook/deluxecs",
            json=VALID_UPDATE,
            headers=VALID_HEADERS,
        )
        response2 = await client.post(
            "/webhook/deluxecs",
            json=VALID_UPDATE,
            headers=VALID_HEADERS,
        )
    assert response1.status_code == 200
    assert response2.status_code == 200
    assert mock_process.call_count == 2

import logging

import pytest

from src.main import REQUEST_ID_PATTERN


@pytest.mark.asyncio
async def test_health(client):
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert REQUEST_ID_PATTERN.fullmatch(response.headers["x-request-id"])


@pytest.mark.asyncio
async def test_request_id_is_preserved(client):
    response = await client.get("/health", headers={"X-Request-ID": "trace-123"})

    assert response.headers["x-request-id"] == "trace-123"


@pytest.mark.asyncio
async def test_invalid_request_id_is_replaced(client):
    response = await client.get("/health", headers={"X-Request-ID": "invalid request id"})

    request_id = response.headers["x-request-id"]
    assert request_id != "invalid request id"
    assert REQUEST_ID_PATTERN.fullmatch(request_id)


@pytest.mark.asyncio
async def test_chat_empty_message(client, caplog):
    # Given
    caplog.set_level(logging.WARNING)

    # When
    response = await client.post("/api/v1/chat", json={"message": ""})

    # Then
    validation_logs = [
        record for record in caplog.records if getattr(record, "event", None) == "http_validation_failed"
    ]
    assert response.status_code == 422
    assert len(validation_logs) == 1
    assert validation_logs[0].status_code == 422
    assert validation_logs[0].error_count > 0


@pytest.mark.asyncio
async def test_agent_status(client):
    response = await client.get("/api/v1/status")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_development_ui_is_not_cached(client):
    response = await client.get("/ui/styles.css")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store, max-age=0"

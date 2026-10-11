import logging

import pytest

PROCUREMENT_CREDENTIALS = {
    "email": "purchasing@vinuni.edu.vn",
    "password": "Purchase123!",
}
MANAGER_CREDENTIALS = {
    "email": "manager@vinuni.edu.vn",
    "password": "Manager123!",
}


async def login(client, credentials):
    response = await client.post("/api/v1/auth/login", json=credentials)
    return response


@pytest.mark.asyncio
async def test_login_returns_token_and_procurement_role(client):
    response = await login(client, PROCUREMENT_CREDENTIALS)

    assert response.status_code == 200
    data = response.json()
    assert data["token_type"] == "bearer"
    assert data["access_token"]
    assert data["user"]["role"] == "procurement"
    assert data["user"]["email"] == PROCUREMENT_CREDENTIALS["email"]


@pytest.mark.asyncio
async def test_login_rejects_invalid_credentials(client, caplog):
    # Given
    caplog.set_level(logging.WARNING)

    # When
    response = await login(
        client,
        {"email": PROCUREMENT_CREDENTIALS["email"], "password": "wrong-password"},
    )

    # Then
    audit_logs = [record for record in caplog.records if getattr(record, "event", None) == "authentication_failed"]
    assert response.status_code == 401
    assert response.json()["detail"] == "Email hoặc mật khẩu không đúng."
    assert len(audit_logs) == 1
    assert "wrong-password" not in caplog.text


@pytest.mark.asyncio
async def test_procurement_cannot_access_manager_route(client, caplog):
    # Given
    caplog.set_level(logging.WARNING)
    login_response = await login(client, PROCUREMENT_CREDENTIALS)
    token = login_response.json()["access_token"]

    # When
    response = await client.get("/api/v1/manager/approvals", headers={"Authorization": f"Bearer {token}"})

    # Then
    audit_logs = [record for record in caplog.records if getattr(record, "event", None) == "authorization_denied"]
    assert response.status_code == 403
    assert len(audit_logs) == 1
    assert audit_logs[0].actor_id == "user-procurement-01"
    assert token not in caplog.text


@pytest.mark.asyncio
async def test_manager_cannot_access_procurement_route(client):
    login_response = await login(client, MANAGER_CREDENTIALS)
    token = login_response.json()["access_token"]

    response = await client.get("/api/v1/procurement/workspace", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_logout_revokes_token(client):
    login_response = await login(client, MANAGER_CREDENTIALS)
    token = login_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    logout_response = await client.post("/api/v1/auth/logout", headers=headers)
    session_response = await client.get("/api/v1/auth/session", headers=headers)

    assert logout_response.status_code == 204
    assert session_response.status_code == 401


@pytest.mark.asyncio
async def test_login_frontend_is_served(client):
    response = await client.get("/ui/")

    assert response.status_code == 200
    assert "DotCom" in response.text
    assert 'src="app.js"' in response.text

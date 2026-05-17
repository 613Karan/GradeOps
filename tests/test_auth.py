import pytest


@pytest.mark.asyncio
async def test_register_instructor(client):
    resp = await client.post("/api/v1/auth/register", json={
        "email": "prof@uni.edu",
        "full_name": "Prof Smith",
        "password": "securepass1",
        "role": "instructor",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["email"] == "prof@uni.edu"
    assert data["role"] == "instructor"
    assert "hashed_password" not in data


@pytest.mark.asyncio
async def test_register_duplicate_email(client):
    payload = {"email": "dup@uni.edu", "full_name": "A", "password": "pass1234", "role": "ta"}
    await client.post("/api/v1/auth/register", json=payload)
    resp = await client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 400
    assert "already registered" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_login_success(client):
    await client.post("/api/v1/auth/register", json={
        "email": "user@test.com", "full_name": "U", "password": "pass1234", "role": "ta"
    })
    resp = await client.post("/api/v1/auth/token", data={
        "username": "user@test.com", "password": "pass1234"
    })
    assert resp.status_code == 200
    assert "access_token" in resp.json()
    assert resp.json()["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_wrong_password(client):
    await client.post("/api/v1/auth/register", json={
        "email": "user2@test.com", "full_name": "U", "password": "correctpass", "role": "ta"
    })
    resp = await client.post("/api/v1/auth/token", data={
        "username": "user2@test.com", "password": "wrongpass"
    })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_register_invalid_role(client):
    resp = await client.post("/api/v1/auth/register", json={
        "email": "x@test.com", "full_name": "X", "password": "pass1234", "role": "superadmin"
    })
    assert resp.status_code == 400
    assert "Invalid role" in resp.json()["detail"]

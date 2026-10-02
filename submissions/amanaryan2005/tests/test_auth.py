"""
Auth endpoint tests — signup, login, user isolation
"""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_signup_success(client: AsyncClient):
    resp = await client.post("/api/v1/auth/signup", json={
        "email": "newuser@example.com",
        "username": "newuser",
        "password": "securepass123",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["username"] == "newuser"
    assert data["email"] == "newuser@example.com"
    assert "hashed_password" not in data


@pytest.mark.asyncio
async def test_signup_duplicate_email(client: AsyncClient):
    payload = {"email": "dup@example.com", "username": "dupuser1", "password": "pass12345"}
    await client.post("/api/v1/auth/signup", json=payload)
    resp = await client.post("/api/v1/auth/signup", json={**payload, "username": "dupuser2"})
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient, auth_headers: dict):
    # auth_headers fixture already logs in — just verify we got a token
    assert "Authorization" in auth_headers
    assert auth_headers["Authorization"].startswith("Bearer ")


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient):
    resp = await client.post("/api/v1/auth/login", json={
        "username": "testuser", "password": "wrongpassword"
    })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_me_authenticated(client: AsyncClient, auth_headers: dict):
    resp = await client.get("/api/v1/auth/me", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["username"] == "testuser"


@pytest.mark.asyncio
async def test_get_me_unauthenticated(client: AsyncClient):
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_signup_weak_password(client: AsyncClient):
    resp = await client.post("/api/v1/auth/signup", json={
        "email": "weak@example.com", "username": "weakuser", "password": "short"
    })
    assert resp.status_code == 422

"""Integration tests for authentication endpoints."""

import pytest
from httpx import AsyncClient

from app.db.models.user import User


@pytest.mark.integration
async def test_login_success(client: AsyncClient, admin_user: User):
    """Test successful login with valid credentials."""
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@test.com", "password": "adminpass123"},
    )

    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["email"] == "admin@test.com"
    assert data["role"] == "admin"
    assert "user_id" in data


@pytest.mark.integration
async def test_login_invalid_password(client: AsyncClient, admin_user: User):
    """Test login with incorrect password."""
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@test.com", "password": "wrongpassword"},
    )

    assert response.status_code == 401
    data = response.json()
    assert "detail" in data
    assert "Incorrect email or password" in data["detail"]


@pytest.mark.integration
async def test_login_nonexistent_user(client: AsyncClient):
    """Test login with non-existent email."""
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@test.com", "password": "somepass123"},
    )

    assert response.status_code == 401
    data = response.json()
    assert "detail" in data


@pytest.mark.integration
async def test_login_invalid_email_format(client: AsyncClient):
    """Test login with invalid email format."""
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "not-an-email", "password": "somepass123"},
    )

    assert response.status_code == 422  # Validation error

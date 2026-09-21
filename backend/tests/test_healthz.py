"""Tests for health check endpoints."""

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_check():
    """Test basic health check endpoint."""
    response = client.get("/healthz")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "dronecds-backend"


def test_readiness_check():
    """Test readiness check endpoint."""
    # Note: This will fail if database is not available
    # In CI, we run with a real database container
    response = client.get("/readyz")

    # Should return either 200 (ready) or 503 (not ready)
    assert response.status_code in [200, 503]

    data = response.json()
    assert "status" in data
    assert "checks" in data


def test_root_endpoint():
    """Test root endpoint."""
    response = client.get("/")

    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "dronecds-backend"
    assert "version" in data
    assert "docs" in data

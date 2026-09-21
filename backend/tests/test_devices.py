"""Integration tests for device endpoints."""

import pytest
from httpx import AsyncClient

from app.db.models.device import Device
from app.db.models.user import User


@pytest.mark.integration
async def test_list_devices_admin(client: AsyncClient, admin_token: str, test_device: tuple[Device, str]):
    """Test that admin can list devices."""
    device, _ = test_device

    response = await client.get(
        "/api/v1/devices",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    assert any(d["id"] == str(device.id) for d in data)


@pytest.mark.integration
async def test_list_devices_non_admin_forbidden(client: AsyncClient, viewer_token: str):
    """Test that non-admin users cannot list devices."""
    response = await client.get(
        "/api/v1/devices",
        headers={"Authorization": f"Bearer {viewer_token}"},
    )

    assert response.status_code == 403
    assert "Insufficient permissions" in response.json()["detail"]


@pytest.mark.integration
async def test_list_devices_unauthenticated(client: AsyncClient):
    """Test that unauthenticated requests are rejected."""
    response = await client.get("/api/v1/devices")

    assert response.status_code == 403  # No credentials provided


@pytest.mark.integration
async def test_create_device_admin(client: AsyncClient, admin_token: str):
    """Test device creation by admin."""
    response = await client.post(
        "/api/v1/devices",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"name": "New Drone", "device_type": "drone"},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "New Drone"
    assert data["device_type"] == "drone"
    assert data["status"] == "offline"
    assert "api_key" in data
    assert len(data["api_key"]) == 64  # hex-encoded 32 bytes
    assert "id" in data


@pytest.mark.integration
async def test_create_device_invalid_type(client: AsyncClient, admin_token: str):
    """Test device creation with invalid device_type."""
    response = await client.post(
        "/api/v1/devices",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"name": "Bad Device", "device_type": "airplane"},
    )

    assert response.status_code == 422  # Validation error


@pytest.mark.integration
async def test_device_heartbeat(client: AsyncClient, test_device: tuple[Device, str]):
    """Test device heartbeat endpoint."""
    device, _ = test_device

    response = await client.get(f"/api/v1/devices/{device.id}/heartbeat")

    assert response.status_code == 200
    data = response.json()
    assert data["device_id"] == str(device.id)
    assert data["status"] == "online"
    assert "last_seen_at" in data


@pytest.mark.integration
async def test_device_heartbeat_nonexistent(client: AsyncClient):
    """Test heartbeat for non-existent device."""
    import uuid

    fake_id = uuid.uuid4()
    response = await client.get(f"/api/v1/devices/{fake_id}/heartbeat")

    assert response.status_code == 404

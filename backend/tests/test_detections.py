"""Integration tests for detection endpoints."""

import uuid

import pytest
from httpx import AsyncClient

from app.db.models.device import Device


@pytest.mark.integration
async def test_ingest_detections_success(
    client: AsyncClient, test_device: tuple[Device, str], test_detection_data: dict
):
    """Test successful detection batch ingest."""
    device, api_key = test_device

    response = await client.post(
        "/api/v1/detections",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"detections": [test_detection_data]},
    )

    assert response.status_code == 202
    data = response.json()
    assert data["accepted"] == 1
    assert data["rejected"] == 0
    assert len(data["results"]) == 1
    assert data["results"][0]["status"] == "created"
    assert data["results"][0]["detection_id"] is not None


@pytest.mark.integration
async def test_ingest_detections_idempotency(
    client: AsyncClient, test_device: tuple[Device, str], test_detection_data: dict
):
    """Test that duplicate client_detection_id is handled correctly."""
    device, api_key = test_device

    # First ingest
    response1 = await client.post(
        "/api/v1/detections",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"detections": [test_detection_data]},
    )
    assert response1.status_code == 202
    first_detection_id = response1.json()["results"][0]["detection_id"]

    # Second ingest with same client_detection_id
    response2 = await client.post(
        "/api/v1/detections",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"detections": [test_detection_data]},
    )

    assert response2.status_code == 202
    data = response2.json()
    assert data["accepted"] == 0
    assert data["rejected"] == 1
    assert data["results"][0]["status"] == "duplicate"
    assert data["results"][0]["detection_id"] == first_detection_id


@pytest.mark.integration
async def test_ingest_detections_invalid_api_key(client: AsyncClient, test_detection_data: dict):
    """Test ingest with invalid API key."""
    response = await client.post(
        "/api/v1/detections",
        headers={"Authorization": "Bearer invalid-key"},
        json={"detections": [test_detection_data]},
    )

    assert response.status_code == 401


@pytest.mark.integration
async def test_ingest_detections_validation_error(
    client: AsyncClient, test_device: tuple[Device, str]
):
    """Test ingest with invalid detection data."""
    device, api_key = test_device

    invalid_data = {
        "client_detection_id": str(uuid.uuid4()),
        "latitude": 100.0,  # Invalid: > 90
        "longitude": -122.4194,
        "severity": "high",
        "confidence": 0.95,
        "detected_at": "2026-09-21T10:00:00Z",
    }

    response = await client.post(
        "/api/v1/detections",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"detections": [invalid_data]},
    )

    assert response.status_code == 422  # Validation error


@pytest.mark.integration
async def test_list_detections(
    client: AsyncClient, test_device: tuple[Device, str], test_detection_data: dict
):
    """Test listing detections."""
    device, api_key = test_device

    # First, ingest a detection
    await client.post(
        "/api/v1/detections",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"detections": [test_detection_data]},
    )

    # List detections
    response = await client.get("/api/v1/detections")

    assert response.status_code == 200
    data = response.json()
    assert "detections" in data
    assert "total" in data
    assert data["total"] >= 1
    assert len(data["detections"]) >= 1


@pytest.mark.integration
async def test_list_detections_with_filters(
    client: AsyncClient, test_device: tuple[Device, str], test_detection_data: dict
):
    """Test detection filtering."""
    device, api_key = test_device

    # Ingest detection
    await client.post(
        "/api/v1/detections",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"detections": [test_detection_data]},
    )

    # Filter by severity
    response = await client.get("/api/v1/detections?severity=high")
    assert response.status_code == 200
    data = response.json()
    assert all(d["severity"] == "high" for d in data["detections"])

    # Filter by status
    response = await client.get("/api/v1/detections?status=new")
    assert response.status_code == 200
    data = response.json()
    assert all(d["status"] == "new" for d in data["detections"])


@pytest.mark.integration
async def test_list_detections_bbox_filter(
    client: AsyncClient, test_device: tuple[Device, str], test_detection_data: dict
):
    """Test geographic bounding box filter."""
    device, api_key = test_device

    # Ingest detection at 37.7749, -122.4194 (San Francisco)
    await client.post(
        "/api/v1/detections",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"detections": [test_detection_data]},
    )

    # Query with bbox that includes the detection
    bbox = "-122.5,-37.8,-122.3,37.9"  # min_lon,min_lat,max_lon,max_lat
    response = await client.get(f"/api/v1/detections?bbox={bbox}")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1

    # Query with bbox that excludes the detection
    bbox_exclude = "-120.0,30.0,-119.0,31.0"
    response = await client.get(f"/api/v1/detections?bbox={bbox_exclude}")

    assert response.status_code == 200
    data = response.json()
    assert all(d["client_detection_id"] != test_detection_data["client_detection_id"] for d in data["detections"])


@pytest.mark.integration
async def test_list_detections_pagination(
    client: AsyncClient, test_device: tuple[Device, str]
):
    """Test pagination of detection list."""
    device, api_key = test_device

    # Ingest multiple detections
    detections = [
        {
            "client_detection_id": str(uuid.uuid4()),
            "latitude": 37.7749 + i * 0.01,
            "longitude": -122.4194,
            "severity": "medium",
            "confidence": 0.8,
            "detected_at": "2026-09-21T10:00:00Z",
        }
        for i in range(5)
    ]

    await client.post(
        "/api/v1/detections",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"detections": detections},
    )

    # Page 1 with size 2
    response = await client.get("/api/v1/detections?page=1&page_size=2")
    assert response.status_code == 200
    data = response.json()
    assert data["page"] == 1
    assert data["page_size"] == 2
    assert len(data["detections"]) == 2
    assert data["has_next"] is True

    # Page 2
    response = await client.get("/api/v1/detections?page=2&page_size=2")
    assert response.status_code == 200
    data = response.json()
    assert data["page"] == 2


@pytest.mark.integration
async def test_get_detection_detail(
    client: AsyncClient, test_device: tuple[Device, str], test_detection_data: dict
):
    """Test retrieving single detection with event history."""
    device, api_key = test_device

    # Ingest detection
    ingest_response = await client.post(
        "/api/v1/detections",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"detections": [test_detection_data]},
    )
    detection_id = ingest_response.json()["results"][0]["detection_id"]

    # Get detail
    response = await client.get(f"/api/v1/detections/{detection_id}")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == detection_id
    assert data["severity"] == "high"
    assert data["confidence"] == 0.95
    assert "events" in data
    assert len(data["events"]) >= 1
    assert data["events"][0]["event_type"] == "created"


@pytest.mark.integration
async def test_get_detection_not_found(client: AsyncClient):
    """Test retrieving non-existent detection."""
    fake_id = uuid.uuid4()
    response = await client.get(f"/api/v1/detections/{fake_id}")

    assert response.status_code == 404


@pytest.mark.integration
async def test_update_detection_status_operator(
    client: AsyncClient,
    test_device: tuple[Device, str],
    test_detection_data: dict,
    operator_token: str,
):
    """Test updating detection status as operator."""
    device, api_key = test_device

    # Ingest detection
    ingest_response = await client.post(
        "/api/v1/detections",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"detections": [test_detection_data]},
    )
    detection_id = ingest_response.json()["results"][0]["detection_id"]

    # Update status
    response = await client.patch(
        f"/api/v1/detections/{detection_id}",
        headers={"Authorization": f"Bearer {operator_token}"},
        json={"status": "confirmed", "note": "Verified by operator"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "confirmed"

    # Check event was created
    detail_response = await client.get(f"/api/v1/detections/{detection_id}")
    events = detail_response.json()["events"]
    assert any(e["event_type"] == "status_change" for e in events)


@pytest.mark.integration
async def test_update_detection_status_viewer_forbidden(
    client: AsyncClient,
    test_device: tuple[Device, str],
    test_detection_data: dict,
    viewer_token: str,
):
    """Test that viewer cannot update detection status."""
    device, api_key = test_device

    # Ingest detection
    ingest_response = await client.post(
        "/api/v1/detections",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"detections": [test_detection_data]},
    )
    detection_id = ingest_response.json()["results"][0]["detection_id"]

    # Try to update as viewer
    response = await client.patch(
        f"/api/v1/detections/{detection_id}",
        headers={"Authorization": f"Bearer {viewer_token}"},
        json={"status": "fixed"},
    )

    assert response.status_code == 403
    assert "Insufficient permissions" in response.json()["detail"]

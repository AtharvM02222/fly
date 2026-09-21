"""Device management endpoints."""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import require_admin
from app.api.schemas import (
    DeviceCreate,
    DeviceCreateResponse,
    DeviceHeartbeatResponse,
    DeviceResponse,
)
from app.core.api_key import generate_api_key, hash_api_key
from app.core.logging import get_logger
from app.db.models.device import Device
from app.db.models.user import User
from app.db.session import get_db

logger = get_logger(__name__)
router = APIRouter(prefix="/devices", tags=["devices"])


@router.get("", response_model=list[DeviceResponse])
async def list_devices(
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_admin),
) -> list[DeviceResponse]:
    """
    List all devices.

    Requires admin role.
    """
    result = await db.execute(select(Device).order_by(Device.created_at.desc()))
    devices = result.scalars().all()

    return [DeviceResponse.model_validate(device) for device in devices]


@router.post("", response_model=DeviceCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_device(
    device_data: DeviceCreate,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_admin),
) -> DeviceCreateResponse:
    """
    Create a new device and generate API key.

    Requires admin role.

    Returns the device with plain API key (only shown once).
    """
    # Generate API key
    api_key = generate_api_key()
    api_key_hash = hash_api_key(api_key)

    # Create device
    device = Device(
        name=device_data.name,
        device_type=device_data.device_type,
        api_key_hash=api_key_hash,
        status="offline",
        created_at=datetime.utcnow(),
    )

    db.add(device)
    await db.commit()
    await db.refresh(device)

    logger.info(f"Created device: {device.name} (id={device.id})")

    return DeviceCreateResponse(
        id=device.id,
        name=device.name,
        device_type=device.device_type,
        api_key=api_key,  # Plain key, only shown once
        status=device.status,
        created_at=device.created_at,
    )


@router.get("/{device_id}/heartbeat", response_model=DeviceHeartbeatResponse)
async def device_heartbeat(
    device_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> DeviceHeartbeatResponse:
    """
    Update device last_seen_at timestamp.

    This endpoint can be called by devices to report they are alive.
    Does not require authentication (device_id is sufficient).
    """
    result = await db.execute(select(Device).where(Device.id == device_id))
    device = result.scalar_one_or_none()

    if device is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Device {device_id} not found",
        )

    # Update last_seen_at
    device.last_seen_at = datetime.utcnow()
    device.status = "online"

    await db.commit()
    await db.refresh(device)

    return DeviceHeartbeatResponse(
        device_id=device.id,
        last_seen_at=device.last_seen_at,
        status=device.status,
    )

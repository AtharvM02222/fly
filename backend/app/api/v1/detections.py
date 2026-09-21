"""Detection endpoints for ingest and management."""

import uuid
from datetime import datetime

import geohash as gh
from fastapi import APIRouter, Depends, HTTPException, Query, status
from geoalchemy2.shape import from_shape
from shapely.geometry import Point
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import get_current_device, require_operator_or_admin
from app.api.schemas import (
    DetectionBatchIngestRequest,
    DetectionBatchIngestResponse,
    DetectionDetailResponse,
    DetectionEventResponse,
    DetectionIngestItemResult,
    DetectionListResponse,
    DetectionResponse,
    DetectionStatusUpdate,
)
from app.core.logging import get_logger
from app.db.models.detection import Detection, DetectionEvent
from app.db.models.device import Device
from app.db.models.user import User
from app.db.session import get_db
from app.services.dedup import DeduplicationService
from app.services.notifier import NotificationService

logger = get_logger(__name__)
router = APIRouter(prefix="/detections", tags=["detections"])


@router.post("", response_model=DetectionBatchIngestResponse, status_code=status.HTTP_202_ACCEPTED)
async def ingest_detections(
    batch: DetectionBatchIngestRequest,
    device: Device = Depends(get_current_device),
    db: AsyncSession = Depends(get_db),
) -> DetectionBatchIngestResponse:
    """
    Batch ingest detections from edge device.

    Authenticates via device API key.
    Returns 202 Accepted with per-item status.
    Idempotent on client_detection_id.
    Performs deduplication and creates notifications for new detections.
    """
    # Initialize services
    dedup_service = DeduplicationService()
    notification_service = NotificationService()

    results: list[DetectionIngestItemResult] = []
    accepted = 0
    rejected = 0

    for det_data in batch.detections:
        try:
            # Check if detection already exists (idempotency)
            existing = await db.execute(
                select(Detection).where(
                    Detection.client_detection_id == det_data.client_detection_id
                )
            )
            existing_detection = existing.scalar_one_or_none()

            if existing_detection is not None:
                results.append(
                    DetectionIngestItemResult(
                        client_detection_id=det_data.client_detection_id,
                        status="duplicate",
                        detection_id=existing_detection.id,
                    )
                )
                rejected += 1
                continue

            # Calculate geohash
            geohash = gh.encode(det_data.latitude, det_data.longitude, precision=7)

            # Create PostGIS geography point
            point = Point(det_data.longitude, det_data.latitude)
            location_wkb = from_shape(point, srid=4326)

            # TODO: Upload image to S3 if provided (det_data.image_base64)
            image_url = None

            # Create detection
            detection = Detection(
                client_detection_id=det_data.client_detection_id,
                device_id=device.id,
                location=location_wkb,
                geohash=geohash,
                severity=det_data.severity,
                confidence=det_data.confidence,
                status="new",
                image_url=image_url,
                bbox=det_data.bbox,
                model_version=det_data.model_version,
                detected_at=det_data.detected_at,
                created_at=datetime.utcnow(),
            )

            db.add(detection)
            await db.flush()  # Get detection.id

            # Create "created" event
            event = DetectionEvent(
                detection_id=detection.id,
                event_type="created",
                actor="system",
                note=f"Detection from device {device.name}",
                created_at=datetime.utcnow(),
            )
            db.add(event)

            # Run deduplication
            parent = await dedup_service.check_and_merge(
                detection,
                det_data.latitude,
                det_data.longitude,
                db,
            )

            # Create notification only if NOT merged
            if parent is None:
                await notification_service.notify(detection, db)

            results.append(
                DetectionIngestItemResult(
                    client_detection_id=det_data.client_detection_id,
                    status="created",
                    detection_id=detection.id,
                )
            )
            accepted += 1

        except Exception as e:
            logger.error(
                f"Failed to ingest detection {det_data.client_detection_id}: {e}", exc_info=True
            )
            results.append(
                DetectionIngestItemResult(
                    client_detection_id=det_data.client_detection_id,
                    status="error",
                    error=str(e),
                )
            )
            rejected += 1

    # Commit all successful detections
    await db.commit()

    logger.info(
        f"Batch ingest from device {device.name}: {accepted} accepted, {rejected} rejected"
    )

    return DetectionBatchIngestResponse(
        accepted=accepted,
        rejected=rejected,
        results=results,
    )


@router.get("", response_model=DetectionListResponse)
async def list_detections(
    bbox: str | None = Query(
        None, description="Bounding box: min_lon,min_lat,max_lon,max_lat"
    ),
    status_filter: str | None = Query(None, alias="status"),
    severity: str | None = None,
    device_id: uuid.UUID | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> DetectionListResponse:
    """
    List detections with filters and pagination.

    Supports filtering by:
    - bbox: Bounding box for geographic filtering
    - status: Detection status
    - severity: Detection severity
    - device_id: Filter by device
    """
    query = select(Detection)

    # Apply filters
    if bbox:
        try:
            min_lon, min_lat, max_lon, max_lat = map(float, bbox.split(","))
            # PostGIS bbox filter
            bbox_polygon = func.ST_MakeEnvelope(min_lon, min_lat, max_lon, max_lat, 4326)
            query = query.where(func.ST_Intersects(Detection.location, bbox_polygon))
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid bbox format. Expected: min_lon,min_lat,max_lon,max_lat",
            )

    if status_filter:
        query = query.where(Detection.status == status_filter)

    if severity:
        query = query.where(Detection.severity == severity)

    if device_id:
        query = query.where(Detection.device_id == device_id)

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    # Pagination
    offset = (page - 1) * page_size
    query = query.order_by(Detection.detected_at.desc()).offset(offset).limit(page_size)

    result = await db.execute(query)
    detections = result.scalars().all()

    # Convert to response models
    detection_responses = []
    for det in detections:
        # Extract lat/lon from PostGIS geography
        lat_lon_result = await db.execute(
            select(
                func.ST_Y(func.ST_GeomFromWKB(det.location)),
                func.ST_X(func.ST_GeomFromWKB(det.location)),
            )
        )
        lat, lon = lat_lon_result.one()

        detection_responses.append(
            DetectionResponse(
                id=det.id,
                client_detection_id=det.client_detection_id,
                device_id=det.device_id,
                latitude=lat,
                longitude=lon,
                geohash=det.geohash,
                severity=det.severity,
                confidence=det.confidence,
                status=det.status,
                image_url=det.image_url,
                bbox=det.bbox,
                model_version=det.model_version,
                detected_at=det.detected_at,
                created_at=det.created_at,
                merged_into=det.merged_into,
            )
        )

    has_next = (offset + page_size) < total

    return DetectionListResponse(
        detections=detection_responses,
        total=total,
        page=page,
        page_size=page_size,
        has_next=has_next,
    )


@router.get("/{detection_id}", response_model=DetectionDetailResponse)
async def get_detection(
    detection_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> DetectionDetailResponse:
    """
    Get single detection with full event history.
    """
    result = await db.execute(select(Detection).where(Detection.id == detection_id))
    detection = result.scalar_one_or_none()

    if detection is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Detection {detection_id} not found",
        )

    # Fetch events
    events_result = await db.execute(
        select(DetectionEvent)
        .where(DetectionEvent.detection_id == detection_id)
        .order_by(DetectionEvent.created_at)
    )
    events = events_result.scalars().all()

    # Extract lat/lon
    lat_lon_result = await db.execute(
        select(
            func.ST_Y(func.ST_GeomFromWKB(detection.location)),
            func.ST_X(func.ST_GeomFromWKB(detection.location)),
        )
    )
    lat, lon = lat_lon_result.one()

    return DetectionDetailResponse(
        id=detection.id,
        client_detection_id=detection.client_detection_id,
        device_id=detection.device_id,
        latitude=lat,
        longitude=lon,
        geohash=detection.geohash,
        severity=detection.severity,
        confidence=detection.confidence,
        status=detection.status,
        image_url=detection.image_url,
        bbox=detection.bbox,
        model_version=detection.model_version,
        detected_at=detection.detected_at,
        created_at=detection.created_at,
        merged_into=detection.merged_into,
        events=[DetectionEventResponse.model_validate(event) for event in events],
    )


@router.patch("/{detection_id}", response_model=DetectionResponse)
async def update_detection_status(
    detection_id: uuid.UUID,
    update: DetectionStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator_or_admin),
) -> DetectionResponse:
    """
    Update detection status.

    Requires operator or admin role.
    Creates audit event for status change.
    """
    result = await db.execute(select(Detection).where(Detection.id == detection_id))
    detection = result.scalar_one_or_none()

    if detection is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Detection {detection_id} not found",
        )

    old_status = detection.status
    detection.status = update.status

    # Create status change event
    event = DetectionEvent(
        detection_id=detection.id,
        event_type="status_change",
        actor=current_user.email,
        note=update.note or f"Status changed from {old_status} to {update.status}",
        created_at=datetime.utcnow(),
    )
    db.add(event)

    await db.commit()
    await db.refresh(detection)

    logger.info(
        f"Detection {detection_id} status updated: {old_status} → {update.status} by {current_user.email}"
    )

    # Extract lat/lon
    lat_lon_result = await db.execute(
        select(
            func.ST_Y(func.ST_GeomFromWKB(detection.location)),
            func.ST_X(func.ST_GeomFromWKB(detection.location)),
        )
    )
    lat, lon = lat_lon_result.one()

    return DetectionResponse(
        id=detection.id,
        client_detection_id=detection.client_detection_id,
        device_id=detection.device_id,
        latitude=lat,
        longitude=lon,
        geohash=detection.geohash,
        severity=detection.severity,
        confidence=detection.confidence,
        status=detection.status,
        image_url=detection.image_url,
        bbox=detection.bbox,
        model_version=detection.model_version,
        detected_at=detection.detected_at,
        created_at=detection.created_at,
        merged_into=detection.merged_into,
    )

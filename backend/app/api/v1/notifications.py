"""Notification endpoints for dashboard."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import require_any_user
from app.api.schemas import NotificationListResponse, NotificationResponse
from app.core.logging import get_logger
from app.db.models.detection import Detection
from app.db.models.notification import Notification
from app.db.models.user import User
from app.db.session import get_db

logger = get_logger(__name__)
router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=NotificationListResponse)
async def list_notifications(
    status_filter: str | None = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_any_user),
) -> NotificationListResponse:
    """
    List notifications for dashboard.

    Returns recent notifications with detection summaries.
    """
    query = select(Notification).join(Detection, Notification.detection_id == Detection.id)

    if status_filter:
        query = query.where(Notification.status == status_filter)

    # Order by created_at desc
    query = query.order_by(Notification.created_at.desc()).limit(limit)

    result = await db.execute(query)
    notifications = result.scalars().all()

    # Count unread
    unread_query = select(func.count()).where(Notification.status == "unread")
    unread_result = await db.execute(unread_query)
    unread_count = unread_result.scalar_one()

    # Build response with detection summaries
    notification_responses = []
    for notif in notifications:
        # Get detection
        det_result = await db.execute(
            select(Detection).where(Detection.id == notif.detection_id)
        )
        detection = det_result.scalar_one_or_none()

        if detection:
            # Extract lat/lon
            lat_lon_result = await db.execute(
                select(
                    func.ST_Y(func.ST_GeomFromWKB(detection.location)),
                    func.ST_X(func.ST_GeomFromWKB(detection.location)),
                )
            )
            lat, lon = lat_lon_result.one()

            notification_responses.append(
                NotificationResponse(
                    id=notif.id,
                    detection_id=notif.detection_id,
                    status=notif.status,
                    created_at=notif.created_at,
                    detection_severity=detection.severity,
                    detection_location=(lat, lon),
                )
            )

    total = len(notification_responses)

    return NotificationListResponse(
        notifications=notification_responses,
        unread_count=unread_count,
        total=total,
    )


@router.patch("/{notification_id}/read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_notification_read(
    notification_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_any_user),
) -> None:
    """
    Mark notification as read.
    """
    result = await db.execute(
        select(Notification).where(Notification.id == notification_id)
    )
    notification = result.scalar_one_or_none()

    if notification is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Notification {notification_id} not found",
        )

    notification.status = "read"
    await db.commit()

    logger.info(f"Notification {notification_id} marked as read by {_current_user.email}")

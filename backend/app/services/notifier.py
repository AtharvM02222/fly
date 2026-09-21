"""Notification service with abstract interface and dashboard implementation."""

from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.db.models.detection import Detection
from app.db.models.notification import Notification

logger = get_logger(__name__)


class Notifier(ABC):
    """Abstract notification interface for detection alerts."""

    @abstractmethod
    async def send(self, detection: Detection, db: AsyncSession) -> bool:
        """
        Send notification for a detection.

        Args:
            detection: Detection to notify about
            db: Database session

        Returns:
            True if notification sent successfully, False otherwise
        """
        pass


class DashboardNotifier(Notifier):
    """
    Dashboard-only notification implementation.

    Creates notification records in the database for the dashboard to display.
    Implements:
    - Severity threshold filtering
    - Per-geohash cooldown to prevent duplicate alerts
    """

    def __init__(
        self,
        severity_threshold: str = settings.notification_severity_threshold,
        cooldown_minutes: int = settings.notification_cooldown_minutes,
    ):
        """
        Initialize dashboard notifier.

        Args:
            severity_threshold: Minimum severity to notify (low/medium/high)
            cooldown_minutes: Cooldown period per geohash cell
        """
        self.severity_threshold = severity_threshold
        self.cooldown_minutes = cooldown_minutes

        # Severity ordering for threshold comparison
        self.severity_order = {"low": 1, "medium": 2, "high": 3}

    async def send(self, detection: Detection, db: AsyncSession) -> bool:
        """
        Create dashboard notification for detection.

        Only creates notification if:
        1. Detection is not merged (standalone)
        2. Severity meets or exceeds threshold
        3. No recent notification for same geohash cell (cooldown)

        Args:
            detection: Detection to notify about
            db: Database session

        Returns:
            True if notification created, False if filtered out
        """
        # Check if detection is merged
        if detection.merged_into is not None:
            logger.debug(
                f"Skipping notification for merged detection {detection.id}"
            )
            return False

        # Check severity threshold
        if not self._meets_severity_threshold(detection.severity):
            logger.debug(
                f"Skipping notification for detection {detection.id}: "
                f"severity {detection.severity} below threshold {self.severity_threshold}"
            )
            return False

        # Check cooldown
        if await self._is_in_cooldown(detection.geohash, db):
            logger.info(
                f"Skipping notification for detection {detection.id}: "
                f"geohash {detection.geohash} in cooldown period"
            )
            return False

        # Create notification
        notification = Notification(
            detection_id=detection.id,
            status="unread",
            created_at=datetime.utcnow(),
        )
        db.add(notification)

        logger.info(
            f"Created notification for detection {detection.id} "
            f"(severity={detection.severity}, geohash={detection.geohash})"
        )

        return True

    def _meets_severity_threshold(self, severity: str) -> bool:
        """
        Check if severity meets or exceeds threshold.

        Args:
            severity: Detection severity

        Returns:
            True if severity meets threshold
        """
        severity_value = self.severity_order.get(severity, 0)
        threshold_value = self.severity_order.get(self.severity_threshold, 0)
        return severity_value >= threshold_value

    async def _is_in_cooldown(self, geohash: str, db: AsyncSession) -> bool:
        """
        Check if geohash cell has a recent notification (cooldown period).

        Args:
            geohash: Geohash to check
            db: Database session

        Returns:
            True if in cooldown period (recent notification exists)
        """
        cooldown_threshold = datetime.utcnow() - timedelta(minutes=self.cooldown_minutes)

        # Query for recent notifications in same geohash
        query = (
            select(Notification)
            .join(Detection, Notification.detection_id == Detection.id)
            .where(
                Detection.geohash == geohash,
                Notification.created_at >= cooldown_threshold,
            )
        )

        result = await db.execute(query)
        recent_notification = result.scalar_one_or_none()

        return recent_notification is not None


class NotificationService:
    """
    High-level notification service.

    Coordinates multiple notifiers (currently just dashboard, but designed
    for future extension to Slack, email, etc.).
    """

    def __init__(self, notifiers: list[Notifier] | None = None):
        """
        Initialize notification service.

        Args:
            notifiers: List of notifiers to use (defaults to DashboardNotifier)
        """
        self.notifiers = notifiers or [DashboardNotifier()]

    async def notify(self, detection: Detection, db: AsyncSession) -> int:
        """
        Send notifications for a detection through all notifiers.

        Args:
            detection: Detection to notify about
            db: Database session

        Returns:
            Number of successful notifications sent
        """
        success_count = 0

        for notifier in self.notifiers:
            try:
                if await notifier.send(detection, db):
                    success_count += 1
            except Exception as e:
                logger.error(
                    f"Failed to send notification via {notifier.__class__.__name__}: {e}",
                    exc_info=True,
                )

        return success_count

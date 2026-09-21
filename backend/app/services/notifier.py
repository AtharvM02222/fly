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
    @abstractmethod
    async def send(self, detection: Detection, db: AsyncSession) -> bool:
        pass
class DashboardNotifier(Notifier):
    def __init__(
        self,
        severity_threshold: str = settings.notification_severity_threshold,
        cooldown_minutes: int = settings.notification_cooldown_minutes,
    ):
        self.severity_threshold = severity_threshold
        self.cooldown_minutes = cooldown_minutes
        self.severity_order = {"low": 1, "medium": 2, "high": 3}
    async def send(self, detection: Detection, db: AsyncSession) -> bool:
        if detection.merged_into is not None:
            logger.debug(
                f"Skipping notification for merged detection {detection.id}"
            )
            return False
        if not self._meets_severity_threshold(detection.severity):
            logger.debug(
                f"Skipping notification for detection {detection.id}: "
                f"severity {detection.severity} below threshold {self.severity_threshold}"
            )
            return False
        if await self._is_in_cooldown(detection.geohash, db):
            logger.info(
                f"Skipping notification for detection {detection.id}: "
                f"geohash {detection.geohash} in cooldown period"
            )
            return False
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
        severity_value = self.severity_order.get(severity, 0)
        threshold_value = self.severity_order.get(self.severity_threshold, 0)
        return severity_value >= threshold_value
    async def _is_in_cooldown(self, geohash: str, db: AsyncSession) -> bool:
        cooldown_threshold = datetime.utcnow() - timedelta(minutes=self.cooldown_minutes)
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
    def __init__(self, notifiers: list[Notifier] | None = None):
        self.notifiers = notifiers or [DashboardNotifier()]
    async def notify(self, detection: Detection, db: AsyncSession) -> int:
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

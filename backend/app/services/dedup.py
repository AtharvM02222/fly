import uuid
from datetime import datetime, timedelta
from typing import Optional
import geohash as gh
from geopy.distance import geodesic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.logging import get_logger
from app.db.models.detection import Detection, DetectionEvent
logger = get_logger(__name__)
class DeduplicationService:
    def __init__(
        self,
        geohash_precision: int = settings.dedup_geohash_precision,
        distance_meters: float = settings.dedup_distance_meters,
        time_window_minutes: int = settings.dedup_time_window_minutes,
    ):
        self.geohash_precision = geohash_precision
        self.distance_meters = distance_meters
        self.time_window_minutes = time_window_minutes
    async def check_and_merge(
        self,
        detection: Detection,
        latitude: float,
        longitude: float,
        db: AsyncSession,
    ) -> Optional[Detection]:
        time_threshold = detection.detected_at - timedelta(minutes=self.time_window_minutes)
        query = select(Detection).where(
            Detection.geohash == detection.geohash,
            Detection.detected_at >= time_threshold,
            Detection.detected_at <= detection.detected_at,
            Detection.status != "fixed",
            Detection.merged_into.is_(None),
            Detection.id != detection.id,
        )
        result = await db.execute(query)
        candidates = result.scalars().all()
        if not candidates:
            logger.debug(
                f"No dedup candidates found for detection {detection.id} "
                f"(geohash={detection.geohash})"
            )
            return None
        logger.info(
            f"Found {len(candidates)} dedup candidates for detection {detection.id}"
        )
        for candidate in candidates:
            from sqlalchemy import func
            lat_lon_result = await db.execute(
                select(
                    func.ST_Y(func.ST_GeomFromWKB(candidate.location)),
                    func.ST_X(func.ST_GeomFromWKB(candidate.location)),
                )
            )
            candidate_lat, candidate_lon = lat_lon_result.one()
            distance = geodesic(
                (latitude, longitude),
                (candidate_lat, candidate_lon),
            ).meters
            logger.debug(
                f"Candidate {candidate.id}: distance={distance:.2f}m "
                f"(threshold={self.distance_meters}m)"
            )
            if distance <= self.distance_meters:
                await self._merge_detection(detection, candidate, distance, db)
                return candidate
        logger.info(
            f"No match found for detection {detection.id} within {self.distance_meters}m"
        )
        return None
    async def _merge_detection(
        self,
        new_detection: Detection,
        parent_detection: Detection,
        distance: float,
        db: AsyncSession,
    ) -> None:
        new_detection.merged_into = parent_detection.id
        event = DetectionEvent(
            detection_id=new_detection.id,
            event_type="merged",
            actor="system",
            note=(
                f"Merged into detection {parent_detection.id} "
                f"(distance: {distance:.2f}m, "
                f"geohash: {new_detection.geohash})"
            ),
            created_at=datetime.utcnow(),
        )
        db.add(event)
        logger.info(
            f"Merged detection {new_detection.id} into {parent_detection.id} "
            f"(distance={distance:.2f}m)"
        )
    async def find_merge_chain_root(
        self, detection_id: uuid.UUID, db: AsyncSession
    ) -> uuid.UUID:
        current_id = detection_id
        visited = set()
        while True:
            if current_id in visited:
                logger.error(f"Circular merge chain detected: {visited}")
                return current_id
            visited.add(current_id)
            result = await db.execute(
                select(Detection.merged_into).where(Detection.id == current_id)
            )
            parent_id = result.scalar_one_or_none()
            if parent_id is None:
                return current_id
            current_id = parent_id

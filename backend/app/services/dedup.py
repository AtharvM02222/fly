"""Geospatial deduplication service for detections."""

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
    """
    Deduplication service using geohash + Haversine distance.

    Algorithm:
    1. Calculate geohash at configured precision (default: 7, ~150m cells)
    2. Query existing non-fixed detections in same geohash within time window
    3. For each candidate, calculate Haversine distance
    4. If match found within distance threshold:
       - Set merged_into FK on new detection
       - Create detection_event with type='merged'
    5. Else: detection remains standalone
    """

    def __init__(
        self,
        geohash_precision: int = settings.dedup_geohash_precision,
        distance_meters: float = settings.dedup_distance_meters,
        time_window_minutes: int = settings.dedup_time_window_minutes,
    ):
        """
        Initialize deduplication service.

        Args:
            geohash_precision: Geohash precision (7 = ~150m cells)
            distance_meters: Maximum distance for match (meters)
            time_window_minutes: Time window for matching (minutes)
        """
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
        """
        Check if detection should be merged with an existing one.

        Args:
            detection: The new detection to check
            latitude: Detection latitude
            longitude: Detection longitude
            db: Database session

        Returns:
            The parent detection if merged, None otherwise
        """
        # Calculate time window
        time_threshold = detection.detected_at - timedelta(minutes=self.time_window_minutes)

        # Query candidates: same geohash, within time window, not fixed, not already merged
        query = select(Detection).where(
            Detection.geohash == detection.geohash,
            Detection.detected_at >= time_threshold,
            Detection.detected_at <= detection.detected_at,
            Detection.status != "fixed",
            Detection.merged_into.is_(None),  # Only match against standalone detections
            Detection.id != detection.id,  # Don't match self
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

        # Check each candidate with Haversine distance
        for candidate in candidates:
            # Get candidate lat/lon (we need to query PostGIS)
            from sqlalchemy import func

            lat_lon_result = await db.execute(
                select(
                    func.ST_Y(func.ST_GeomFromWKB(candidate.location)),
                    func.ST_X(func.ST_GeomFromWKB(candidate.location)),
                )
            )
            candidate_lat, candidate_lon = lat_lon_result.one()

            # Calculate distance
            distance = geodesic(
                (latitude, longitude),
                (candidate_lat, candidate_lon),
            ).meters

            logger.debug(
                f"Candidate {candidate.id}: distance={distance:.2f}m "
                f"(threshold={self.distance_meters}m)"
            )

            if distance <= self.distance_meters:
                # Match found! Merge detection into candidate
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
        """
        Merge new detection into existing parent detection.

        Args:
            new_detection: The detection to merge
            parent_detection: The parent detection to merge into
            distance: Distance between detections (meters)
            db: Database session
        """
        # Set merged_into FK
        new_detection.merged_into = parent_detection.id

        # Create merged event
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
        """
        Find the root detection in a merge chain.

        Prevents merge chain issues: if A merges to B, and C tries to merge to A,
        C should merge to B (the root).

        Args:
            detection_id: Detection ID to find root for
            db: Database session

        Returns:
            Root detection ID
        """
        current_id = detection_id
        visited = set()

        while True:
            if current_id in visited:
                # Circular reference detected (shouldn't happen, but guard against it)
                logger.error(f"Circular merge chain detected: {visited}")
                return current_id

            visited.add(current_id)

            result = await db.execute(
                select(Detection.merged_into).where(Detection.id == current_id)
            )
            parent_id = result.scalar_one_or_none()

            if parent_id is None:
                # Found root
                return current_id

            current_id = parent_id

"""Durable write-ahead buffer using SQLite."""

import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from config import BufferConfig


@dataclass
class BufferedDetection:
    """Detection record in buffer."""

    id: int
    client_detection_id: str
    latitude: float
    longitude: float
    severity: str
    confidence: float
    bbox: Optional[dict]
    model_version: str
    detected_at: str  # ISO format
    is_interpolated: bool
    retry_count: int
    uploaded: bool


class DetectionBuffer:
    """
    SQLite-based write-ahead buffer for detections.

    Ensures detections are durably written before uplink attempt.
    Tracks upload status and retry count per detection.
    """

    def __init__(self, config: BufferConfig):
        """
        Initialize buffer.

        Args:
            config: Buffer configuration
        """
        self.config = config
        self.conn: Optional[sqlite3.Connection] = None

    def open(self) -> None:
        """Open database connection and create tables."""
        self.conn = sqlite3.connect(
            self.config.db_path,
            check_same_thread=False,
        )
        self.conn.row_factory = sqlite3.Row

        # Enable WAL mode for better concurrency
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")

        # Create table
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS detections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_detection_id TEXT UNIQUE NOT NULL,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                severity TEXT NOT NULL,
                confidence REAL NOT NULL,
                bbox TEXT,
                model_version TEXT,
                detected_at TEXT NOT NULL,
                is_interpolated INTEGER NOT NULL,
                retry_count INTEGER DEFAULT 0,
                uploaded INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                uploaded_at TEXT
            )
        """)
        self.conn.commit()

    def close(self) -> None:
        """Close database connection."""
        if self.conn:
            self.conn.close()
            self.conn = None

    def write(
        self,
        client_detection_id: str,
        latitude: float,
        longitude: float,
        severity: str,
        confidence: float,
        bbox: Optional[dict],
        model_version: str,
        detected_at: datetime,
        is_interpolated: bool,
    ) -> int:
        """
        Write detection to buffer.

        Args:
            client_detection_id: Unique detection ID
            latitude: Detection latitude
            longitude: Detection longitude
            severity: Severity level
            confidence: Detection confidence
            bbox: Bounding box dict
            model_version: Model version
            detected_at: Detection timestamp
            is_interpolated: GPS interpolation flag

        Returns:
            Buffer record ID

        Raises:
            sqlite3.IntegrityError: If client_detection_id already exists
        """
        if not self.conn:
            raise RuntimeError("Buffer not opened")

        cursor = self.conn.execute(
            """
            INSERT INTO detections (
                client_detection_id,
                latitude,
                longitude,
                severity,
                confidence,
                bbox,
                model_version,
                detected_at,
                is_interpolated,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                client_detection_id,
                latitude,
                longitude,
                severity,
                confidence,
                json.dumps(bbox) if bbox else None,
                model_version,
                detected_at.isoformat(),
                1 if is_interpolated else 0,
                datetime.utcnow().isoformat(),
            ),
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_pending(self, limit: int = 100) -> List[BufferedDetection]:
        """
        Get pending (not uploaded) detections.

        Args:
            limit: Maximum number of detections to return

        Returns:
            List of buffered detections
        """
        if not self.conn:
            raise RuntimeError("Buffer not opened")

        cursor = self.conn.execute(
            """
            SELECT * FROM detections
            WHERE uploaded = 0 AND retry_count < ?
            ORDER BY created_at ASC
            LIMIT ?
            """,
            (self.config.max_retries, limit),
        )

        detections = []
        for row in cursor:
            detections.append(
                BufferedDetection(
                    id=row["id"],
                    client_detection_id=row["client_detection_id"],
                    latitude=row["latitude"],
                    longitude=row["longitude"],
                    severity=row["severity"],
                    confidence=row["confidence"],
                    bbox=json.loads(row["bbox"]) if row["bbox"] else None,
                    model_version=row["model_version"],
                    detected_at=row["detected_at"],
                    is_interpolated=bool(row["is_interpolated"]),
                    retry_count=row["retry_count"],
                    uploaded=bool(row["uploaded"]),
                )
            )

        return detections

    def mark_uploaded(self, buffer_id: int) -> None:
        """
        Mark detection as successfully uploaded.

        Args:
            buffer_id: Buffer record ID
        """
        if not self.conn:
            raise RuntimeError("Buffer not opened")

        self.conn.execute(
            """
            UPDATE detections
            SET uploaded = 1, uploaded_at = ?
            WHERE id = ?
            """,
            (datetime.utcnow().isoformat(), buffer_id),
        )
        self.conn.commit()

    def increment_retry(self, buffer_id: int) -> None:
        """
        Increment retry count for detection.

        Args:
            buffer_id: Buffer record ID
        """
        if not self.conn:
            raise RuntimeError("Buffer not opened")

        self.conn.execute(
            """
            UPDATE detections
            SET retry_count = retry_count + 1
            WHERE id = ?
            """,
            (buffer_id,),
        )
        self.conn.commit()

    def get_stats(self) -> dict:
        """
        Get buffer statistics.

        Returns:
            Dict with pending, uploaded, failed counts
        """
        if not self.conn:
            raise RuntimeError("Buffer not opened")

        cursor = self.conn.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN uploaded = 0 THEN 1 ELSE 0 END) as pending,
                SUM(CASE WHEN uploaded = 1 THEN 1 ELSE 0 END) as uploaded,
                SUM(CASE WHEN retry_count >= ? THEN 1 ELSE 0 END) as failed
            FROM detections
        """, (self.config.max_retries,))

        row = cursor.fetchone()
        return {
            "total": row["total"],
            "pending": row["pending"],
            "uploaded": row["uploaded"],
            "failed": row["failed"],
        }

    def __enter__(self):
        """Context manager entry."""
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()

"""Tests for buffer module."""

import os
import tempfile
import uuid
from datetime import datetime

import pytest

from config import BufferConfig
from pipeline.buffer import DetectionBuffer


@pytest.fixture
def temp_db():
    """Create temporary database file."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.unlink(path)


def test_buffer_open_close(temp_db):
    """Test opening and closing buffer."""
    config = BufferConfig(db_path=temp_db, max_retries=10)
    buffer = DetectionBuffer(config)

    buffer.open()
    assert buffer.conn is not None

    buffer.close()
    assert buffer.conn is None


def test_buffer_context_manager(temp_db):
    """Test buffer as context manager."""
    config = BufferConfig(db_path=temp_db, max_retries=10)

    with DetectionBuffer(config) as buffer:
        assert buffer.conn is not None
        # Write something
        buffer.write(
            client_detection_id=str(uuid.uuid4()),
            latitude=37.7749,
            longitude=-122.4194,
            severity="high",
            confidence=0.95,
            bbox={"x1": 100, "y1": 100, "x2": 200, "y2": 200},
            model_version="v1.0",
            detected_at=datetime.utcnow(),
            is_interpolated=False,
        )

    # Connection should be closed after context
    assert buffer.conn is None


def test_buffer_write_and_read(temp_db):
    """Test writing and reading detections."""
    config = BufferConfig(db_path=temp_db, max_retries=10)

    with DetectionBuffer(config) as buffer:
        client_id = str(uuid.uuid4())
        buffer_id = buffer.write(
            client_detection_id=client_id,
            latitude=37.7749,
            longitude=-122.4194,
            severity="high",
            confidence=0.95,
            bbox={"x1": 100, "y1": 100, "x2": 200, "y2": 200},
            model_version="v1.0",
            detected_at=datetime.utcnow(),
            is_interpolated=False,
        )

        assert buffer_id > 0

        # Read pending
        pending = buffer.get_pending()
        assert len(pending) == 1
        assert pending[0].client_detection_id == client_id
        assert pending[0].severity == "high"
        assert pending[0].uploaded is False


def test_buffer_mark_uploaded(temp_db):
    """Test marking detection as uploaded."""
    config = BufferConfig(db_path=temp_db, max_retries=10)

    with DetectionBuffer(config) as buffer:
        buffer_id = buffer.write(
            client_detection_id=str(uuid.uuid4()),
            latitude=37.7749,
            longitude=-122.4194,
            severity="high",
            confidence=0.95,
            bbox=None,
            model_version="v1.0",
            detected_at=datetime.utcnow(),
            is_interpolated=False,
        )

        # Mark as uploaded
        buffer.mark_uploaded(buffer_id)

        # Should not appear in pending
        pending = buffer.get_pending()
        assert len(pending) == 0


def test_buffer_retry_count(temp_db):
    """Test incrementing retry count."""
    config = BufferConfig(db_path=temp_db, max_retries=3)

    with DetectionBuffer(config) as buffer:
        buffer_id = buffer.write(
            client_detection_id=str(uuid.uuid4()),
            latitude=37.7749,
            longitude=-122.4194,
            severity="high",
            confidence=0.95,
            bbox=None,
            model_version="v1.0",
            detected_at=datetime.utcnow(),
            is_interpolated=False,
        )

        # Increment retry
        buffer.increment_retry(buffer_id)
        pending = buffer.get_pending()
        assert pending[0].retry_count == 1

        # Increment again
        buffer.increment_retry(buffer_id)
        pending = buffer.get_pending()
        assert pending[0].retry_count == 2

        # Increment to max
        buffer.increment_retry(buffer_id)
        pending = buffer.get_pending()
        # Should still appear (retry_count=3, max_retries=3)
        assert len(pending) == 1

        # One more increment
        buffer.increment_retry(buffer_id)
        pending = buffer.get_pending()
        # Should not appear anymore (retry_count=4 >= max_retries=3)
        assert len(pending) == 0


def test_buffer_stats(temp_db):
    """Test buffer statistics."""
    config = BufferConfig(db_path=temp_db, max_retries=3)

    with DetectionBuffer(config) as buffer:
        # Write 3 detections
        id1 = buffer.write(
            client_detection_id=str(uuid.uuid4()),
            latitude=37.7749,
            longitude=-122.4194,
            severity="high",
            confidence=0.95,
            bbox=None,
            model_version="v1.0",
            detected_at=datetime.utcnow(),
            is_interpolated=False,
        )

        id2 = buffer.write(
            client_detection_id=str(uuid.uuid4()),
            latitude=37.7750,
            longitude=-122.4195,
            severity="medium",
            confidence=0.85,
            bbox=None,
            model_version="v1.0",
            detected_at=datetime.utcnow(),
            is_interpolated=True,
        )

        id3 = buffer.write(
            client_detection_id=str(uuid.uuid4()),
            latitude=37.7751,
            longitude=-122.4196,
            severity="low",
            confidence=0.75,
            bbox=None,
            model_version="v1.0",
            detected_at=datetime.utcnow(),
            is_interpolated=False,
        )

        # Mark one as uploaded
        buffer.mark_uploaded(id1)

        # Fail one beyond max retries
        for _ in range(4):
            buffer.increment_retry(id2)

        stats = buffer.get_stats()
        assert stats["total"] == 3
        assert stats["uploaded"] == 1
        assert stats["pending"] == 1  # id3
        assert stats["failed"] == 1  # id2


def test_buffer_duplicate_client_id(temp_db):
    """Test that duplicate client_detection_id raises error."""
    config = BufferConfig(db_path=temp_db, max_retries=10)

    with DetectionBuffer(config) as buffer:
        client_id = str(uuid.uuid4())

        # Write first
        buffer.write(
            client_detection_id=client_id,
            latitude=37.7749,
            longitude=-122.4194,
            severity="high",
            confidence=0.95,
            bbox=None,
            model_version="v1.0",
            detected_at=datetime.utcnow(),
            is_interpolated=False,
        )

        # Try to write again with same client_id
        with pytest.raises(Exception):  # sqlite3.IntegrityError
            buffer.write(
                client_detection_id=client_id,
                latitude=37.7749,
                longitude=-122.4194,
                severity="high",
                confidence=0.95,
                bbox=None,
                model_version="v1.0",
                detected_at=datetime.utcnow(),
                is_interpolated=False,
            )

"""Tests for tracker module."""

import pytest

from config import TrackerConfig
from pipeline.detector import Detection
from pipeline.tracker import Tracker, iou


def test_iou_full_overlap():
    """Test IoU with fully overlapping boxes."""
    bbox1 = (0, 0, 100, 100)
    bbox2 = (0, 0, 100, 100)
    assert iou(bbox1, bbox2) == 1.0


def test_iou_no_overlap():
    """Test IoU with no overlap."""
    bbox1 = (0, 0, 100, 100)
    bbox2 = (200, 200, 300, 300)
    assert iou(bbox1, bbox2) == 0.0


def test_iou_partial_overlap():
    """Test IoU with partial overlap."""
    bbox1 = (0, 0, 100, 100)
    bbox2 = (50, 50, 150, 150)
    
    # Intersection: 50x50 = 2500
    # Union: 10000 + 10000 - 2500 = 17500
    # IoU: 2500 / 17500 ≈ 0.143
    result = iou(bbox1, bbox2)
    assert 0.14 < result < 0.15


def test_tracker_single_detection():
    """Test tracker with single detection per frame."""
    config = TrackerConfig(iou_threshold=0.3, min_hits=3, max_age=30)
    tracker = Tracker(config)

    detection = Detection(
        bbox_xyxy=(100, 100, 200, 200),
        confidence=0.9,
        class_id=0,
        class_name="pothole",
    )

    # Frame 1: New detection
    tracks = tracker.update([detection])
    assert len(tracks) == 0  # Not confirmed yet (min_hits=3)

    # Frame 2: Same detection
    tracks = tracker.update([detection])
    assert len(tracks) == 0  # Still not confirmed

    # Frame 3: Same detection
    tracks = tracker.update([detection])
    assert len(tracks) == 1  # Now confirmed!
    assert tracks[0].hits == 3
    assert tracks[0].confirmed is True


def test_tracker_flicker_rejection():
    """Test that single-frame detections (flicker) don't get confirmed."""
    config = TrackerConfig(iou_threshold=0.3, min_hits=3, max_age=30)
    tracker = Tracker(config)

    detection = Detection(
        bbox_xyxy=(100, 100, 200, 200),
        confidence=0.9,
        class_id=0,
        class_name="pothole",
    )

    # Frame 1: Detection appears
    tracks = tracker.update([detection])
    assert len(tracks) == 0

    # Frame 2: Detection disappears
    tracks = tracker.update([])
    assert len(tracks) == 0

    # Frame 3: Detection reappears
    tracks = tracker.update([detection])
    assert len(tracks) == 0  # Treated as new detection, not confirmed


def test_tracker_max_age():
    """Test that tracks are removed after max_age frames without update."""
    config = TrackerConfig(iou_threshold=0.3, min_hits=2, max_age=5)
    tracker = Tracker(config)

    detection = Detection(
        bbox_xyxy=(100, 100, 200, 200),
        confidence=0.9,
        class_id=0,
        class_name="pothole",
    )

    # Confirm track
    tracker.update([detection])
    tracks = tracker.update([detection])
    assert len(tracks) == 1

    # Stop sending detection
    for _ in range(5):
        tracks = tracker.update([])

    # Track should still exist (age=5, max_age=5)
    assert len(tracker.tracks) == 1

    # One more frame without detection
    tracks = tracker.update([])
    # Track should be removed (age=6 > max_age=5)
    assert len(tracker.tracks) == 0


def test_tracker_multiple_objects():
    """Test tracking multiple objects simultaneously."""
    config = TrackerConfig(iou_threshold=0.3, min_hits=2, max_age=30)
    tracker = Tracker(config)

    detection1 = Detection(
        bbox_xyxy=(100, 100, 200, 200),
        confidence=0.9,
        class_id=0,
        class_name="pothole",
    )

    detection2 = Detection(
        bbox_xyxy=(300, 300, 400, 400),
        confidence=0.85,
        class_id=0,
        class_name="pothole",
    )

    # Frame 1: Both detections
    tracker.update([detection1, detection2])

    # Frame 2: Both detections
    tracks = tracker.update([detection1, detection2])

    # Both should be confirmed
    assert len(tracks) == 2


def test_tracker_moving_object():
    """Test tracking object that moves across frames."""
    config = TrackerConfig(iou_threshold=0.3, min_hits=2, max_age=30)
    tracker = Tracker(config)

    # Object moves slightly each frame (high IoU overlap)
    detections = [
        Detection(
            bbox_xyxy=(100 + i * 10, 100, 200 + i * 10, 200),
            confidence=0.9,
            class_id=0,
            class_name="pothole",
        )
        for i in range(5)
    ]

    for detection in detections:
        tracks = tracker.update([detection])

    # Should have one confirmed track (same object moving)
    assert len(tracks) == 1
    assert tracks[0].hits >= 2

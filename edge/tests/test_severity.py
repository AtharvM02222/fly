"""Tests for severity module."""

import pytest

from config import SeverityConfig, SeverityThresholdsConfig
from pipeline.severity import bbox_area, calculate_severity


def test_bbox_area():
    """Test bounding box area calculation."""
    bbox = (100, 100, 200, 200)
    area = bbox_area(bbox)
    assert area == 10000  # 100 * 100


def test_calculate_severity_low():
    """Test low severity classification."""
    config = SeverityConfig(
        camera_height_m=2.0,
        camera_angle_deg=45,
        thresholds=SeverityThresholdsConfig(
            low_max_area=5000, medium_max_area=15000, confidence_multiplier=1.0
        ),
    )

    # Small area, high confidence
    severity = calculate_severity(
        bbox_area=3000,
        confidence=0.95,
        config=config,
    )
    assert severity == "low"


def test_calculate_severity_medium():
    """Test medium severity classification."""
    config = SeverityConfig(
        camera_height_m=2.0,
        camera_angle_deg=45,
        thresholds=SeverityThresholdsConfig(
            low_max_area=5000, medium_max_area=15000, confidence_multiplier=1.0
        ),
    )

    # Medium area
    severity = calculate_severity(
        bbox_area=10000,
        confidence=0.9,
        config=config,
    )
    assert severity == "medium"


def test_calculate_severity_high():
    """Test high severity classification."""
    config = SeverityConfig(
        camera_height_m=2.0,
        camera_angle_deg=45,
        thresholds=SeverityThresholdsConfig(
            low_max_area=5000, medium_max_area=15000, confidence_multiplier=1.0
        ),
    )

    # Large area
    severity = calculate_severity(
        bbox_area=20000,
        confidence=0.95,
        config=config,
    )
    assert severity == "high"


def test_calculate_severity_confidence_multiplier():
    """Test confidence multiplier effect on severity."""
    config = SeverityConfig(
        camera_height_m=2.0,
        camera_angle_deg=45,
        thresholds=SeverityThresholdsConfig(
            low_max_area=5000, medium_max_area=15000, confidence_multiplier=2.0
        ),
    )

    # Area of 4000 with confidence 0.8
    # Adjusted: 4000 * (0.8 * 2.0) = 6400 (medium)
    severity = calculate_severity(
        bbox_area=4000,
        confidence=0.8,
        config=config,
    )
    assert severity == "medium"


def test_calculate_severity_boundary_low_to_medium():
    """Test boundary between low and medium severity."""
    config = SeverityConfig(
        camera_height_m=2.0,
        camera_angle_deg=45,
        thresholds=SeverityThresholdsConfig(
            low_max_area=5000, medium_max_area=15000, confidence_multiplier=1.0
        ),
    )

    # Just below threshold
    severity = calculate_severity(
        bbox_area=4999,
        confidence=1.0,
        config=config,
    )
    assert severity == "low"

    # At threshold
    severity = calculate_severity(
        bbox_area=5000,
        confidence=1.0,
        config=config,
    )
    assert severity == "low"

    # Just above threshold
    severity = calculate_severity(
        bbox_area=5001,
        confidence=1.0,
        config=config,
    )
    assert severity == "medium"

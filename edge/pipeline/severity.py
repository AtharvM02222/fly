"""Severity classification for detections."""

from config import SeverityConfig


def calculate_severity(
    bbox_area: float,
    confidence: float,
    config: SeverityConfig,
) -> str:
    """
    Calculate detection severity based on bbox area and confidence.

    Pure function with no side effects. Formula uses camera geometry
    from config to normalize bbox area.

    Args:
        bbox_area: Bounding box area in pixels (x2-x1) * (y2-y1)
        confidence: Detection confidence [0, 1]
        config: Severity configuration

    Returns:
        Severity level: 'low', 'medium', or 'high'
    """
    # Apply confidence multiplier
    adjusted_area = bbox_area * (confidence * config.thresholds.confidence_multiplier)

    # Classify based on thresholds
    if adjusted_area <= config.thresholds.low_max_area:
        return "low"
    elif adjusted_area <= config.thresholds.medium_max_area:
        return "medium"
    else:
        return "high"


def bbox_area(bbox_xyxy: tuple[float, float, float, float]) -> float:
    """
    Calculate bbox area.

    Args:
        bbox_xyxy: Bounding box (x1, y1, x2, y2)

    Returns:
        Area in pixels squared
    """
    x1, y1, x2, y2 = bbox_xyxy
    width = x2 - x1
    height = y2 - y1
    return width * height

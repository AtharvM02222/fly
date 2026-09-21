from config import SeverityConfig
def calculate_severity(
    bbox_area: float,
    confidence: float,
    config: SeverityConfig,
) -> str:
    adjusted_area = bbox_area * (confidence * config.thresholds.confidence_multiplier)
    if adjusted_area <= config.thresholds.low_max_area:
        return "low"
    elif adjusted_area <= config.thresholds.medium_max_area:
        return "medium"
    else:
        return "high"
def bbox_area(bbox_xyxy: tuple[float, float, float, float]) -> float:
    x1, y1, x2, y2 = bbox_xyxy
    width = x2 - x1
    height = y2 - y1
    return width * height

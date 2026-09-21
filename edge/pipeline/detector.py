"""Detection interface and implementations."""

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List

import numpy as np

from config import DetectorConfig


@dataclass
class Detection:
    """Single detection result."""

    bbox_xyxy: tuple[float, float, float, float]  # (x1, y1, x2, y2) in original frame coordinates
    confidence: float
    class_id: int
    class_name: str


class DetectorInterface(ABC):
    """Abstract detector interface."""

    @abstractmethod
    def detect(self, frame: np.ndarray) -> List[Detection]:
        """
        Run detection on a frame.

        Args:
            frame: BGR frame (HxWx3 uint8)

        Returns:
            List of detections (empty list if nothing found, never None)
        """
        pass

    @abstractmethod
    def get_model_version(self) -> str:
        """Get model version identifier."""
        pass


class MockDetector(DetectorInterface):
    """
    Mock detector for testing without real model weights.

    Returns synthetic detections at configurable intervals.
    Useful for end-to-end pipeline testing.
    """

    def __init__(
        self,
        config: DetectorConfig,
        detection_interval: int = 10,
        detection_probability: float = 0.3,
    ):
        """
        Initialize mock detector.

        Args:
            config: Detector configuration
            detection_interval: Emit detection every N frames
            detection_probability: Probability of detection per frame
        """
        self.config = config
        self.detection_interval = detection_interval
        self.detection_probability = detection_probability
        self.frame_count = 0
        self.model_version = "mock-v1.0"

    def detect(self, frame: np.ndarray) -> List[Detection]:
        """
        Generate synthetic detections.

        Args:
            frame: BGR frame (HxWx3 uint8)

        Returns:
            List of synthetic detections
        """
        self.frame_count += 1

        # Emit detection every N frames or with probability P
        if (
            self.frame_count % self.detection_interval == 0
            or np.random.random() < self.detection_probability
        ):
            h, w = frame.shape[:2]

            # Generate random bbox
            x1 = np.random.randint(0, w - 200)
            y1 = np.random.randint(0, h - 200)
            x2 = x1 + np.random.randint(100, 200)
            y2 = y1 + np.random.randint(100, 200)

            # Generate confidence above threshold
            confidence = np.random.uniform(
                self.config.confidence_threshold, 1.0
            )

            return [
                Detection(
                    bbox_xyxy=(float(x1), float(y1), float(x2), float(y2)),
                    confidence=float(confidence),
                    class_id=0,
                    class_name="pothole",
                )
            ]

        return []

    def get_model_version(self) -> str:
        """Get model version."""
        return self.model_version


class RealDetector(DetectorInterface):
    """
    Real YOLOv8n detector (Phase 5).

    This is a placeholder - will be implemented in Phase 5 with:
    - ONNX Runtime or TensorRT backend
    - Letterbox preprocessing
    - NMS postprocessing
    - Coordinate transformation
    - Latency tracking
    """

    def __init__(self, config: DetectorConfig):
        """Initialize real detector."""
        self.config = config
        raise NotImplementedError(
            "RealDetector will be implemented in Phase 5. Use MockDetector for now."
        )

    def detect(self, frame: np.ndarray) -> List[Detection]:
        """Run real detection."""
        raise NotImplementedError("Phase 5")

    def get_model_version(self) -> str:
        """Get model version."""
        return self.config.model_version

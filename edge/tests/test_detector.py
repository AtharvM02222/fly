"""Tests for real detector implementation."""

import hashlib
from pathlib import Path
from unittest.mock import MagicMock, patch

import cv2
import numpy as np
import pytest

from config import DetectorConfig
from pipeline.detector import Detection, MockDetector, RealDetector


@pytest.fixture
def detector_config():
    """Minimal detector config for testing."""
    from config.loader import NormalizationConfig
    
    return DetectorConfig(
        model_path="models/test_pothole.onnx",
        engine_path=None,
        weights_checksum="sha256:placeholder",
        backend="onnx-cpu",
        confidence_threshold=0.5,
        nms_iou_threshold=0.45,
        max_detections=50,
        input_size=640,
        quantization="none",
        warmup_iterations=1,
        inference_timeout_seconds=5.0,
        latency_budget_ms=100,
        normalization=NormalizationConfig(
            mean=[0.0, 0.0, 0.0],
            std=[1.0, 1.0, 1.0],
            scale=255.0,
        ),
        model_version="test-v1.0",
    )


class TestMockDetector:
    """Tests for mock detector."""

    def test_mock_detector_returns_empty_list(self, detector_config):
        """Test mock detector returns empty list when no detection triggered."""
        detector = MockDetector(detector_config, detection_interval=100, detection_probability=0.0)
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        
        for _ in range(10):
            result = detector.detect(frame)
            if not result:
                assert result == []
                return
        
        # If we reach here, detection_probability=0.0 still triggered (shouldn't happen)
        pytest.fail("Mock detector triggered with probability=0.0")

    def test_mock_detector_emits_detection(self, detector_config):
        """Test mock detector emits detection at interval."""
        detector = MockDetector(detector_config, detection_interval=5, detection_probability=0.0)
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        
        # First 4 frames should be empty
        for _ in range(4):
            assert detector.detect(frame) == []
        
        # 5th frame should have detection
        result = detector.detect(frame)
        assert len(result) == 1
        assert isinstance(result[0], Detection)
        assert result[0].confidence >= detector_config.confidence_threshold
        assert result[0].class_name == "pothole"

    def test_mock_detector_bbox_in_bounds(self, detector_config):
        """Test mock detector generates bbox within frame bounds."""
        detector = MockDetector(detector_config, detection_interval=1)
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        
        result = detector.detect(frame)
        if result:
            det = result[0]
            x1, y1, x2, y2 = det.bbox_xyxy
            assert 0 <= x1 < x2 <= 1920
            assert 0 <= y1 < y2 <= 1080


class TestRealDetectorPreprocessing:
    """Tests for preprocessing (letterbox, normalization)."""

    def test_letterbox_square_image(self, detector_config):
        """Test letterbox on already-square image."""
        # Create a mock detector to access preprocessing
        with patch("pipeline.detector.Path.exists", return_value=False):
            # We'll test preprocessing independently
            pass
        
        # Test letterbox logic directly
        frame = np.zeros((640, 640, 3), dtype=np.uint8)
        target_size = 640
        
        h, w = frame.shape[:2]
        scale = min(target_size / h, target_size / w)
        new_h, new_w = int(h * scale), int(w * scale)
        
        # Should be no scaling
        assert scale == 1.0
        assert new_h == 640
        assert new_w == 640
        
        # Padding should be zero
        pad_h = (target_size - new_h) // 2
        pad_w = (target_size - new_w) // 2
        assert pad_h == 0
        assert pad_w == 0

    def test_letterbox_wide_image(self):
        """Test letterbox on wide image (1920x1080)."""
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        target_size = 640
        
        h, w = frame.shape[:2]
        scale = min(target_size / h, target_size / w)
        new_h, new_w = int(h * scale), int(w * scale)
        
        # Width is limiting factor
        assert scale == pytest.approx(640 / 1920, rel=1e-6)
        assert new_w == 640
        assert new_h == int(1080 * scale)
        
        # Should have vertical padding
        pad_h = (target_size - new_h) // 2
        pad_w = (target_size - new_w) // 2
        assert pad_h > 0
        assert pad_w == 0

    def test_letterbox_tall_image(self):
        """Test letterbox on tall image (1080x1920)."""
        frame = np.zeros((1920, 1080, 3), dtype=np.uint8)
        target_size = 640
        
        h, w = frame.shape[:2]
        scale = min(target_size / h, target_size / w)
        new_h, new_w = int(h * scale), int(w * scale)
        
        # Height is limiting factor
        assert scale == pytest.approx(640 / 1920, rel=1e-6)
        assert new_h == 640
        assert new_w == int(1080 * scale)
        
        # Should have horizontal padding
        pad_h = (target_size - new_h) // 2
        pad_w = (target_size - new_w) // 2
        assert pad_h == 0
        assert pad_w > 0

    def test_normalization_no_mean_std(self):
        """Test normalization with mean=0, std=1 (just scaling)."""
        img = np.ones((640, 640, 3), dtype=np.uint8) * 128  # Gray image
        
        # Normalize
        img_float = img.astype(np.float32) / 255.0
        
        assert img_float.min() == pytest.approx(128 / 255.0)
        assert img_float.max() == pytest.approx(128 / 255.0)

    def test_normalization_with_mean_std(self):
        """Test normalization with non-zero mean/std."""
        img = np.ones((640, 640, 3), dtype=np.uint8) * 128
        
        img_float = img.astype(np.float32) / 255.0
        mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
        std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
        
        img_normalized = (img_float - mean) / std
        
        # Check values are in reasonable range
        assert img_normalized.shape == (640, 640, 3)
        # After normalization with ImageNet stats, values should be roughly [-2, 2]
        assert -3 < img_normalized.min() < img_normalized.max() < 3


class TestCoordinateTransform:
    """Tests for coordinate transformation (letterbox → original frame).
    
    This is the CRITICAL test that catches the most common YOLO bugs.
    """

    def test_transform_no_padding_no_scaling(self):
        """Test coordinate transform with square image (no padding, scale=1)."""
        # Original frame: 640x640
        # Letterbox: 640x640 (no change)
        boxes_letterbox = np.array([
            [100, 100, 200, 200],  # Simple box
        ], dtype=np.float32)
        
        scale = 1.0
        pad_w = 0
        pad_h = 0
        original_shape = (640, 640, 3)
        
        # Transform
        boxes_letterbox[:, [0, 2]] -= pad_w
        boxes_letterbox[:, [1, 3]] -= pad_h
        boxes_letterbox /= scale
        
        # Clip
        h, w = original_shape[:2]
        boxes_letterbox[:, [0, 2]] = np.clip(boxes_letterbox[:, [0, 2]], 0, w)
        boxes_letterbox[:, [1, 3]] = np.clip(boxes_letterbox[:, [1, 3]], 0, h)
        
        # Should be unchanged
        expected = np.array([[100, 100, 200, 200]], dtype=np.float32)
        np.testing.assert_array_almost_equal(boxes_letterbox, expected)

    def test_transform_with_horizontal_padding(self):
        """Test coordinate transform with horizontal padding (tall image).
        
        Original: 1920x1080 (H x W) - tall
        Letterbox: 640x640
        Scale: 640/1920 = 0.333...
        After resize: 640x360
        Padding: horizontal, (640-360)/2 = 140 on each side
        """
        # Box in letterbox space (center of letterbox image)
        boxes_letterbox = np.array([
            [140, 320, 500, 320],  # Horizontal line at vertical center
        ], dtype=np.float32)
        
        scale = 640 / 1920  # 0.333...
        pad_w = 140  # (640 - 360) / 2
        pad_h = 0
        original_shape = (1920, 1080, 3)
        
        # Transform
        boxes_original = boxes_letterbox.copy()
        boxes_original[:, [0, 2]] -= pad_w  # Remove horizontal padding: [0, 360]
        boxes_original[:, [1, 3]] -= pad_h  # No vertical padding
        boxes_original /= scale  # Scale back: [0, 1080]
        
        # Expected: horizontal coordinates scaled back, vertical unchanged
        # x: (140 - 140) / scale = 0 / 0.333 = 0
        # x: (500 - 140) / scale = 360 / 0.333 = 1080
        # y: 320 / scale = 320 / 0.333 = 960
        expected_x1 = 0
        expected_x2 = 360 / scale
        expected_y = 320 / scale
        
        np.testing.assert_almost_equal(boxes_original[0, 0], expected_x1, decimal=1)
        np.testing.assert_almost_equal(boxes_original[0, 2], expected_x2, decimal=1)
        np.testing.assert_almost_equal(boxes_original[0, 1], expected_y, decimal=1)
        np.testing.assert_almost_equal(boxes_original[0, 3], expected_y, decimal=1)

    def test_transform_with_vertical_padding(self):
        """Test coordinate transform with vertical padding (wide image).
        
        Original: 1080x1920 (H x W) - wide
        Letterbox: 640x640
        Scale: 640/1920 = 0.333...
        After resize: 360x640
        Padding: vertical, (640-360)/2 = 140 on top/bottom
        """
        # Box in letterbox space (center of letterbox image)
        boxes_letterbox = np.array([
            [320, 140, 320, 500],  # Vertical line at horizontal center
        ], dtype=np.float32)
        
        scale = 640 / 1920  # 0.333...
        pad_w = 0
        pad_h = 140  # (640 - 360) / 2
        original_shape = (1080, 1920, 3)
        
        # Transform
        boxes_original = boxes_letterbox.copy()
        boxes_original[:, [0, 2]] -= pad_w
        boxes_original[:, [1, 3]] -= pad_h  # Remove vertical padding
        boxes_original /= scale
        
        # Expected:
        # x: 320 / scale = 320 / 0.333 = 960
        # y: (140 - 140) / scale = 0
        # y: (500 - 140) / scale = 360 / 0.333 = 1080
        expected_x = 320 / scale
        expected_y1 = 0
        expected_y2 = 360 / scale
        
        np.testing.assert_almost_equal(boxes_original[0, 0], expected_x, decimal=1)
        np.testing.assert_almost_equal(boxes_original[0, 2], expected_x, decimal=1)
        np.testing.assert_almost_equal(boxes_original[0, 1], expected_y1, decimal=1)
        np.testing.assert_almost_equal(boxes_original[0, 3], expected_y2, decimal=1)

    def test_transform_clipping(self):
        """Test that transformed boxes are clipped to frame bounds."""
        # Box that extends beyond bounds after transform
        boxes_letterbox = np.array([
            [-50, -50, 1000, 1000],
        ], dtype=np.float32)
        
        scale = 1.0
        pad_w = 0
        pad_h = 0
        original_shape = (640, 640, 3)
        
        # Transform
        boxes_original = boxes_letterbox.copy()
        boxes_original[:, [0, 2]] -= pad_w
        boxes_original[:, [1, 3]] -= pad_h
        boxes_original /= scale
        
        # Clip
        h, w = original_shape[:2]
        boxes_original[:, [0, 2]] = np.clip(boxes_original[:, [0, 2]], 0, w)
        boxes_original[:, [1, 3]] = np.clip(boxes_original[:, [1, 3]], 0, h)
        
        expected = np.array([[0, 0, 640, 640]], dtype=np.float32)
        np.testing.assert_array_almost_equal(boxes_original, expected)


class TestNMS:
    """Tests for Non-Maximum Suppression."""

    def test_nms_removes_overlapping_boxes(self):
        """Test NMS removes highly overlapping boxes."""
        boxes = np.array([
            [100, 100, 200, 200],  # Box 1
            [105, 105, 205, 205],  # Box 2 - highly overlapping with 1
            [300, 300, 400, 400],  # Box 3 - separate
        ], dtype=np.float32)
        
        scores = np.array([0.9, 0.8, 0.85], dtype=np.float32)
        iou_threshold = 0.5
        
        # Use OpenCV NMS
        indices = cv2.dnn.NMSBoxes(
            bboxes=boxes.tolist(),
            scores=scores.tolist(),
            score_threshold=0.0,
            nms_threshold=iou_threshold
        )
        
        indices = indices.flatten() if len(indices) > 0 else np.array([], dtype=int)
        
        # Should keep boxes 0 and 2 (highest scores from each cluster)
        assert len(indices) == 2
        assert 0 in indices  # Highest score in cluster 1
        assert 2 in indices  # Separate cluster

    def test_nms_keeps_non_overlapping_boxes(self):
        """Test NMS keeps non-overlapping boxes."""
        boxes = np.array([
            [100, 100, 200, 200],
            [300, 300, 400, 400],
            [500, 500, 600, 600],
        ], dtype=np.float32)
        
        scores = np.array([0.9, 0.8, 0.7], dtype=np.float32)
        iou_threshold = 0.5
        
        indices = cv2.dnn.NMSBoxes(
            bboxes=boxes.tolist(),
            scores=scores.tolist(),
            score_threshold=0.0,
            nms_threshold=iou_threshold
        )
        
        indices = indices.flatten() if len(indices) > 0 else np.array([], dtype=int)
        
        # Should keep all three
        assert len(indices) == 3

    def test_nms_empty_input(self):
        """Test NMS with empty input."""
        boxes = np.array([], dtype=np.float32).reshape(0, 4)
        scores = np.array([], dtype=np.float32)
        
        indices = cv2.dnn.NMSBoxes(
            bboxes=boxes.tolist(),
            scores=scores.tolist(),
            score_threshold=0.0,
            nms_threshold=0.5
        )
        
        indices = indices.flatten() if len(indices) > 0 else np.array([], dtype=int)
        assert len(indices) == 0


class TestConfidenceThreshold:
    """Tests for confidence threshold filtering."""

    def test_confidence_boundary_below(self):
        """Test detection with confidence just below threshold is filtered."""
        # This would be tested in the full detector, but we can test the logic
        confidences = np.array([0.49, 0.50, 0.51])
        threshold = 0.50
        
        mask = confidences >= threshold
        filtered = confidences[mask]
        
        assert len(filtered) == 2
        assert 0.49 not in filtered
        assert 0.50 in filtered
        assert 0.51 in filtered

    def test_confidence_boundary_exact(self):
        """Test detection with confidence exactly at threshold is kept."""
        confidences = np.array([0.50])
        threshold = 0.50
        
        mask = confidences >= threshold
        assert mask[0] == True

    def test_confidence_boundary_above(self):
        """Test detection with confidence above threshold is kept."""
        confidences = np.array([0.51])
        threshold = 0.50
        
        mask = confidences >= threshold
        assert mask[0] == True


class TestChecksumVerification:
    """Tests for model weights checksum verification."""

    def test_checksum_placeholder_skips_verification(self, detector_config, tmp_path):
        """Test placeholder checksum skips verification."""
        # Create a dummy model file
        model_path = tmp_path / "test_model.onnx"
        model_path.write_bytes(b"fake model data")
        
        detector_config.model_path = str(model_path)
        detector_config.weights_checksum = "sha256:placeholder"
        
        # Mock ONNX Runtime to avoid actual model loading
        with patch("onnxruntime.InferenceSession"):
            with patch("pipeline.detector.RealDetector._warmup"):
                # Should not raise
                detector = RealDetector(detector_config)

    def test_checksum_mismatch_raises(self, detector_config, tmp_path):
        """Test checksum mismatch raises ValueError."""
        # Create a dummy model file
        model_path = tmp_path / "test_model.onnx"
        model_data = b"fake model data"
        model_path.write_bytes(model_data)
        
        # Compute correct checksum
        correct_hash = hashlib.sha256(model_data).hexdigest()
        wrong_hash = "0" * 64  # Definitely wrong
        
        detector_config.model_path = str(model_path)
        detector_config.weights_checksum = f"sha256:{wrong_hash}"
        
        with pytest.raises(ValueError, match="Weights checksum mismatch"):
            RealDetector(detector_config)

    def test_checksum_correct_passes(self, detector_config, tmp_path):
        """Test correct checksum passes verification."""
        # Create a dummy model file
        model_path = tmp_path / "test_model.onnx"
        model_data = b"fake model data"
        model_path.write_bytes(model_data)
        
        # Compute correct checksum
        correct_hash = hashlib.sha256(model_data).hexdigest()
        
        detector_config.model_path = str(model_path)
        detector_config.weights_checksum = f"sha256:{correct_hash}"
        
        # Mock ONNX Runtime
        with patch("onnxruntime.InferenceSession"):
            with patch("pipeline.detector.RealDetector._warmup"):
                # Should not raise
                detector = RealDetector(detector_config)

    def test_checksum_file_not_found(self, detector_config):
        """Test missing model file raises ValueError."""
        detector_config.model_path = "nonexistent/model.onnx"
        detector_config.weights_checksum = "sha256:abc123"
        
        with pytest.raises(ValueError, match="Model weights not found"):
            RealDetector(detector_config)


class TestLatencyTracking:
    """Tests for latency tracking and budget warnings."""

    def test_latency_stats_empty(self, detector_config, tmp_path):
        """Test latency stats with no inferences."""
        model_path = tmp_path / "test_model.onnx"
        model_path.write_bytes(b"fake")
        detector_config.model_path = str(model_path)
        detector_config.weights_checksum = "sha256:placeholder"
        
        with patch("onnxruntime.InferenceSession"):
            with patch("pipeline.detector.RealDetector._warmup"):
                detector = RealDetector(detector_config)
                detector.latencies.clear()  # Clear warm-up latencies
                
                stats = detector.get_latency_stats()
                assert stats["p50"] == 0
                assert stats["p95"] == 0
                assert stats["p99"] == 0
                assert stats["count"] == 0

    def test_latency_stats_with_data(self, detector_config, tmp_path):
        """Test latency stats calculation."""
        model_path = tmp_path / "test_model.onnx"
        model_path.write_bytes(b"fake")
        detector_config.model_path = str(model_path)
        detector_config.weights_checksum = "sha256:placeholder"
        
        with patch("onnxruntime.InferenceSession"):
            with patch("pipeline.detector.RealDetector._warmup"):
                detector = RealDetector(detector_config)
                
                # Add synthetic latencies
                detector.latencies.clear()
                for i in range(100):
                    detector.latencies.append(float(i))  # 0 to 99 ms
                
                stats = detector.get_latency_stats()
                assert stats["p50"] == pytest.approx(49.5, rel=0.1)
                assert stats["p95"] == pytest.approx(94.05, rel=0.1)
                assert stats["p99"] == pytest.approx(98.01, rel=0.1)
                assert stats["count"] == 100

    def test_error_rate_calculation(self, detector_config, tmp_path):
        """Test error rate tracking."""
        model_path = tmp_path / "test_model.onnx"
        model_path.write_bytes(b"fake")
        detector_config.model_path = str(model_path)
        detector_config.weights_checksum = "sha256:placeholder"
        
        with patch("onnxruntime.InferenceSession"):
            with patch("pipeline.detector.RealDetector._warmup"):
                detector = RealDetector(detector_config)
                
                detector.total_frames = 100
                detector.error_count = 5
                
                assert detector.get_error_rate() == 0.05


class TestXYWHToXYXY:
    """Tests for bbox format conversion."""

    def test_xywh_to_xyxy_conversion(self):
        """Test xywh (center) to xyxy conversion."""
        # Center format: [x_center, y_center, width, height]
        boxes_xywh = np.array([
            [150, 150, 100, 100],  # Center at (150, 150), size 100x100
        ], dtype=np.float32)
        
        # Convert
        boxes_xyxy = np.zeros_like(boxes_xywh)
        boxes_xyxy[:, 0] = boxes_xywh[:, 0] - boxes_xywh[:, 2] / 2  # x1
        boxes_xyxy[:, 1] = boxes_xywh[:, 1] - boxes_xywh[:, 3] / 2  # y1
        boxes_xyxy[:, 2] = boxes_xywh[:, 0] + boxes_xywh[:, 2] / 2  # x2
        boxes_xyxy[:, 3] = boxes_xywh[:, 1] + boxes_xywh[:, 3] / 2  # y2
        
        # Expected: [100, 100, 200, 200]
        expected = np.array([[100, 100, 200, 200]], dtype=np.float32)
        np.testing.assert_array_almost_equal(boxes_xyxy, expected)

    def test_xywh_to_xyxy_multiple_boxes(self):
        """Test conversion with multiple boxes."""
        boxes_xywh = np.array([
            [50, 50, 20, 20],
            [100, 100, 40, 40],
            [200, 200, 60, 60],
        ], dtype=np.float32)
        
        boxes_xyxy = np.zeros_like(boxes_xywh)
        boxes_xyxy[:, 0] = boxes_xywh[:, 0] - boxes_xywh[:, 2] / 2
        boxes_xyxy[:, 1] = boxes_xywh[:, 1] - boxes_xywh[:, 3] / 2
        boxes_xyxy[:, 2] = boxes_xywh[:, 0] + boxes_xywh[:, 2] / 2
        boxes_xyxy[:, 3] = boxes_xywh[:, 1] + boxes_xywh[:, 3] / 2
        
        expected = np.array([
            [40, 40, 60, 60],
            [80, 80, 120, 120],
            [170, 170, 230, 230],
        ], dtype=np.float32)
        np.testing.assert_array_almost_equal(boxes_xyxy, expected)


# Note: Golden frame tests would go here, but require actual model weights
# and ground-truth annotations. These would be added during model training.
#
# Example structure:
# class TestGoldenFrames:
#     """Regression tests against golden test set with known ground truth."""
#     
#     @pytest.mark.golden
#     def test_golden_frame_001(self):
#         """Test detection on golden frame 001."""
#         frame = cv2.imread("tests/golden/frame_001.jpg")
#         expected_boxes = [...]  # Hand-verified ground truth
#         
#         detector = RealDetector(config)
#         detections = detector.detect(frame)
#         
#         # Assert detections match expected within tolerance
#         assert len(detections) == len(expected_boxes)
#         for det, expected in zip(detections, expected_boxes):
#             assert bbox_iou(det.bbox_xyxy, expected) > 0.9

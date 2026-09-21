"""Tests for configuration loading and validation."""

import os
import tempfile
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from config import load_config, Config


def test_load_default_config():
    """Test loading default configuration."""
    config = load_config()

    assert config.backend.url == "http://localhost:8000/api/v1"
    assert config.device.id == "device-001"
    assert config.detector.confidence_threshold == 0.5
    assert config.tracker.min_hits == 3


def test_config_validation_missing_required_field():
    """Test that missing required fields raise validation error."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        config_data = {
            "backend": {"url": "http://localhost:8000/api/v1", "timeout_seconds": 30},
            # Missing device, camera, detector, etc.
        }
        yaml.dump(config_data, f)
        temp_path = f.name

    try:
        with pytest.raises(ValidationError) as exc_info:
            load_config(temp_path)

        # Check that error mentions missing fields
        error_str = str(exc_info.value)
        assert "device" in error_str or "Field required" in error_str
    finally:
        os.unlink(temp_path)


def test_config_validation_invalid_type():
    """Test that invalid types raise validation error."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        config_data = {
            "backend": {
                "url": "http://localhost:8000/api/v1",
                "timeout_seconds": "not-an-integer"  # Should be int
            },
            "device": {"id": "test", "api_key": "x" * 32, "device_type": "drone"},
            "camera": {"source": 0, "frame_sample_rate": 3},
            "detector": {
                "model_path": "test.onnx",
                "weights_checksum": "sha256:abc123",
                "confidence_threshold": 0.5,
                "nms_iou_threshold": 0.45,
                "input_size": 640,
            },
            "tracker": {"iou_threshold": 0.3, "min_hits": 3, "max_age": 30},
            "severity": {
                "camera_height_m": 2.0,
                "camera_angle_deg": 45,
                "thresholds": {"low_max_area": 5000, "medium_max_area": 15000}
            },
            "gps": {"source": "mock"},
            "buffer": {"db_path": "test.db"},
            "uplink": {
                "batch_size": 10,
                "interval_seconds": 30,
                "retry_backoff_base": 2.0,
                "retry_max_delay_seconds": 300,
            },
        }
        yaml.dump(config_data, f)
        temp_path = f.name

    try:
        with pytest.raises(ValidationError) as exc_info:
            load_config(temp_path)

        error_str = str(exc_info.value)
        assert "timeout_seconds" in error_str or "Input should be a valid integer" in error_str
    finally:
        os.unlink(temp_path)


def test_config_validation_boundary_values():
    """Test boundary value validation."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        config_data = {
            "backend": {"url": "http://localhost:8000/api/v1", "timeout_seconds": 1},  # < min
            "device": {"id": "test", "api_key": "x" * 32},
            "camera": {"source": 0, "frame_sample_rate": 100},  # > max
            "detector": {
                "model_path": "test.onnx",
                "weights_checksum": "sha256:abc",
                "confidence_threshold": 1.5,  # > 1.0
                "nms_iou_threshold": 0.45,
                "input_size": 640,
            },
            "tracker": {"iou_threshold": 0.3, "min_hits": 3, "max_age": 30},
            "severity": {
                "camera_height_m": 2.0,
                "camera_angle_deg": 45,
                "thresholds": {"low_max_area": 5000, "medium_max_area": 15000}
            },
            "gps": {"source": "mock"},
            "buffer": {"db_path": "test.db"},
            "uplink": {
                "batch_size": 10,
                "interval_seconds": 30,
                "retry_backoff_base": 2.0,
                "retry_max_delay_seconds": 300,
            },
        }
        yaml.dump(config_data, f)
        temp_path = f.name

    try:
        with pytest.raises(ValidationError) as exc_info:
            load_config(temp_path)

        error_str = str(exc_info.value)
        # Should have errors for timeout_seconds, frame_sample_rate, and/or confidence_threshold
        assert "timeout_seconds" in error_str or "frame_sample_rate" in error_str or "confidence" in error_str
    finally:
        os.unlink(temp_path)


def test_config_validation_invalid_enum():
    """Test that invalid enum values raise validation error."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        config_data = {
            "backend": {"url": "http://localhost:8000/api/v1", "timeout_seconds": 30},
            "device": {"id": "test", "api_key": "x" * 32, "device_type": "airplane"},  # Invalid
            "camera": {"source": 0, "frame_sample_rate": 3},
            "detector": {
                "model_path": "test.onnx",
                "weights_checksum": "sha256:abc",
                "confidence_threshold": 0.5,
                "nms_iou_threshold": 0.45,
                "input_size": 640,
            },
            "tracker": {"iou_threshold": 0.3, "min_hits": 3, "max_age": 30},
            "severity": {
                "camera_height_m": 2.0,
                "camera_angle_deg": 45,
                "thresholds": {"low_max_area": 5000, "medium_max_area": 15000}
            },
            "gps": {"source": "mock"},
            "buffer": {"db_path": "test.db"},
            "uplink": {
                "batch_size": 10,
                "interval_seconds": 30,
                "retry_backoff_base": 2.0,
                "retry_max_delay_seconds": 300,
            },
        }
        yaml.dump(config_data, f)
        temp_path = f.name

    try:
        with pytest.raises(ValidationError) as exc_info:
            load_config(temp_path)

        error_str = str(exc_info.value)
        assert "device_type" in error_str
    finally:
        os.unlink(temp_path)


def test_env_override():
    """Test that environment variables override config file values."""
    # Set environment variable
    os.environ["EDGE_DEVICE_ID"] = "env-device-123"
    os.environ["EDGE_DETECTOR_CONFIDENCE_THRESHOLD"] = "0.75"

    try:
        config = load_config()

        assert config.device.id == "env-device-123"
        assert config.detector.confidence_threshold == 0.75
    finally:
        # Clean up
        os.environ.pop("EDGE_DEVICE_ID", None)
        os.environ.pop("EDGE_DETECTOR_CONFIDENCE_THRESHOLD", None)


def test_config_file_not_found():
    """Test that missing config file raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        load_config("nonexistent-config.yaml")

"""Configuration loader with schema validation."""

import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from pydantic import BaseModel, Field, HttpUrl, field_validator


class BackendConfig(BaseModel):
    """Backend API connection settings."""

    url: str
    timeout_seconds: int = Field(ge=5, le=300)


class DeviceConfig(BaseModel):
    """Device identity and authentication."""

    id: str
    api_key: str = Field(min_length=32)
    device_type: str = "drone"

    @field_validator("device_type")
    @classmethod
    def validate_device_type(cls, v: str) -> str:
        if v not in ["drone", "vehicle", "fixed"]:
            raise ValueError(f"device_type must be one of: drone, vehicle, fixed (got {v})")
        return v


class CameraConfig(BaseModel):
    """Camera capture configuration."""

    source: int | str
    frame_sample_rate: int = Field(ge=1, le=60)
    queue_max_size: int = Field(ge=1, le=100, default=10)
    width: int = Field(ge=640, le=3840, default=1920)
    height: int = Field(ge=480, le=2160, default=1080)


class NormalizationConfig(BaseModel):
    """Detector preprocessing normalization."""

    mean: list[float] = Field(default=[0.0, 0.0, 0.0])
    std: list[float] = Field(default=[1.0, 1.0, 1.0])
    scale: float = 255.0

    @field_validator("mean", "std")
    @classmethod
    def validate_channel_count(cls, v: list[float]) -> list[float]:
        if len(v) != 3:
            raise ValueError("mean and std must have exactly 3 values (RGB channels)")
        return v


class DetectorConfig(BaseModel):
    """YOLOv8n detector configuration."""

    model_path: str
    engine_path: Optional[str] = None
    weights_checksum: str
    backend: str = "auto"
    confidence_threshold: float = Field(ge=0.0, le=1.0)
    nms_iou_threshold: float = Field(ge=0.0, le=1.0)
    max_detections: int = Field(ge=1, le=500)
    input_size: int
    quantization: str = "none"
    warmup_iterations: int = Field(ge=1, le=20, default=5)
    inference_timeout_seconds: float = Field(ge=0.1, le=60.0, default=5.0)
    latency_budget_ms: float = Field(ge=10, le=1000, default=100)
    normalization: NormalizationConfig = Field(default_factory=NormalizationConfig)
    model_version: str = "v1.0"

    @field_validator("backend")
    @classmethod
    def validate_backend(cls, v: str) -> str:
        if v not in ["auto", "tensorrt", "onnx-cuda", "onnx-cpu"]:
            raise ValueError(f"backend must be one of: auto, tensorrt, onnx-cuda, onnx-cpu (got {v})")
        return v

    @field_validator("input_size")
    @classmethod
    def validate_input_size(cls, v: int) -> int:
        valid_sizes = [320, 416, 512, 640, 768, 896, 1024]
        if v not in valid_sizes:
            raise ValueError(f"input_size must be one of: {valid_sizes} (got {v})")
        return v

    @field_validator("quantization")
    @classmethod
    def validate_quantization(cls, v: str) -> str:
        if v not in ["none", "fp16", "int8"]:
            raise ValueError(f"quantization must be one of: none, fp16, int8 (got {v})")
        return v


class TrackerConfig(BaseModel):
    """Multi-frame tracking configuration."""

    iou_threshold: float = Field(ge=0.0, le=1.0)
    min_hits: int = Field(ge=1, le=20)
    max_age: int = Field(ge=1, le=300)


class SeverityThresholdsConfig(BaseModel):
    """Severity classification thresholds."""

    low_max_area: float = Field(ge=0)
    medium_max_area: float = Field(ge=0)
    confidence_multiplier: float = Field(ge=0.0, le=2.0, default=1.0)


class SeverityConfig(BaseModel):
    """Severity classification configuration."""

    camera_height_m: float = Field(ge=0.5, le=100.0)
    camera_angle_deg: float = Field(ge=0, le=90)
    thresholds: SeverityThresholdsConfig


class GPSInterpolationConfig(BaseModel):
    """GPS interpolation settings."""

    enabled: bool = True
    max_age_seconds: float = Field(ge=1, le=300, default=10)
    use_imu: bool = False


class GPSConfig(BaseModel):
    """GPS receiver configuration."""

    source: str
    baud_rate: int = 9600
    timeout_seconds: float = Field(ge=0.1, le=60.0, default=2.0)
    interpolation: GPSInterpolationConfig = Field(default_factory=GPSInterpolationConfig)

    @field_validator("baud_rate")
    @classmethod
    def validate_baud_rate(cls, v: int) -> int:
        valid_rates = [4800, 9600, 19200, 38400, 57600, 115200]
        if v not in valid_rates:
            raise ValueError(f"baud_rate must be one of: {valid_rates} (got {v})")
        return v


class BufferConfig(BaseModel):
    """Local buffer configuration."""

    db_path: str = "edge/buffer.db"
    max_retries: int = Field(ge=1, le=100, default=10)
    cleanup_after_days: int = Field(ge=1, le=365, default=7)


class UplinkConfig(BaseModel):
    """Backend uplink configuration."""

    batch_size: int = Field(ge=1, le=1000)
    interval_seconds: float = Field(ge=1, le=3600)
    retry_backoff_base: float = Field(ge=1.0, le=10.0)
    retry_max_delay_seconds: int = Field(ge=10, le=3600)
    jitter_max_seconds: float = Field(ge=0, le=60, default=5.0)


class LoggingConfig(BaseModel):
    """Logging configuration."""

    level: str = "INFO"
    format: str = "json"
    output: str = "stdout"
    file_path: Optional[str] = None
    metrics_interval_seconds: int = Field(ge=1, le=3600, default=60)

    @field_validator("level")
    @classmethod
    def validate_level(cls, v: str) -> str:
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v not in valid_levels:
            raise ValueError(f"level must be one of: {valid_levels} (got {v})")
        return v

    @field_validator("format")
    @classmethod
    def validate_format(cls, v: str) -> str:
        if v not in ["json", "text"]:
            raise ValueError(f"format must be one of: json, text (got {v})")
        return v

    @field_validator("output")
    @classmethod
    def validate_output(cls, v: str) -> str:
        if v not in ["stdout", "file"]:
            raise ValueError(f"output must be one of: stdout, file (got {v})")
        return v


class Config(BaseModel):
    """Complete edge pipeline configuration."""

    backend: BackendConfig
    device: DeviceConfig
    camera: CameraConfig
    detector: DetectorConfig
    tracker: TrackerConfig
    severity: SeverityConfig
    gps: GPSConfig
    buffer: BufferConfig
    uplink: UplinkConfig
    logging: LoggingConfig = Field(default_factory=LoggingConfig)


def load_config(config_path: Optional[str] = None) -> Config:
    """
    Load and validate configuration from YAML file.

    Args:
        config_path: Path to config file. If None, uses default.yaml.

    Returns:
        Validated Config object.

    Raises:
        FileNotFoundError: If config file doesn't exist.
        ValidationError: If config doesn't match schema.
    """
    if config_path is None:
        config_dir = Path(__file__).parent
        config_path = str(config_dir / "default.yaml")

    config_file = Path(config_path)
    if not config_file.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    with open(config_file) as f:
        config_dict = yaml.safe_load(f)

    # Override with environment variables if present
    config_dict = _apply_env_overrides(config_dict)

    return Config(**config_dict)


def _apply_env_overrides(config: Dict[str, Any]) -> Dict[str, Any]:
    """Apply environment variable overrides to config dict."""
    env_mapping = {
        "EDGE_BACKEND_URL": ("backend", "url"),
        "EDGE_DEVICE_ID": ("device", "id"),
        "EDGE_DEVICE_API_KEY": ("device", "api_key"),
        "EDGE_CAMERA_SOURCE": ("camera", "source"),
        "EDGE_CAMERA_FRAME_SAMPLE_RATE": ("camera", "frame_sample_rate"),
        "EDGE_DETECTOR_MODEL_PATH": ("detector", "model_path"),
        "EDGE_DETECTOR_ENGINE_PATH": ("detector", "engine_path"),
        "EDGE_DETECTOR_WEIGHTS_CHECKSUM": ("detector", "weights_checksum"),
        "EDGE_DETECTOR_BACKEND": ("detector", "backend"),
        "EDGE_DETECTOR_CONFIDENCE_THRESHOLD": ("detector", "confidence_threshold"),
        "EDGE_DETECTOR_NMS_IOU_THRESHOLD": ("detector", "nms_iou_threshold"),
        "EDGE_GPS_SOURCE": ("gps", "source"),
        "EDGE_GPS_BAUD_RATE": ("gps", "baud_rate"),
        "EDGE_BUFFER_DB_PATH": ("buffer", "db_path"),
        "EDGE_UPLINK_BATCH_SIZE": ("uplink", "batch_size"),
        "EDGE_UPLINK_INTERVAL_SECONDS": ("uplink", "interval_seconds"),
    }

    for env_var, (section, key) in env_mapping.items():
        value = os.getenv(env_var)
        if value is not None:
            # Type conversion based on existing value
            if section in config and key in config[section]:
                existing_type = type(config[section][key])
                if existing_type == int:
                    value = int(value)
                elif existing_type == float:
                    value = float(value)
                elif existing_type == bool:
                    value = value.lower() in ["true", "1", "yes"]

            if section not in config:
                config[section] = {}
            config[section][key] = value

    return config

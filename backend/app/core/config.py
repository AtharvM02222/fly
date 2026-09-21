from typing import Literal
from pydantic import Field, PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict
class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )
    database_url: PostgresDsn = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/dronecds"
    )
    database_pool_size: int = Field(default=20, ge=1, le=100)
    database_max_overflow: int = Field(default=10, ge=0, le=100)
    redis_url: str = Field(default="redis://localhost:6379/0")
    jwt_secret: str = Field(min_length=32)
    jwt_algorithm: str = "HS256"
    jwt_expiry_minutes: int = Field(default=1440, ge=5)
    api_key_salt: str = Field(min_length=16)
    rate_limit_per_device_per_minute: int = Field(default=100, ge=1)
    s3_endpoint: str = Field(default="http://localhost:9000")
    s3_access_key: str
    s3_secret_key: str
    s3_bucket: str = "dronecds-detections"
    s3_region: str = "us-east-1"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_format: Literal["json", "text"] = "json"
    dedup_geohash_precision: int = Field(default=7, ge=1, le=12)
    dedup_distance_meters: float = Field(default=150.0, ge=1.0)
    dedup_time_window_minutes: int = Field(default=5, ge=1)
    notification_severity_threshold: Literal["low", "medium", "high"] = "medium"
    notification_cooldown_minutes: int = Field(default=60, ge=1)
    api_v1_prefix: str = "/api/v1"
    cors_origins: list[str] = Field(
        default=["http://localhost:3000", "http://localhost:8000"]
    )
    service_name: str = "dronecds-backend"
    environment: Literal["development", "staging", "production"] = "development"
def get_settings() -> Settings:
    return Settings()
settings = get_settings()

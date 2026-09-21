import uuid
from datetime import datetime
from typing import Any
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
class ErrorResponse(BaseModel):
    error_code: str
    message: str
    details: dict[str, Any] | None = None
class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: uuid.UUID
    email: str
    role: str
class TokenData(BaseModel):
    user_id: uuid.UUID
    email: str | None = None
class DeviceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    device_type: str = Field(pattern="^(drone|vehicle|fixed)$")
class DeviceCreateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    device_type: str
    api_key: str
    status: str
    created_at: datetime
class DeviceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    device_type: str
    last_seen_at: datetime | None
    status: str
    created_at: datetime
class DeviceHeartbeatResponse(BaseModel):
    device_id: uuid.UUID
    last_seen_at: datetime
    status: str
class DetectionCreate(BaseModel):
    client_detection_id: uuid.UUID
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    severity: str = Field(pattern="^(low|medium|high)$")
    confidence: float = Field(ge=0.0, le=1.0)
    bbox: dict[str, float] | None = None
    image_base64: str | None = None
    model_version: str | None = None
    detected_at: datetime
    is_interpolated: bool = False
    @field_validator("bbox")
    @classmethod
    def validate_bbox(cls, v: dict[str, float] | None) -> dict[str, float] | None:
        if v is not None:
            required_keys = {"x1", "y1", "x2", "y2"}
            if not required_keys.issubset(v.keys()):
                raise ValueError(f"bbox must contain keys: {required_keys}")
        return v
class DetectionBatchIngestRequest(BaseModel):
    detections: list[DetectionCreate] = Field(min_length=1, max_length=100)
class DetectionIngestItemResult(BaseModel):
    client_detection_id: uuid.UUID
    status: str
    detection_id: uuid.UUID | None = None
    error: str | None = None
class DetectionBatchIngestResponse(BaseModel):
    accepted: int
    rejected: int
    results: list[DetectionIngestItemResult]
class DetectionEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    event_type: str
    actor: str | None
    note: str | None
    created_at: datetime
class DetectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    client_detection_id: uuid.UUID
    device_id: uuid.UUID
    latitude: float
    longitude: float
    geohash: str
    severity: str
    confidence: float
    status: str
    image_url: str | None
    bbox: dict[str, float] | None
    model_version: str | None
    detected_at: datetime
    created_at: datetime
    merged_into: uuid.UUID | None
class DetectionDetailResponse(DetectionResponse):
    events: list[DetectionEventResponse]
class DetectionListResponse(BaseModel):
    detections: list[DetectionResponse]
    total: int
    page: int
    page_size: int
    has_next: bool
class DetectionStatusUpdate(BaseModel):
    status: str = Field(pattern="^(new|confirmed|assigned|fixed|verified)$")
    note: str | None = Field(None, max_length=1000)
class NotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    detection_id: uuid.UUID
    status: str
    created_at: datetime
    detection_severity: str | None = None
    detection_location: tuple[float, float] | None = None
class NotificationListResponse(BaseModel):
    notifications: list[NotificationResponse]
    unread_count: int
    total: int
class DetectionFilters(BaseModel):
    bbox: str | None = Field(
        None, description="Bounding box: min_lon,min_lat,max_lon,max_lat"
    )
    status: str | None = Field(None, pattern="^(new|confirmed|assigned|fixed|verified)$")
    severity: str | None = Field(None, pattern="^(low|medium|high)$")
    device_id: uuid.UUID | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None
    page: int = Field(1, ge=1)
    page_size: int = Field(50, ge=1, le=100)

import uuid
from datetime import datetime
from typing import TYPE_CHECKING
from geoalchemy2 import Geography
from sqlalchemy import DateTime, Float, ForeignKey, Index, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..base import Base
if TYPE_CHECKING:
    from .device import Device
    from .notification import Notification
class Detection(Base):
    __tablename__ = "detections"
    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
        server_default=Text("gen_random_uuid()"),
    )
    client_detection_id: Mapped[uuid.UUID] = mapped_column(
        unique=True, nullable=False, index=True
    )
    device_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    location: Mapped[str] = mapped_column(
        Geography(geometry_type="POINT", srid=4326), nullable=False
    )
    geohash: Mapped[str] = mapped_column(String(12), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="new"
    )
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    bbox: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    model_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    merged_into: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("detections.id", ondelete="SET NULL"), nullable=True
    )
    device: Mapped["Device"] = relationship("Device", back_populates="detections")
    events: Mapped[list["DetectionEvent"]] = relationship(
        "DetectionEvent", back_populates="detection", cascade="all, delete-orphan"
    )
    notifications: Mapped[list["Notification"]] = relationship(
        "Notification", back_populates="detection", cascade="all, delete-orphan"
    )
    merged_parent: Mapped["Detection | None"] = relationship(
        "Detection", remote_side=[id], foreign_keys=[merged_into]
    )
    __table_args__ = (
        Index("idx_detections_location", "location", postgresql_using="gist"),
        Index("idx_detections_status_time", "status", "detected_at"),
    )
    def __repr__(self) -> str:
        return f"<Detection(id={self.id}, severity={self.severity}, status={self.status})>"
class DetectionEvent(Base):
    __tablename__ = "detection_events"
    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
        server_default=Text("gen_random_uuid()"),
    )
    detection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("detections.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )
    actor: Mapped[str | None] = mapped_column(String(255), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    detection: Mapped["Detection"] = relationship("Detection", back_populates="events")
    def __repr__(self) -> str:
        return f"<DetectionEvent(id={self.id}, type={self.event_type}, actor={self.actor})>"

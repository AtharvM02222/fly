"""Base class for SQLAlchemy models and model imports for Alembic."""

from sqlalchemy.orm import DeclarativeBase

# Import all models here so Alembic can auto-detect them
# This must be done AFTER Base is defined
class Base(DeclarativeBase):
    """Base class for all database models."""
    pass


# Import models for Alembic autogenerate
from app.db.models.device import Device  # noqa: E402, F401
from app.db.models.detection import Detection, DetectionEvent  # noqa: E402, F401
from app.db.models.user import User  # noqa: E402, F401
from app.db.models.notification import Notification  # noqa: E402, F401

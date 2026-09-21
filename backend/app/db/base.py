from sqlalchemy.orm import DeclarativeBase
class Base(DeclarativeBase):
    pass
from app.db.models.device import Device
from app.db.models.detection import Detection, DetectionEvent
from app.db.models.user import User
from app.db.models.notification import Notification

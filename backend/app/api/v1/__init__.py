from fastapi import APIRouter
from .auth import router as auth_router
from .devices import router as devices_router
from .detections import router as detections_router
from .notifications import router as notifications_router
api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(devices_router)
api_router.include_router(detections_router)
api_router.include_router(notifications_router)

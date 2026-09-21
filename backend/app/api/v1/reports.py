import csv
import io
import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models.detection import Detection
from app.db.session import get_db
from app.core.logging import get_logger
logger = get_logger(__name__)
router = APIRouter(prefix="/reports", tags=["reports"])
@router.get("/export")
async def export_detections(
    format: str = Query("csv", regex="^(csv)$"),
    bbox: str | None = Query(None, description="Bounding box: min_lon,min_lat,max_lon,max_lat"),
    status_filter: str | None = Query(None, alias="status"),
    severity: str | None = None,
    device_id: uuid.UUID | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    db: AsyncSession = Depends(get_db),
):
    query = select(Detection)
    if bbox:
        try:
            min_lon, min_lat, max_lon, max_lat = map(float, bbox.split(","))
            bbox_polygon = func.ST_MakeEnvelope(min_lon, min_lat, max_lon, max_lat, 4326)
            query = query.where(func.ST_Intersects(Detection.location, bbox_polygon))
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid bbox format",
            )
    if status_filter:
        query = query.where(Detection.status == status_filter)
    if severity:
        query = query.where(Detection.severity == severity)
    if device_id:
        query = query.where(Detection.device_id == device_id)
    if start_date:
        query = query.where(Detection.detected_at >= start_date)
    if end_date:
        query = query.where(Detection.detected_at <= end_date)
    query = query.order_by(Detection.detected_at.desc())
    result = await db.execute(query)
    detections = result.scalars().all()
    if format == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "ID",
            "Client ID",
            "Device ID",
            "Latitude",
            "Longitude",
            "Geohash",
            "Severity",
            "Confidence",
            "Status",
            "Model Version",
            "Detected At",
            "Created At",
            "Merged Into"
        ])
        for det in detections:
            lat_lon_result = await db.execute(
                select(
                    func.ST_Y(func.ST_GeomFromWKB(det.location)),
                    func.ST_X(func.ST_GeomFromWKB(det.location)),
                )
            )
            lat, lon = lat_lon_result.one()
            writer.writerow([
                str(det.id),
                det.client_detection_id,
                str(det.device_id),
                f"{lat:.6f}",
                f"{lon:.6f}",
                det.geohash,
                det.severity,
                f"{det.confidence:.3f}",
                det.status,
                det.model_version,
                det.detected_at.isoformat(),
                det.created_at.isoformat(),
                str(det.merged_into) if det.merged_into else ""
            ])
        output.seek(0)
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"detections_export_{timestamp}.csv"
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Unsupported format: {format}"
    )

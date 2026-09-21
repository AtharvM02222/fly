import base64
import hashlib
import io
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional
from PIL import Image
from app.core.config import settings
from app.core.logging import get_logger
logger = get_logger(__name__)
class StorageService:
    def __init__(self, storage_dir: str = "./storage/images"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.max_size = (1024, 1024)
        self.jpeg_quality = 85
    def save_detection_image(
        self,
        image_base64: str,
        detection_id: uuid.UUID,
    ) -> str:
        try:
            image_data = base64.b64decode(image_base64)
            image = Image.open(io.BytesIO(image_data))
            if image.mode != 'RGB':
                image = image.convert('RGB')
            image.thumbnail(self.max_size, Image.Resampling.LANCZOS)
            output_buffer = io.BytesIO()
            image.save(output_buffer, format='JPEG', quality=self.jpeg_quality, optimize=True)
            output_buffer.seek(0)
            file_hash = hashlib.sha256(output_buffer.getvalue()).hexdigest()[:16]
            timestamp = datetime.utcnow().strftime("%Y%m%d")
            filename = f"{timestamp}_{detection_id}_{file_hash}.jpg"
            file_path = self.storage_dir / filename
            with open(file_path, 'wb') as f:
                f.write(output_buffer.getvalue())
            relative_url = f"/images/{filename}"
            logger.info(f"Saved detection image: {relative_url}")
            return relative_url
        except Exception as e:
            logger.error(f"Failed to save detection image: {e}")
            return None
    def delete_image(self, image_url: str) -> bool:
        try:
            filename = image_url.split("/")[-1]
            file_path = self.storage_dir / filename
            if file_path.exists():
                file_path.unlink()
                logger.info(f"Deleted image: {image_url}")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to delete image {image_url}: {e}")
            return False

import random
import time
from typing import Dict, List
import requests
from config import BackendConfig, UplinkConfig
from .buffer import BufferedDetection
class UplinkService:
    def __init__(
        self,
        backend_config: BackendConfig,
        uplink_config: UplinkConfig,
        device_api_key: str,
    ):
        self.backend_config = backend_config
        self.uplink_config = uplink_config
        self.device_api_key = device_api_key
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {device_api_key}"})
    def upload_batch(
        self, detections: List[BufferedDetection]
    ) -> Dict[str, List[BufferedDetection]]:
        if not detections:
            return {"success": [], "failed": []}
        payload = {
            "detections": [
                {
                    "client_detection_id": det.client_detection_id,
                    "latitude": det.latitude,
                    "longitude": det.longitude,
                    "severity": det.severity,
                    "confidence": det.confidence,
                    "bbox": det.bbox,
                    "model_version": det.model_version,
                    "detected_at": det.detected_at,
                    "is_interpolated": det.is_interpolated,
                }
                for det in detections
            ]
        }
        url = f"{self.backend_config.url}/detections"
        try:
            response = self.session.post(
                url,
                json=payload,
                timeout=self.backend_config.timeout_seconds,
            )
            if response.status_code == 202:
                data = response.json()
                results = data.get("results", [])
                success = []
                failed = []
                for det in detections:
                    result = next(
                        (
                            r
                            for r in results
                            if r["client_detection_id"] == det.client_detection_id
                        ),
                        None,
                    )
                    if result and result["status"] in ["created", "duplicate"]:
                        success.append(det)
                    else:
                        failed.append(det)
                return {"success": success, "failed": failed}
            else:
                return {"success": [], "failed": detections}
        except requests.exceptions.RequestException as e:
            return {"success": [], "failed": detections}
    def calculate_backoff_delay(self, retry_count: int) -> float:
        base_delay = self.uplink_config.retry_backoff_base ** retry_count
        max_delay = self.uplink_config.retry_max_delay_seconds
        delay = min(base_delay, max_delay)
        jitter = random.uniform(0, self.uplink_config.jitter_max_seconds)
        return delay + jitter
    def close(self) -> None:
        self.session.close()

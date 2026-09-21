"""Uplink module for posting detections to backend."""

import random
import time
from typing import Dict, List

import requests

from config import BackendConfig, UplinkConfig
from .buffer import BufferedDetection


class UplinkService:
    """
    Uplink service with exponential backoff retry.

    Posts buffered detections to backend API with:
    - Batching for efficiency
    - Exponential backoff with jitter on failure
    - Per-item status tracking
    """

    def __init__(
        self,
        backend_config: BackendConfig,
        uplink_config: UplinkConfig,
        device_api_key: str,
    ):
        """
        Initialize uplink service.

        Args:
            backend_config: Backend connection settings
            uplink_config: Uplink retry settings
            device_api_key: Device API key for authentication
        """
        self.backend_config = backend_config
        self.uplink_config = uplink_config
        self.device_api_key = device_api_key
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {device_api_key}"})

    def upload_batch(
        self, detections: List[BufferedDetection]
    ) -> Dict[str, List[BufferedDetection]]:
        """
        Upload batch of detections to backend.

        Args:
            detections: List of buffered detections

        Returns:
            Dict with 'success' and 'failed' lists
        """
        if not detections:
            return {"success": [], "failed": []}

        # Build request payload
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

        # Post to backend
        url = f"{self.backend_config.url}/detections"

        try:
            response = self.session.post(
                url,
                json=payload,
                timeout=self.backend_config.timeout_seconds,
            )

            if response.status_code == 202:
                # Success - parse per-item results
                data = response.json()
                results = data.get("results", [])

                success = []
                failed = []

                for det in detections:
                    # Find corresponding result
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
                # Non-2xx response - all failed
                return {"success": [], "failed": detections}

        except requests.exceptions.RequestException as e:
            # Network error - all failed
            return {"success": [], "failed": detections}

    def calculate_backoff_delay(self, retry_count: int) -> float:
        """
        Calculate exponential backoff delay with jitter.

        Args:
            retry_count: Number of retries so far

        Returns:
            Delay in seconds
        """
        base_delay = self.uplink_config.retry_backoff_base ** retry_count
        max_delay = self.uplink_config.retry_max_delay_seconds

        # Cap at max delay
        delay = min(base_delay, max_delay)

        # Add jitter
        jitter = random.uniform(0, self.uplink_config.jitter_max_seconds)
        return delay + jitter

    def close(self) -> None:
        """Close HTTP session."""
        self.session.close()

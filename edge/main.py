import argparse
import logging
import sys
import time
import uuid
from datetime import datetime
from config import load_config
from pipeline.buffer import DetectionBuffer
from pipeline.capture import CameraCapture
from pipeline.detector import MockDetector, RealDetector
from pipeline.geo import GPSReader
from pipeline.severity import bbox_area, calculate_severity
from pipeline.tracker import Tracker
from pipeline.uplink import UplinkService
def setup_logging(level: str = "INFO") -> logging.Logger:
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    return logging.getLogger(__name__)
def run_pipeline(config, use_mock_detector: bool, logger: logging.Logger) -> None:
    logger.info("Initializing pipeline modules...")
    capture = CameraCapture(config.camera)
    if use_mock_detector:
        logger.info("Using MOCK detector (synthetic detections)")
        detector = MockDetector(config.detector)
    else:
        logger.info("Using REAL detector (ONNX/TensorRT)")
        detector = RealDetector(config.detector)
        logger.info(f"Detector backend: {detector.backend_name}")
        logger.info(f"Model version: {detector.get_model_version()}")
    tracker = Tracker(config.tracker)
    gps_reader = GPSReader(config.gps)
    buffer = DetectionBuffer(config.buffer)
    uplink = UplinkService(config.backend, config.uplink, config.device.api_key)
    logger.info("Opening buffer...")
    buffer.open()
    logger.info("Starting capture...")
    capture.start()
    logger.info(
        f"Capture resolution: {capture.get_resolution()}, "
        f"FPS: {capture.get_fps():.1f}, "
        f"Sample rate: every {config.camera.frame_sample_rate} frames"
    )
    try:
        frame_count = 0
        detection_count = 0
        last_uplink_time = time.time()
        logger.info("Pipeline running - press Ctrl+C to stop")
        for frame_number, frame in capture.sample_frames():
            frame_count += 1
            detections = detector.detect(frame)
            if detections:
                logger.debug(f"Frame {frame_number}: {len(detections)} raw detection(s)")
            confirmed_tracks = tracker.update(detections)
            for track in confirmed_tracks:
                track.buffered = True
                gps_reading = gps_reader.read()
                if gps_reading is None:
                    logger.warning("GPS unavailable and interpolation failed - skipping")
                    continue
                area = bbox_area(track.bbox_xyxy)
                severity = calculate_severity(area, track.confidence, config.severity)
                client_detection_id = str(uuid.uuid4())
                image_base64 = None
                try:
                    x1, y1, x2, y2 = map(int, track.bbox_xyxy)
                    x1, y1 = max(0, x1), max(0, y1)
                    x2, y2 = min(frame.shape[1], x2), min(frame.shape[0], y2)
                    if x2 > x1 and y2 > y1:
                        cropped = frame[y1:y2, x1:x2]
                        import cv2
                        _, buffer = cv2.imencode('.jpg', cropped, [cv2.IMWRITE_JPEG_QUALITY, 85])
                        import base64
                        image_base64 = base64.b64encode(buffer).decode('utf-8')
                except Exception as e:
                    logger.warning(f"Failed to crop/encode image: {e}")
                try:
                    buffer.write(
                        client_detection_id=client_detection_id,
                        latitude=gps_reading.latitude,
                        longitude=gps_reading.longitude,
                        severity=severity,
                        confidence=track.confidence,
                        bbox={
                            "x1": track.bbox_xyxy[0],
                            "y1": track.bbox_xyxy[1],
                            "x2": track.bbox_xyxy[2],
                            "y2": track.bbox_xyxy[3],
                        },
                        model_version=detector.get_model_version(),
                        detected_at=datetime.utcnow(),
                        is_interpolated=gps_reading.is_interpolated,
                        image_base64=image_base64,
                    )
                            "x2": track.bbox_xyxy[2],
                            "y2": track.bbox_xyxy[3],
                        },
                        model_version=detector.get_model_version(),
                        detected_at=datetime.utcnow(),
                        is_interpolated=gps_reading.is_interpolated,
                    )
                    detection_count += 1
                    logger.info(
                        f"Confirmed detection: severity={severity}, "
                        f"confidence={track.confidence:.2f}, "
                        f"GPS={'interpolated' if gps_reading.is_interpolated else 'live'}"
                    )
                except Exception as e:
                    logger.error(f"Failed to buffer detection: {e}")
            now = time.time()
            if now - last_uplink_time >= config.uplink.interval_seconds:
                pending = buffer.get_pending(config.uplink.batch_size)
                if pending:
                    logger.info(f"Uploading {len(pending)} pending detection(s)...")
                    result = uplink.upload_batch(pending)
                    for det in result["success"]:
                        buffer.mark_uploaded(det.id)
                        logger.info(f"Uploaded detection {det.client_detection_id}")
                    for det in result["failed"]:
                        buffer.increment_retry(det.id)
                        logger.warning(
                            f"Failed to upload detection {det.client_detection_id} "
                            f"(retry {det.retry_count + 1}/{config.buffer.max_retries})"
                        )
                    stats = buffer.get_stats()
                    logger.info(
                        f"Buffer stats: pending={stats['pending']}, "
                        f"uploaded={stats['uploaded']}, failed={stats['failed']}"
                    )
                last_uplink_time = now
            if frame_count % 100 == 0:
                stats = buffer.get_stats()
                if not use_mock_detector and hasattr(detector, 'get_latency_stats'):
                    latency_stats = detector.get_latency_stats()
                    error_rate = detector.get_error_rate()
                    logger.info(
                        f"Processed {frame_count} frames, "
                        f"{detection_count} confirmed detections, "
                        f"{stats['pending']} pending upload | "
                        f"Latency p50/p95={latency_stats['p50']:.1f}/{latency_stats['p95']:.1f}ms, "
                        f"Error rate={error_rate:.2%}"
                    )
                else:
                    logger.info(
                        f"Processed {frame_count} frames, "
                        f"{detection_count} confirmed detections, "
                        f"{stats['pending']} pending upload"
                    )
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        capture.stop()
        buffer.close()
        uplink.close()
        logger.info("Pipeline stopped")
def main() -> int:
    parser = argparse.ArgumentParser(description="Drone-CDS Edge Detection Pipeline")
    parser.add_argument(
        "--config", type=str, help="Path to configuration file (default: config/default.yaml)"
    )
    parser.add_argument(
        "--detector",
        type=str,
        choices=["real", "mock"],
        default="mock",
        help="Detector type: real (ONNX/TensorRT) or mock (for testing)",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level",
    )
    args = parser.parse_args()
    logger = setup_logging(args.log_level)
    logger.info("Starting Drone-CDS Edge Pipeline")
    try:
        config = load_config(args.config)
        logger.info("Configuration loaded successfully")
        logger.info(f"Device ID: {config.device.id}")
        logger.info(f"Backend URL: {config.backend.url}")
        logger.info(f"Detector: {args.detector}")
        run_pipeline(config, use_mock_detector=(args.detector == "mock"), logger=logger)
        return 0
    except Exception as e:
        logger.error(f"Failed to start edge pipeline: {e}", exc_info=True)
        return 1
if __name__ == "__main__":
    sys.exit(main())

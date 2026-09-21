import hashlib
import logging
import time
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple
import cv2
import numpy as np
try:
    import onnxruntime as ort
    HAS_ONNX = True
except ImportError:
    ort = None
    HAS_ONNX = False
from config import DetectorConfig
logger = logging.getLogger(__name__)
@dataclass
class Detection:
    bbox_xyxy: tuple[float, float, float, float]
    confidence: float
    class_id: int
    class_name: str
class DetectorInterface(ABC):
    @abstractmethod
    def detect(self, frame: np.ndarray) -> List[Detection]:
        pass
    @abstractmethod
    def get_model_version(self) -> str:
        pass
class MockDetector(DetectorInterface):
    def __init__(
        self,
        config: DetectorConfig,
        detection_interval: int = 10,
        detection_probability: float = 0.3,
    ):
        self.config = config
        self.detection_interval = detection_interval
        self.detection_probability = detection_probability
        self.frame_count = 0
        self.model_version = "mock-v1.0"
    def detect(self, frame: np.ndarray) -> List[Detection]:
        self.frame_count += 1
        if (
            self.frame_count % self.detection_interval == 0
            or np.random.random() < self.detection_probability
        ):
            h, w = frame.shape[:2]
            x1 = np.random.randint(0, w - 200)
            y1 = np.random.randint(0, h - 200)
            x2 = x1 + np.random.randint(100, 200)
            y2 = y1 + np.random.randint(100, 200)
            confidence = np.random.uniform(
                self.config.confidence_threshold, 1.0
            )
            return [
                Detection(
                    bbox_xyxy=(float(x1), float(y1), float(x2), float(y2)),
                    confidence=float(confidence),
                    class_id=0,
                    class_name="pothole",
                )
            ]
        return []
    def get_model_version(self) -> str:
        return self.model_version
class RealDetector(DetectorInterface):
    def __init__(self, config: DetectorConfig):
        self.config = config
        self.model_path = Path(config.model_path)
        self.engine_path = Path(config.engine_path) if config.engine_path else None
        self._verify_checksum()
        self.session = None
        self.backend_name = self._initialize_backend()
        logger.info(f"Initialized detector with backend: {self.backend_name}")
        self.input_name, self.output_names = self._get_io_names()
        self.latencies = deque(maxlen=1000)
        self.error_count = 0
        self.total_frames = 0
        self._warmup()
        logger.info(f"Detector ready. Model version: {config.model_version}")
    def _verify_checksum(self) -> None:
        if not self.model_path.exists():
            raise ValueError(
                f"Model weights not found at {self.model_path}. "
                f"Please provide trained weights before running real detector."
            )
        checksum_str = self.config.weights_checksum
        if checksum_str == "sha256:placeholder":
            logger.warning(
                "Checksum is 'placeholder' - skipping verification. "
                "Set real checksum in production!"
            )
            return
        try:
            algo, expected_hash = checksum_str.split(":", 1)
        except ValueError:
            raise ValueError(
                f"Invalid checksum format: {checksum_str}. "
                f"Expected 'algorithm:hash' (e.g., 'sha256:abc123...')"
            )
        if algo == "sha256":
            hasher = hashlib.sha256()
        elif algo == "md5":
            hasher = hashlib.md5()
        else:
            raise ValueError(f"Unsupported checksum algorithm: {algo}")
        with open(self.model_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hasher.update(chunk)
        actual_hash = hasher.hexdigest()
        if actual_hash != expected_hash:
            raise ValueError(
                f"Weights checksum mismatch!\n"
                f"Expected: {expected_hash}\n"
                f"Actual:   {actual_hash}\n"
                f"File may be corrupted or wrong version."
            )
        logger.info(f"Weights checksum verified ({algo})")
    def _initialize_backend(self) -> str:
        if not HAS_ONNX:
            raise RuntimeError(
                "ONNX Runtime not installed. Install with: pip install onnxruntime"
            )
        backend_pref = self.config.backend.lower()
        if backend_pref in ("auto", "tensorrt") and self.engine_path and self.engine_path.exists():
            try:
                providers = ort.get_available_providers()
                if "TensorrtExecutionProvider" in providers:
                    self.session = ort.InferenceSession(
                        str(self.model_path),
                        providers=["TensorrtExecutionProvider", "CUDAExecutionProvider", "CPUExecutionProvider"]
                    )
                    return "TensorRT (via ONNX Runtime)"
            except Exception as e:
                logger.warning(f"TensorRT backend failed: {e}. Falling back...")
        if backend_pref in ("auto", "onnx-cuda"):
            try:
                providers = ort.get_available_providers()
                if "CUDAExecutionProvider" in providers:
                    self.session = ort.InferenceSession(
                        str(self.model_path),
                        providers=["CUDAExecutionProvider", "CPUExecutionProvider"]
                    )
                    actual_provider = self.session.get_providers()[0]
                    if actual_provider == "CUDAExecutionProvider":
                        return "ONNX Runtime (CUDA)"
                    else:
                        logger.warning(f"CUDA requested but using {actual_provider}")
            except Exception as e:
                logger.warning(f"ONNX Runtime CUDA backend failed: {e}. Falling back...")
        if backend_pref in ("auto", "onnx-cpu") or self.session is None:
            try:
                self.session = ort.InferenceSession(
                    str(self.model_path),
                    providers=["CPUExecutionProvider"]
                )
                return "ONNX Runtime (CPU)"
            except Exception as e:
                raise RuntimeError(f"All inference backends failed. Last error: {e}")
        raise RuntimeError("No inference backend could be initialized")
    def _get_io_names(self) -> Tuple[str, List[str]]:
        input_name = self.session.get_inputs()[0].name
        output_names = [output.name for output in self.session.get_outputs()]
        return input_name, output_names
    def _warmup(self) -> None:
        logger.info(f"Running {self.config.warmup_iterations} warm-up iterations...")
        dummy_frame = np.zeros(
            (self.config.input_size, self.config.input_size, 3),
            dtype=np.uint8
        )
        for i in range(self.config.warmup_iterations):
            try:
                self.detect(dummy_frame)
            except Exception as e:
                logger.warning(f"Warm-up iteration {i+1} failed: {e}")
        self.latencies.clear()
        logger.info("Warm-up complete")
    def detect(self, frame: np.ndarray) -> List[Detection]:
        self.total_frames += 1
        start_time = time.perf_counter()
        try:
            input_tensor, scale, pad_w, pad_h = self._preprocess(frame)
            outputs = self._run_inference(input_tensor)
            detections = self._postprocess(
                outputs, frame.shape, scale, pad_w, pad_h
            )
            latency_ms = (time.perf_counter() - start_time) * 1000
            self.latencies.append(latency_ms)
            if len(self.latencies) >= 100:
                p95 = np.percentile(self.latencies, 95)
                if p95 > self.config.latency_budget_ms:
                    logger.warning(
                        f"Latency budget exceeded! p95={p95:.1f}ms > {self.config.latency_budget_ms}ms"
                    )
            return detections
        except Exception as e:
            self.error_count += 1
            error_rate = self.error_count / self.total_frames
            logger.error(
                f"Detection failed on frame {self.total_frames}: {e} "
                f"(error_rate={error_rate:.3f})"
            )
            if error_rate > 0.1:
                logger.critical(
                    f"High error rate detected: {error_rate:.1%}. "
                    f"Check model compatibility and input format."
                )
            return []
    def _preprocess(self, frame: np.ndarray) -> Tuple[np.ndarray, float, int, int]:
        h, w = frame.shape[:2]
        target_size = self.config.input_size
        scale = min(target_size / h, target_size / w)
        new_h, new_w = int(h * scale), int(w * scale)
        resized = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
        letterboxed = np.full((target_size, target_size, 3), 114, dtype=np.uint8)
        pad_h = (target_size - new_h) // 2
        pad_w = (target_size - new_w) // 2
        letterboxed[pad_h:pad_h+new_h, pad_w:pad_w+new_w] = resized
        letterboxed = cv2.cvtColor(letterboxed, cv2.COLOR_BGR2RGB)
        img_float = letterboxed.astype(np.float32) / self.config.normalization.scale
        mean = np.array(self.config.normalization.mean, dtype=np.float32)
        std = np.array(self.config.normalization.std, dtype=np.float32)
        if not np.allclose(mean, 0.0) or not np.allclose(std, 1.0):
            img_float = (img_float - mean) / std
        img_transposed = np.transpose(img_float, (2, 0, 1))
        input_tensor = np.expand_dims(img_transposed, axis=0)
        return input_tensor, scale, pad_w, pad_h
    def _run_inference(self, input_tensor: np.ndarray) -> np.ndarray:
        outputs = self.session.run(
            self.output_names,
            {self.input_name: input_tensor}
        )
        return outputs[0]
    def _postprocess(
        self,
        outputs: np.ndarray,
        original_shape: Tuple[int, int, int],
        scale: float,
        pad_w: int,
        pad_h: int
    ) -> List[Detection]:
        predictions = outputs[0]
        boxes_xywh = predictions[:, :4]
        class_scores = predictions[:, 4:]
        class_ids = np.argmax(class_scores, axis=1)
        confidences = np.max(class_scores, axis=1)
        mask = confidences >= self.config.confidence_threshold
        boxes_xywh = boxes_xywh[mask]
        confidences = confidences[mask]
        class_ids = class_ids[mask]
        if len(boxes_xywh) == 0:
            return []
        boxes_xyxy = self._xywh_to_xyxy(boxes_xywh)
        keep_indices = self._nms(boxes_xyxy, confidences, self.config.nms_iou_threshold)
        boxes_xyxy = boxes_xyxy[keep_indices]
        confidences = confidences[keep_indices]
        class_ids = class_ids[keep_indices]
        if len(boxes_xyxy) > self.config.max_detections:
            sorted_indices = np.argsort(confidences)[::-1][:self.config.max_detections]
            boxes_xyxy = boxes_xyxy[sorted_indices]
            confidences = confidences[sorted_indices]
            class_ids = class_ids[sorted_indices]
        boxes_xyxy_original = self._transform_coords(
            boxes_xyxy, scale, pad_w, pad_h, original_shape
        )
        detections = []
        for bbox, conf, class_id in zip(boxes_xyxy_original, confidences, class_ids):
            detections.append(
                Detection(
                    bbox_xyxy=tuple(bbox.tolist()),
                    confidence=float(conf),
                    class_id=int(class_id),
                    class_name="pothole"
                )
            )
        return detections
    def _xywh_to_xyxy(self, boxes_xywh: np.ndarray) -> np.ndarray:
        boxes_xyxy = np.zeros_like(boxes_xywh)
        boxes_xyxy[:, 0] = boxes_xywh[:, 0] - boxes_xywh[:, 2] / 2
        boxes_xyxy[:, 1] = boxes_xywh[:, 1] - boxes_xywh[:, 3] / 2
        boxes_xyxy[:, 2] = boxes_xywh[:, 0] + boxes_xywh[:, 2] / 2
        boxes_xyxy[:, 3] = boxes_xywh[:, 1] + boxes_xywh[:, 3] / 2
        return boxes_xyxy
    def _nms(
        self,
        boxes: np.ndarray,
        scores: np.ndarray,
        iou_threshold: float
    ) -> np.ndarray:
        indices = cv2.dnn.NMSBoxes(
            bboxes=boxes.tolist(),
            scores=scores.tolist(),
            score_threshold=0.0,
            nms_threshold=iou_threshold
        )
        if len(indices) > 0:
            return indices.flatten()
        return np.array([], dtype=int)
    def _transform_coords(
        self,
        boxes_xyxy: np.ndarray,
        scale: float,
        pad_w: int,
        pad_h: int,
        original_shape: Tuple[int, int, int]
    ) -> np.ndarray:
        boxes_xyxy[:, [0, 2]] -= pad_w
        boxes_xyxy[:, [1, 3]] -= pad_h
        boxes_xyxy /= scale
        h, w = original_shape[:2]
        boxes_xyxy[:, [0, 2]] = np.clip(boxes_xyxy[:, [0, 2]], 0, w)
        boxes_xyxy[:, [1, 3]] = np.clip(boxes_xyxy[:, [1, 3]], 0, h)
        return boxes_xyxy
    def get_model_version(self) -> str:
        return self.config.model_version
    def get_latency_stats(self) -> dict:
        if len(self.latencies) == 0:
            return {"p50": 0, "p95": 0, "p99": 0, "count": 0}
        latencies_arr = np.array(self.latencies)
        return {
            "p50": float(np.percentile(latencies_arr, 50)),
            "p95": float(np.percentile(latencies_arr, 95)),
            "p99": float(np.percentile(latencies_arr, 99)),
            "count": len(self.latencies),
            "mean": float(np.mean(latencies_arr)),
        }
    def get_error_rate(self) -> float:
        if self.total_frames == 0:
            return 0.0
        return self.error_count / self.total_frames

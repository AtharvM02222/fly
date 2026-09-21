import time
from queue import Queue
from typing import Iterator, Optional
import cv2
import numpy as np
from config import CameraConfig
class CameraCapture:
    def __init__(self, config: CameraConfig):
        self.config = config
        self.cap: Optional[cv2.VideoCapture] = None
        self.frame_count = 0
        self.running = False
    def start(self) -> None:
        source = self.config.source
        if isinstance(source, int):
            self.cap = cv2.VideoCapture(source)
        else:
            self.cap = cv2.VideoCapture(source)
        if not self.cap or not self.cap.isOpened():
            raise RuntimeError(f"Failed to open video source: {source}")
        if self.config.width and self.config.height:
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.config.width)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.config.height)
        self.running = True
    def stop(self) -> None:
        self.running = False
        if self.cap:
            self.cap.release()
            self.cap = None
    def read_frame(self) -> Optional[np.ndarray]:
        if not self.cap or not self.cap.isOpened():
            return None
        ret, frame = self.cap.read()
        if not ret or frame is None:
            return None
        self.frame_count += 1
        return frame
    def sample_frames(self) -> Iterator[tuple[int, np.ndarray]]:
        sample_counter = 0
        while self.running:
            frame = self.read_frame()
            if frame is None:
                break
            sample_counter += 1
            if sample_counter % self.config.frame_sample_rate == 0:
                yield (self.frame_count, frame)
    def get_fps(self) -> float:
        if self.cap:
            return self.cap.get(cv2.CAP_PROP_FPS)
        return 0.0
    def get_resolution(self) -> tuple[int, int]:
        if self.cap:
            width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            return (width, height)
        return (0, 0)
    def __enter__(self):
        self.start()
        return self
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()

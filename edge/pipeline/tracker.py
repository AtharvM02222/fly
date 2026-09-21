import uuid
from dataclasses import dataclass, field
from typing import Dict, List
import numpy as np
from config import TrackerConfig
from .detector import Detection
def iou(bbox1: tuple[float, float, float, float], bbox2: tuple[float, float, float, float]) -> float:
    x1_max = max(bbox1[0], bbox2[0])
    y1_max = max(bbox1[1], bbox2[1])
    x2_min = min(bbox1[2], bbox2[2])
    y2_min = min(bbox1[3], bbox2[3])
    intersection_area = max(0, x2_min - x1_max) * max(0, y2_min - y1_max)
    bbox1_area = (bbox1[2] - bbox1[0]) * (bbox1[3] - bbox1[1])
    bbox2_area = (bbox2[2] - bbox2[0]) * (bbox2[3] - bbox2[1])
    union_area = bbox1_area + bbox2_area - intersection_area
    if union_area == 0:
        return 0.0
    return intersection_area / union_area
@dataclass
class Track:
    track_id: str
    bbox_xyxy: tuple[float, float, float, float]
    confidence: float
    class_id: int
    class_name: str
    hits: int = 0
    age: int = 0
    confirmed: bool = False
    buffered: bool = False
class Tracker:
    def __init__(self, config: TrackerConfig):
        self.config = config
        self.tracks: Dict[str, Track] = {}
    def update(self, detections: List[Detection]) -> List[Track]:
        for track in self.tracks.values():
            track.age += 1
        matched_tracks = set()
        matched_detections = set()
        for det_idx, detection in enumerate(detections):
            best_iou = 0.0
            best_track_id = None
            for track_id, track in self.tracks.items():
                if track_id in matched_tracks:
                    continue
                iou_value = iou(detection.bbox_xyxy, track.bbox_xyxy)
                if iou_value > self.config.iou_threshold and iou_value > best_iou:
                    best_iou = iou_value
                    best_track_id = track_id
            if best_track_id:
                track = self.tracks[best_track_id]
                track.bbox_xyxy = detection.bbox_xyxy
                track.confidence = detection.confidence
                track.hits += 1
                track.age = 0
                matched_tracks.add(best_track_id)
                matched_detections.add(det_idx)
                if track.hits >= self.config.min_hits:
                    track.confirmed = True
        for det_idx, detection in enumerate(detections):
            if det_idx not in matched_detections:
                track_id = str(uuid.uuid4())
                self.tracks[track_id] = Track(
                    track_id=track_id,
                    bbox_xyxy=detection.bbox_xyxy,
                    confidence=detection.confidence,
                    class_id=detection.class_id,
                    class_name=detection.class_name,
                    hits=1,
                    age=0,
                    confirmed=False,
                )
        stale_tracks = [
            track_id
            for track_id, track in self.tracks.items()
            if track.age > self.config.max_age
        ]
        for track_id in stale_tracks:
            del self.tracks[track_id]
        return [track for track in self.tracks.values() if track.confirmed and not track.buffered]
    def reset(self) -> None:
        self.tracks.clear()

# Golden Test Set for Detector

This directory contains golden test frames with hand-verified ground truth annotations for regression testing of the detector.

## Purpose

Golden tests ensure that:
1. Model outputs remain consistent across code changes
2. Preprocessing/postprocessing logic doesn't introduce bugs
3. Coordinate transformations are correct
4. Detection quality doesn't degrade over time

## Structure

```
golden/
├── README.md (this file)
├── annotations.json (ground truth bboxes)
├── frame_001.jpg (test image 1)
├── frame_002.jpg (test image 2)
└── ...
```

## Annotations Format

`annotations.json` contains hand-verified ground truth:

```json
{
  "frame_001.jpg": {
    "original_size": [1080, 1920],
    "detections": [
      {
        "bbox_xyxy": [450, 320, 650, 480],
        "confidence_min": 0.7,
        "class_name": "pothole",
        "notes": "Large pothole, center-left of frame"
      }
    ]
  }
}
```

## Adding New Golden Frames

1. Select representative frames (various lighting, angles, defect sizes)
2. Run detector and visually verify outputs
3. Manually annotate ground truth bboxes (use annotation tool or measure in image editor)
4. Add entry to `annotations.json`
5. Commit both image and annotation

## Running Golden Tests

```bash
# Run all golden tests
pytest tests/test_detector.py::TestGoldenFrames -v

# Run with marker
pytest -m golden
```

## Tolerance

- Bbox IoU should be > 0.85 (allowing small variations in NMS)
- Confidence should be within ±0.05 of expected
- Missing detections or false positives fail the test

## When Tests Fail

Golden test failures indicate:
1. **Regression**: Code change broke detection quality → fix the bug
2. **Model update**: New model has different (better?) outputs → review and update annotations
3. **Acceptable variation**: Minor numerical differences → adjust tolerance if justified

Never blindly update annotations to make tests pass. Always investigate root cause.

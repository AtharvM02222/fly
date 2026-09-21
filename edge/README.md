# Drone-CDS Edge Pipeline

Production-grade road defect detection pipeline for edge deployment on drone and vehicle-mounted cameras.

## Hardware Requirements

### Primary Target: NVIDIA Jetson Orin Nano

- **Compute**: 6-core Arm CPU + NVIDIA Ampere GPU (1024 CUDA cores)
- **Memory**: 8GB unified RAM
- **Storage**: 64GB+ eMMC/SD card
- **Camera**: USB/MIPI camera (1080p @ 30fps minimum)
- **GPS**: USB/Serial GPS module (NMEA compatible)
- **Power**: 10-25W TDP

### CPU Fallback: Raspberry Pi 5

- **Compute**: Quad-core Arm Cortex-A76
- **Memory**: 8GB RAM
- **Storage**: 64GB+ SD card
- **Camera**: USB/CSI camera
- **GPS**: USB GPS module
- **Performance**: ~3-5 FPS with ONNX CPU backend

### Development: x86_64 Laptop/Desktop

- **Recommended**: 16GB+ RAM, 4+ cores
- **GPU**: Optional (CUDA for faster inference)
- **OS**: Linux, macOS, or Windows with WSL2

## Software Dependencies

### Core Requirements

```bash
# Python 3.10+
python >= 3.10

# ONNX Runtime (auto-selects backend)
pip install onnxruntime-gpu  # For CUDA
pip install onnxruntime       # CPU fallback

# Computer Vision
opencv-python >= 4.9.0
numpy >= 1.26.0

# Other dependencies in requirements.txt
```

### Installing on Jetson Orin Nano

```bash
# Use JetPack SDK for CUDA/TensorRT
# Install onnxruntime-gpu from NVIDIA wheels
pip install onnxruntime-gpu --extra-index-url https://pypi.nvidia.com
```

## Setup

### 1. Install Dependencies

```bash
cd edge/
pip install -r requirements.txt
```

### 2. Provide Model Weights

The detector requires trained YOLOv8n weights. Place model files in `models/`:

```
edge/models/
├── pothole.onnx     # ONNX model (required)
└── pothole.engine   # TensorRT engine (optional, for Jetson)
```

**Generate checksum** for weights verification:

```bash
sha256sum models/pothole.onnx
# Output: abc123... models/pothole.onnx

# Update config/default.yaml:
# weights_checksum: "sha256:abc123..."
```

### 3. Configure

Copy and edit configuration:

```bash
cp config/default.yaml config/production.yaml
nano config/production.yaml
```

**Key settings to update:**

```yaml
device:
  id: "your-device-id"           # Unique device identifier
  api_key: "your-api-key"        # Get from backend admin

backend:
  url: "https://your-backend.com/api/v1"

camera:
  source: 0                       # Camera index, or "/dev/video0", or "rtsp://..."

detector:
  model_path: "models/pothole.onnx"
  weights_checksum: "sha256:YOUR_ACTUAL_CHECKSUM"
  backend: "auto"                 # auto, tensorrt, onnx-cuda, onnx-cpu
  confidence_threshold: 0.5
  latency_budget_ms: 100          # Warn if p95 latency exceeds this

gps:
  source: "/dev/ttyUSB0"          # GPS serial port, or "mock" for testing
```

### 4. Test with Mock Detector

Before using real model weights, test the pipeline end-to-end with synthetic detections:

```bash
python main.py --detector mock --log-level INFO
```

This validates:
- Camera capture
- GPS reading
- Buffer persistence
- Backend connectivity
- All module integration

### 5. Run with Real Detector

Once you have model weights:

```bash
python main.py --detector real --config config/production.yaml
```

**Monitor logs for:**
- Backend selection: `Detector backend: ONNX Runtime (CUDA)`
- Latency stats: `Latency p50/p95=45.2/87.3ms`
- Detection confirmations: `Confirmed detection: severity=high, confidence=0.87`

## Camera Setup

### USB Camera

```yaml
camera:
  source: 0  # First USB camera
```

Test camera:

```bash
python -c "import cv2; cap = cv2.VideoCapture(0); print('Camera OK:', cap.isOpened())"
```

### RTSP Stream

```yaml
camera:
  source: "rtsp://192.168.1.100:8554/stream"
```

### Video File (for testing)

```yaml
camera:
  source: "/path/to/test_video.mp4"
```

## GPS Setup

### Serial GPS (NMEA)

```yaml
gps:
  source: "/dev/ttyUSB0"
  baud_rate: 9600
```

Find GPS device:

```bash
ls /dev/tty* | grep USB
dmesg | grep tty  # Check kernel logs
```

Test GPS:

```bash
cat /dev/ttyUSB0  # Should show NMEA sentences like $GPGGA,...
```

### Mock GPS (for testing)

```yaml
gps:
  source: "mock"
```

Mock GPS generates a synthetic path around a starting location.

## Deployment

### Docker (Recommended)

```bash
# Build for target architecture
docker build -t drone-cds-edge:latest -f edge/Dockerfile .

# Run with hardware access
docker run --rm \
  --privileged \
  --device=/dev/video0 \
  --device=/dev/ttyUSB0 \
  -v $(pwd)/config:/app/config:ro \
  -v $(pwd)/models:/app/models:ro \
  -v $(pwd)/buffer.db:/app/buffer.db \
  drone-cds-edge:latest \
  --detector real --config config/production.yaml
```

### Systemd Service

For bare-metal deployment, create `/etc/systemd/system/drone-cds.service`:

```ini
[Unit]
Description=Drone-CDS Edge Pipeline
After=network.target

[Service]
Type=simple
User=drone-cds
WorkingDirectory=/opt/drone-cds/edge
ExecStart=/opt/drone-cds/venv/bin/python main.py --detector real --config config/production.yaml
Restart=on-failure
RestartSec=30

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl enable drone-cds
sudo systemctl start drone-cds
sudo journalctl -u drone-cds -f  # View logs
```

## Performance Tuning

### Jetson Orin Nano

```bash
# Max performance mode
sudo nvpmodel -m 0
sudo jetson_clocks

# Monitor GPU/CPU usage
tegrastats

# Check temperature
cat /sys/devices/virtual/thermal/thermal_zone*/temp
```

### Latency Optimization

```yaml
camera:
  frame_sample_rate: 5  # Process every 5th frame (12 FPS @ 60 FPS camera)

detector:
  input_size: 640       # Smaller = faster, less accurate
  quantization: "fp16"  # Enable FP16 on supported hardware
  latency_budget_ms: 80 # Tighter budget
```

### Memory Optimization

```yaml
camera:
  queue_max_size: 5     # Reduce frame buffer

tracker:
  max_age: 20           # Drop tracks faster

buffer:
  cleanup_after_days: 3 # Clean uploaded records sooner
```

## Troubleshooting

### Weights Checksum Mismatch

```
ValueError: Weights checksum mismatch!
Expected: abc123...
Actual:   def456...
```

**Fix**: Recompute checksum and update config:

```bash
sha256sum models/pothole.onnx
# Update weights_checksum in config
```

### Backend Initialization Failed

```
RuntimeError: All inference backends failed.
```

**Fixes**:
1. Check ONNX Runtime installation: `python -c "import onnxruntime; print(onnxruntime.get_available_providers())"`
2. Verify model file is valid ONNX: `python -c "import onnx; onnx.checker.check_model('models/pothole.onnx')"`
3. Try CPU backend explicitly: `backend: "onnx-cpu"`

### High Latency

```
WARNING - Latency budget exceeded! p95=150.2ms > 100ms
```

**Fixes**:
1. Reduce input size: `input_size: 416`
2. Increase frame sample rate: `frame_sample_rate: 5`
3. Enable FP16 quantization (Jetson only): `quantization: "fp16"`
4. Check CPU/GPU load: `top`, `tegrastats`

### GPS Unavailable

```
WARNING - GPS unavailable and interpolation failed - skipping
```

**Fixes**:
1. Check GPS device: `ls -l /dev/ttyUSB0`
2. Check permissions: `sudo chmod 666 /dev/ttyUSB0`
3. Verify GPS has satellite fix: `cat /dev/ttyUSB0` (look for valid $GPGGA)
4. Enable interpolation: `gps.interpolation.enabled: true`

### Upload Failures

```
WARNING - Failed to upload detection ... (retry 3/10)
```

**Fixes**:
1. Check backend connectivity: `curl https://backend/api/v1/healthz`
2. Verify API key: Check `device.api_key` in config
3. Check network: `ping backend-host`
4. Detections are buffered durably - will retry automatically

## Testing

### Unit Tests

```bash
cd edge/
pytest tests/test_detector.py -v
pytest tests/test_tracker.py -v
pytest tests/test_buffer.py -v
```

### Integration Test (Mock Detector)

```bash
# Terminal 1: Start backend
cd backend/
docker-compose up

# Terminal 2: Run edge with mock detector
cd edge/
python main.py --detector mock
```

### Soak Test (Memory Leak Detection)

```bash
# Short soak test (10k frames, ~10 minutes)
pytest tests/test_detector_soak.py::TestDetectorSoak::test_mock_detector_memory_leak -v

# Manual extended soak test (run for 1+ hours)
python tests/test_detector_soak.py
```

### Golden Frame Tests

```bash
# Add real frames to tests/golden/ with annotations.json
pytest tests/test_detector.py::TestGoldenFrames -v
```

## Model Training

The detector expects a YOLOv8n model trained on pothole data. Export to ONNX:

```python
from ultralytics import YOLO

# Train
model = YOLO('yolov8n.pt')
model.train(data='pothole.yaml', epochs=100, imgsz=640)

# Export to ONNX
model.export(format='onnx', opset=12, simplify=True)

# Result: runs/detect/train/weights/best.onnx
```

**For TensorRT on Jetson:**

```bash
trtexec --onnx=best.onnx \
        --saveEngine=pothole.engine \
        --fp16 \
        --workspace=4096 \
        --verbose
```

Copy to `edge/models/`:

```bash
cp runs/detect/train/weights/best.onnx edge/models/pothole.onnx
cp pothole.engine edge/models/pothole.engine
```

## Monitoring

### Latency Statistics

Logged every 100 frames:

```
Latency p50/p95=45.2/87.3ms, Error rate=0.00%
```

- **p50**: Median latency (should be < 50ms on Jetson)
- **p95**: 95th percentile (should be < latency_budget_ms)
- **Error rate**: Fraction of frames that failed detection

### Buffer Statistics

Logged on each uplink:

```
Buffer stats: pending=5, uploaded=243, failed=0
```

- **pending**: Waiting for upload
- **uploaded**: Successfully uploaded
- **failed**: Max retries exceeded (investigate!)

### Detection Rate

Logged on confirmation:

```
Confirmed detection: severity=high, confidence=0.87, GPS=live
```

Track these over time:
- Detections per kilometer
- False positive rate (manual review)
- GPS interpolation rate

## Production Checklist

- [ ] Model weights provided and checksum verified
- [ ] Config updated with production backend URL and API key
- [ ] Camera and GPS hardware tested and accessible
- [ ] Detector runs without errors for 1+ hours (soak test)
- [ ] Latency p95 < budget on target hardware
- [ ] Buffer persists detections across restarts
- [ ] Uplink successfully reaches backend
- [ ] Systemd service configured with auto-restart
- [ ] Monitoring/alerting configured for device offline
- [ ] Backup power supply tested (drones/vehicles)

## Support

For issues:
1. Check logs: `journalctl -u drone-cds -f`
2. Review RUNBOOK.md for common procedures
3. Check GitHub issues
4. Contact: dev-team@drone-cds.example

## License

[Your License Here]

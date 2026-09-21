# Drone-CDS v2

**Production road-defect (pothole) detection and alerting system for drone/vehicle-mounted cameras.**

Drone-CDS v2 is a full-stack edge-to-cloud system that performs real-time pothole detection on edge devices (Jetson Orin Nano, Raspberry Pi 5), uploads confirmed detections to a central backend with geospatial deduplication, and provides an operational dashboard for fleet monitoring and work order management.

## Architecture

- **Edge Pipeline**: YOLOv8n-based detection running on-device with TensorRT/ONNX Runtime, GPS tracking, multi-frame confirmation, durable buffering, and automatic uplink
- **Backend API**: FastAPI + Postgres/PostGIS with geohash-based deduplication, device authentication, and notification management
- **Dashboard**: Next.js admin/ops interface with map view, detection management, device fleet monitoring, and CSV/PDF export

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for detailed system design.

## Quick Start

### Prerequisites

- Docker & Docker Compose
- Python 3.11+ (for local edge development)
- Node.js 18+ (for local dashboard development)
- For edge deployment: Jetson Orin Nano with JetPack 5.x or Raspberry Pi 5

### Local Development Setup

1. **Clone and configure**
   ```bash
   git clone <repository-url>
   cd drone-cds
   cp .env.example .env
   # Edit .env with your configuration
   ```

2. **Start all services**
   ```bash
   docker-compose -f infra/docker-compose.yml up -d
   ```

   This starts:
   - Postgres with PostGIS (port 5432)
   - Redis (port 6379)
   - Backend API (port 8000)
   - Dashboard (port 3000)
   - MinIO (S3-compatible storage, port 9000)

3. **Run database migrations**
   ```bash
   docker-compose -f infra/docker-compose.yml exec backend alembic upgrade head
   ```

4. **Create first admin user**
   ```bash
   docker-compose -f infra/docker-compose.yml exec backend python -m backend.scripts.create_admin \
     --email admin@example.com \
     --password changeme
   ```

5. **Generate device API key**
   ```bash
   docker-compose -f infra/docker-compose.yml exec backend python -m backend.scripts.create_device \
     --name "Test Device" \
     --type drone
   ```
   Save the returned API key to `.env` as `EDGE_DEVICE_API_KEY`.

6. **Access the system**
   - Dashboard: http://localhost:3000
   - API docs: http://localhost:8000/docs
   - MinIO console: http://localhost:9001

### Running the Edge Pipeline

The edge pipeline runs on the drone/vehicle device and can be tested locally:

```bash
# Install edge dependencies
cd edge
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows
pip install -r requirements.txt

# Configure
cp ../.env.example .env
# Edit .env with EDGE_* variables

# Run with mock detector (for testing without model weights)
python main.py --detector mock

# Run with real detector (requires model weights)
# Place models/pothole.onnx or models/pothole.engine in the project root
python main.py
```

See [edge/README.md](edge/README.md) for deployment to Jetson/Raspberry Pi.

## Providing Model Weights

Drone-CDS expects a YOLOv8n model trained on pothole detection. The model should be exported to ONNX or TensorRT format.

1. **Export to ONNX** (from your training environment):
   ```python
   from ultralytics import YOLO
   model = YOLO('path/to/trained/best.pt')
   model.export(format='onnx', imgsz=640, simplify=True)
   ```

2. **Place weights** in `models/` directory:
   ```
   models/
   ├── pothole.onnx        # For CPU or ONNX Runtime + CUDA
   └── pothole.engine      # For TensorRT (Jetson)
   ```

3. **Calculate checksum**:
   ```bash
   sha256sum models/pothole.onnx
   # Update EDGE_DETECTOR_WEIGHTS_CHECKSUM in .env
   ```

The edge pipeline will automatically select the best available backend (TensorRT → ONNX+CUDA → ONNX CPU) and verify the checksum before loading.

## Development Workflow

### Pre-commit Hooks

Install pre-commit hooks to ensure code quality:

```bash
pip install pre-commit
pre-commit install
```

This runs linters and formatters on every commit:
- Python: ruff, black, mypy
- TypeScript: eslint, prettier
- Checks: trailing whitespace, YAML validity, merge conflict markers

### Running Tests

**Backend:**
```bash
cd backend
pytest                          # All tests
pytest tests/integration/       # Integration tests only
pytest --cov=app --cov-report=html  # With coverage
```

**Edge:**
```bash
cd edge
pytest                          # All tests
pytest -k "not soak"            # Skip long-running soak tests
pytest tests/test_detector.py   # Detector tests only
```

**Dashboard:**
```bash
cd dashboard
npm test                        # Component tests
npm run test:e2e                # End-to-end tests
```

### CI/CD

GitHub Actions runs on every push:
- Lint and typecheck all codebases
- Run unit and integration tests
- Build Docker images
- On `main` branch: push images to registry with `latest` tag

See `.github/workflows/` for pipeline definitions.

## Project Structure

```
drone-cds/
├── edge/                   # Edge detection pipeline
│   ├── pipeline/           # Core modules (capture, detector, tracker, etc.)
│   ├── config/             # Configuration schema and defaults
│   ├── tests/              # Edge tests including golden frames
│   └── main.py             # Pipeline entry point
├── backend/                # FastAPI backend
│   ├── app/
│   │   ├── api/            # REST API routes
│   │   ├── core/           # Auth, config, logging
│   │   ├── db/             # Models and session management
│   │   └── services/       # Business logic (dedup, notifications)
│   ├── alembic/            # Database migrations
│   └── tests/              # Backend tests
├── dashboard/              # Next.js dashboard
│   ├── app/                # App router pages
│   ├── components/         # React components
│   └── lib/                # Utilities and API client
├── infra/                  # Docker Compose and deployment configs
├── docs/                   # Documentation and ADRs
└── models/                 # Model weights (not checked in)
```

## API Documentation

Full API documentation is available at:
- Interactive docs: http://localhost:8000/docs (Swagger UI)
- OpenAPI schema: http://localhost:8000/api/v1/openapi.json
- Written guide: [docs/API.md](docs/API.md)

## Operations

### Device Down Procedure

If a device stops reporting:
1. Check `last_seen_at` in dashboard device fleet page
2. SSH to device and check edge service logs
3. Verify GPS lock and camera connectivity
4. Restart edge service or reboot device

See [docs/RUNBOOK.md](docs/RUNBOOK.md) for detailed procedures.

### Manual Deduplication

If deduplication fails for a batch:
```bash
docker-compose -f infra/docker-compose.yml exec backend python -m backend.scripts.rerun_dedup \
  --start-date 2026-09-20 \
  --end-date 2026-09-21
```

### API Key Rotation

1. Generate new key via dashboard or CLI
2. Update device configuration with new key
3. Verify device reconnects successfully
4. Revoke old key in dashboard

## Monitoring

**Backend Metrics** (Prometheus format at `/metrics`):
- Request latency by endpoint
- Ingest volume (detections/minute)
- Deduplication merge rate
- Active device count

**Edge Metrics** (logged locally):
- Inference latency (p50/p95/p99)
- Detection rate
- Frame processing rate
- Buffer size and uplink success rate

## Contributing

1. Create a feature branch from `main`
2. Make changes with tests
3. Ensure pre-commit hooks pass
4. Open a pull request with description

## License

[To be determined]

## Support

For issues and questions:
- GitHub Issues: [repository-url]/issues
- Documentation: [docs/](docs/)
- Architecture decisions: [docs/ADR/](docs/ADR/)

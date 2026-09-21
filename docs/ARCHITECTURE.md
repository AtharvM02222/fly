# Drone-CDS v2 Architecture

## System Overview

Drone-CDS v2 is a production-grade road defect detection and alerting system designed for edge deployment on drone and vehicle-mounted cameras. The system performs real-time pothole detection on-device, uploads confirmed detections to a central backend with intelligent deduplication, and provides an operational dashboard for monitoring and work order management.

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      EDGE DEVICES                           │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  │
│  │ Capture  │→ │ Detector │→ │ Tracker  │→ │ Severity │  │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘  │
│       ↓             ↓              ↓              ↓         │
│  ┌──────────┐  ┌──────────────────────────────────────┐  │
│  │   GPS    │→ │           Buffer (SQLite)            │  │
│  └──────────┘  └──────────────────────────────────────┘  │
│                             ↓                              │
│                      ┌──────────┐                         │
│                      │  Uplink  │                         │
│                      └──────────┘                         │
└─────────────────────────┬───────────────────────────────┘
                          │ HTTPS + Device API Key
                          ↓
┌─────────────────────────────────────────────────────────────┐
│                     BACKEND (FastAPI)                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │
│  │   Detections │→ │     Dedup    │→ │ Notification │    │
│  │   API        │  │   Service    │  │   Service    │    │
│  └──────────────┘  └──────────────┘  └──────────────┘    │
│         ↓                ↓                   ↓              │
│  ┌─────────────────────────────────────────────────────┐  │
│  │     Postgres + PostGIS + Redis + S3 Storage         │  │
│  └─────────────────────────────────────────────────────┘  │
└────────────────────────────┬────────────────────────────────┘
                             │ REST API + JWT Auth
                             ↓
┌─────────────────────────────────────────────────────────────┐
│                 DASHBOARD (Next.js)                          │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  │
│  │   Map    │  │Detection │  │  Device  │  │ Reports  │  │
│  │   View   │  │  Detail  │  │  Fleet   │  │  Export  │  │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘  │
└─────────────────────────────────────────────────────────────┘
```

## Core Design Decisions

### 1. Edge Inference (Not Cloud Streaming)

**Decision:** All detection runs on-device. Only confirmed detections with metadata and compressed images are uploaded to the backend.

**Rationale:**
- **Bandwidth efficiency:** Streaming video from multiple drones/vehicles is prohibitively expensive
- **Latency:** Real-time detection without round-trip to server
- **Offline operation:** Devices continue detecting during network outages, buffering for later upload
- **Privacy:** Raw video never leaves the device

**Tradeoffs:**
- Requires compute-capable edge hardware (Jetson Orin Nano, Raspberry Pi 5)
- Model deployment and version management across fleet
- Limited by on-device GPU/CPU resources

See [ADR-001: Edge vs Server Inference](ADR/001-edge-vs-server-inference.md)

### 2. Postgres + PostGIS for Geospatial Storage

**Decision:** Use Postgres with PostGIS extension for primary data storage.

**Rationale:**
- **Native geospatial support:** Built-in geography types, distance calculations, spatial indexing (GIST)
- **ACID guarantees:** Critical for deduplication and audit trails
- **Mature ecosystem:** Well-understood operations, backup, scaling patterns
- **Query flexibility:** Complex spatial + temporal + status queries in a single system

**Alternatives considered:**
- MongoDB: Weaker transactional guarantees, less mature geospatial querying
- TimescaleDB: Strong for time-series, but geospatial support less mature than PostGIS

See [ADR-002: Postgres + PostGIS](ADR/002-postgres-postgis.md)

### 3. Geohash + Haversine Deduplication

**Decision:** Use geohash for coarse spatial bucketing, then Haversine distance for precise matching within a time window.

**Rationale:**
- **Performance:** Geohash (precision 7 ≈ 150m cells) creates a btree-indexable prefix for fast candidate retrieval
- **Boundary handling:** Haversine distance check catches detections on opposite sides of geohash cell boundaries
- **Time window:** Prevents merging detections of the same pothole months apart (legitimate re-detection)
- **Configurability:** Distance and time thresholds can be tuned based on operational experience

See [ADR-003: Geohash Deduplication](ADR/003-geohash-dedup.md)

## Component Details

### Edge Pipeline

**Target Hardware:**
- Primary: NVIDIA Jetson Orin Nano (8GB, CUDA + TensorRT)
- Fallback: Raspberry Pi 5 (8GB, CPU-only ONNX Runtime)

**Detector Module (`detector.py`)** — Highest quality bar in the system:
- **Input:** BGR frame (HxWx3 uint8) from capture module
- **Output:** List of `{bbox_xyxy, confidence, class_id, class_name}` in original frame coordinates
- **Preprocessing:** Aspect-ratio-preserving letterbox resize, normalization from config (no magic numbers)
- **Inference backends:** TensorRT engine → ONNX Runtime + CUDA → ONNX Runtime CPU (auto-detected at runtime)
- **Postprocessing:**
  - Class-aware NMS with config-driven IoU threshold
  - **Coordinate transform from letterboxed space back to original frame** (dedicated unit test)
  - Clip to frame bounds, cap max detections
- **Error handling:** Per-frame timeout, rolling error rate tracking
- **Observability:** Per-frame latency logged, p50/p95/p99 tracked against latency budget
- **Integrity:** Checksum verification of weights file before loading

**Tracker Module (`tracker.py`):**
- IoU-based multi-frame tracking
- Assigns stable `track_id` across frames
- Only emits "confirmed" detection after N consecutive hits (config-driven, prevents single-frame flicker)

**Severity Module (`severity.py`):**
- Pure function: `(bbox_area, confidence, camera_config) → severity`
- Formula uses camera height/angle from config (no hardcoded constants)
- Output: `low`, `medium`, `high`

**Geo Module (`geo.py`):**
- Reads GPS from serial/BLE
- On dropout: interpolates from last-known + speed/IMU if available
- Flags interpolated points with `is_interpolated=True`

**Buffer Module (`buffer.py`):**
- SQLite with write-ahead logging (WAL mode)
- Durably writes every confirmed detection before uplink attempt
- Marks uploaded only on backend 2xx response
- Retries failed uploads with exponential backoff

**Uplink Module (`uplink.py`):**
- Batches pending detections (configurable batch size)
- Device API key authentication
- Exponential backoff with jitter on failure
- Idempotent via `client_detection_id`

### Backend

**Technology Stack:**
- FastAPI (async Python web framework)
- SQLAlchemy 2.0 (async ORM)
- Alembic (database migrations)
- Redis (rate limiting, caching)
- Boto3 (S3-compatible storage for images)

**Database Schema:**

```sql
-- Device identity and authentication
devices (
  id UUID PRIMARY KEY,
  name TEXT NOT NULL,
  api_key_hash TEXT UNIQUE NOT NULL,  -- hashed at rest
  device_type TEXT NOT NULL,          -- drone | vehicle | fixed
  last_seen_at TIMESTAMPTZ,
  status TEXT,                        -- online | offline | maintenance
  created_at TIMESTAMPTZ NOT NULL
)

-- Detection records
detections (
  id UUID PRIMARY KEY,
  client_detection_id UUID UNIQUE NOT NULL,  -- for idempotency
  device_id UUID REFERENCES devices(id),
  location GEOGRAPHY(POINT, 4326) NOT NULL,  -- PostGIS geography type
  geohash TEXT NOT NULL,                     -- for dedup indexing
  severity TEXT NOT NULL,                    -- low | medium | high
  confidence FLOAT NOT NULL,
  status TEXT DEFAULT 'new',                 -- new → confirmed → assigned → fixed → verified
  image_url TEXT,
  bbox JSONB,
  model_version TEXT,
  detected_at TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ NOT NULL,
  merged_into UUID REFERENCES detections(id) -- for deduplicated records
)

-- Audit trail for status changes
detection_events (
  id UUID PRIMARY KEY,
  detection_id UUID REFERENCES detections(id),
  event_type TEXT NOT NULL,             -- created | merged | status_change | note_added
  actor TEXT,                            -- user email or system
  note TEXT,
  created_at TIMESTAMPTZ NOT NULL
)

-- Dashboard user authentication
users (
  id UUID PRIMARY KEY,
  email TEXT UNIQUE NOT NULL,
  role TEXT NOT NULL,                   -- admin | operator | viewer
  password_hash TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL
)

-- Dashboard notifications
notifications (
  id UUID PRIMARY KEY,
  detection_id UUID REFERENCES detections(id),
  status TEXT DEFAULT 'unread',         -- unread | read
  created_at TIMESTAMPTZ NOT NULL
)

-- Indexes
CREATE INDEX idx_detections_location ON detections USING GIST(location);
CREATE INDEX idx_detections_geohash ON detections(geohash);
CREATE INDEX idx_detections_status_time ON detections(status, detected_at);
CREATE UNIQUE INDEX idx_detections_client_id ON detections(client_detection_id);
```

**API Contract (REST, versioned as `/api/v1`):**

```
POST   /detections          - Batch ingest (device API key auth, 202 Accepted)
GET    /detections          - List with filters (bbox/status/severity/date, cursor pagination)
GET    /detections/{id}     - Single detection with event history
PATCH  /detections/{id}     - Status transition (operator+ role required)

GET    /devices             - List devices (admin only)
POST   /devices             - Create device, generate API key (admin only)
GET    /devices/{id}/heartbeat - Update last_seen_at

POST   /auth/login          - JWT authentication (email/password → token)

GET    /notifications       - Unread notifications
PATCH  /notifications/{id}/read - Mark as read

GET    /reports/export      - CSV/PDF export with filters

GET    /healthz             - Liveness check
GET    /readyz              - Readiness check (verifies DB connection)
GET    /metrics             - Prometheus-format metrics
```

**Error Response Format:**
```json
{
  "error_code": "DETECTION_NOT_FOUND",
  "message": "Detection with id xyz not found",
  "details": { ... }
}
```

**Deduplication Service (`services/dedup.py`):**
1. Calculate geohash at precision 7 (~150m cells)
2. Query existing non-fixed detections in same geohash within time window (e.g., 5 minutes)
3. For each candidate, calculate Haversine distance
4. If match found within distance threshold:
   - Set `merged_into` FK on new detection
   - Create `detection_event` with `type=merged`
5. Else: detection remains standalone (potentially triggers notification)

**Notification Service (`services/notifier.py`):**
- Abstract `Notifier` interface: `send(detection: Detection)`
- v1 implementation: `DashboardNotifier` writes to `notifications` table
- Triggered only for genuinely new (non-merged) detections above severity threshold
- Per-geohash cooldown to prevent duplicate alerts from multiple devices covering same road
- Future: Add `SlackNotifier`, `EmailNotifier`, etc. without touching detection/dedup logic

### Dashboard

**Technology Stack:**
- Next.js 14 (App Router)
- TypeScript (strict mode)
- TailwindCSS (styling)
- Mapbox GL JS or Leaflet (map visualization)

**Authentication:**
- JWT tokens from backend `/auth/login`
- Stored in httpOnly cookies or localStorage
- Auto-refresh on expiry

**Role-Based Access Control:**
- **Viewer:** Read-only access to map, detections, reports
- **Operator:** Can change detection status, add notes
- **Admin:** Full access including device management, user management

**Key Pages:**

1. **Map View** (`/map`)
   - Detection pins colored by severity
   - Clustering at low zoom levels
   - Filters: status, date range, device, severity
   - Click pin → summary popup → link to detail page

2. **Detection Detail** (`/detections/[id]`)
   - Image display
   - All metadata: confidence, severity, GPS (with interpolation flag), bbox, model version
   - Full audit trail from `detection_events`
   - Status transition form (operator+ role only)
   - Link to merged parent if applicable

3. **Notifications** (header dropdown)
   - Unread count badge
   - Recent notifications list
   - Mark as read
   - Jump to detection on click

4. **Device Fleet** (`/devices`)
   - Table: name, type, last_seen_at, online/offline, detection count
   - Online = `last_seen_at` within last 5 minutes
   - Click device → device detail page with detection list

5. **Reports** (`/reports`)
   - Filter UI (same as map)
   - Export button: CSV or PDF
   - Triggers backend `/reports/export` endpoint

## Security Model

**Device Authentication:**
- Each device has a unique API key (generated on device creation)
- API keys hashed at rest in database (using bcrypt or similar)
- Transmitted in `Authorization: Bearer <api_key>` header
- Rate limited per device key (e.g., 100 requests/minute)

**Dashboard User Authentication:**
- Email/password → JWT token
- JWT secret from environment variable (never in code)
- Token expiry: 24 hours (configurable)
- Password hashing: bcrypt with appropriate cost factor

**Network Security:**
- TLS/HTTPS in production (Nginx reverse proxy terminates SSL)
- CORS configured to allow only dashboard origin
- No secrets in Docker images or code

## Observability

**Metrics (Backend `/metrics` in Prometheus format):**
- `http_requests_total{method, endpoint, status}` - Request count
- `http_request_duration_seconds{endpoint}` - Latency histogram
- `detections_ingested_total{device_id}` - Ingest volume
- `detections_merged_total` - Deduplication rate
- `devices_active` - Active device count (last_seen < 5min)

**Metrics (Edge, logged locally):**
- Inference latency (p50, p95, p99) per metrics interval
- Detection rate (detections/minute)
- Frame processing rate (FPS)
- Buffer size (pending uploads)
- Uplink success/failure rate

**Logging:**
- Structured JSON logs on both edge and backend
- Request IDs propagated through backend call chain
- Log levels: DEBUG, INFO, WARNING, ERROR, CRITICAL
- Sensitive data (API keys, passwords) never logged

## Deployment

**Edge Devices:**
- Dockerized or bare-metal Python 3.11+
- Model weights deployed via separate mechanism (not in Docker image)
- Configuration via YAML file + environment variable overrides
- Systemd service for auto-restart on failure

**Backend + Dashboard:**
- Docker Compose for local development
- Production: Kubernetes or Docker Swarm (horizontal scaling)
- Database migrations via Alembic (run before container start)
- Image registry: AWS ECR, Google Artifact Registry, or private Harbor

**CI/CD:**
- GitHub Actions on every PR: lint, typecheck, test, build
- On merge to `main`: push images to registry with `latest` tag
- Pre-commit hooks enforce code quality locally

## Scaling Considerations

**Edge:**
- Each device operates independently
- No horizontal scaling needed (1 device = 1 pipeline instance)

**Backend:**
- Stateless API servers → horizontal scaling via load balancer
- Database: Read replicas for GET-heavy workloads
- Redis: Cluster mode for high rate-limiting throughput
- S3 storage: Infinite horizontal scaling

**Dashboard:**
- Stateless Next.js server → horizontal scaling
- CDN for static assets

## Future Enhancements

- Real-time dashboard updates via WebSockets or SSE
- Mobile app for field operators
- Integration with GIS/work-order systems (Esri ArcGIS, Trimble)
- Model retraining pipeline with active learning
- Multi-tenant deployment (separate fleets per organization)
- Advanced analytics: defect density heatmaps, severity trends over time

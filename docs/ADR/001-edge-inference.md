# ADR 001: Edge Inference Architecture

**Status:** Accepted  
**Date:** 2026-09-01  
**Deciders:** Architecture Team

## Context

Road defect detection requires processing video frames from drone/vehicle-mounted cameras. Two architectural approaches were considered:

1. **Edge Inference**: Run detection models on-device, upload only confirmed detections
2. **Server Inference**: Stream video to cloud, run detection centrally

## Decision

We will run inference **on the edge device** (drone/vehicle-mounted computer).

## Rationale

### Advantages of Edge Inference

1. **Bandwidth Efficiency**
   - Video: ~30 Mbps for 1080p @ 30fps
   - Detections: ~10 KB per detection (metadata + compressed image)
   - **Savings**: 99.9% reduction in upload bandwidth
   - Critical for cellular connections with limited/expensive data

2. **Latency**
   - Edge: ~50ms detection latency
   - Cloud: 50ms + 100-500ms network round-trip
   - Real-time response needed for autonomous vehicle integration

3. **Offline Operation**
   - Devices continue detecting during network outages
   - Detections buffered durably in SQLite
   - Uploads resume automatically when connectivity restored

4. **Privacy**
   - Video never leaves device
   - Only confirmed detections uploaded
   - Reduces exposure of potentially sensitive footage

5. **Cost**
   - Cellular data: $10-50/GB
   - Edge compute: One-time hardware cost (~$500/device)
   - **ROI**: Break-even after 1-2 months for fleet of 10+ devices

### Disadvantages Accepted

1. **Device Requirements**
   - Need GPU-capable edge device (Jetson Orin Nano ~$500)
   - Higher upfront hardware cost vs simpler capture-only device
   - **Mitigation**: CPU fallback for low-cost Raspberry Pi 5

2. **Model Deployment Complexity**
   - Must update models on all edge devices
   - Version management across fleet
   - **Mitigation**: Centralized model registry (future Phase 8)

3. **Heterogeneous Performance**
   - Different devices have different capabilities
   - Jetson: 15 FPS, Pi 5: 3-5 FPS
   - **Mitigation**: Config-driven performance tuning per device

## Alternatives Considered

### Alternative 1: Server-Side Inference

**Pros:**
- Centralized model management
- Unlimited compute scaling
- Easier debugging (all data in one place)

**Cons:**
- **Bandwidth**: Prohibitive for fleet (100+ GB/day/device)
- **Latency**: Unacceptable for real-time use cases
- **Offline**: Cannot operate without connectivity
- **Cost**: Cellular data costs 10x hardware cost over 1 year

**Decision**: Rejected due to bandwidth and offline requirements.

### Alternative 2: Hybrid (Edge Filtering + Cloud Inference)

Run lightweight filter on edge, send candidates to cloud for full inference.

**Pros:**
- Reduced bandwidth vs full streaming
- Centralized model management

**Cons:**
- Still requires streaming (reduced, but substantial)
- Two inference pipelines to maintain
- Latency still high
- Doesn't solve offline operation

**Decision**: Rejected as overly complex without solving core issues.

## Consequences

### Positive

- ✅ System works reliably on cellular/poor networks
- ✅ Offline operation with durable buffering
- ✅ Low operating costs (data transfer)
- ✅ Real-time capable
- ✅ Privacy-preserving

### Negative

- ❌ Higher device hardware cost ($500 vs $50)
- ❌ Model deployment more complex
- ❌ Debugging requires device access or logs
- ❌ Performance varies by device capability

### Neutral

- Edge devices require more setup and configuration
- Need monitoring infrastructure for fleet health
- Model updates require deployment tooling (planned Phase 8)

## Implementation Notes

### Device Requirements

**Primary Target:** NVIDIA Jetson Orin Nano
- 6-core ARM CPU
- NVIDIA Ampere GPU (1024 CUDA cores)
- 8GB unified RAM
- TensorRT acceleration
- **Performance**: 15 FPS @ 640x640 input

**Fallback:** Raspberry Pi 5
- Quad-core ARM Cortex-A76
- 8GB RAM
- ONNX Runtime CPU
- **Performance**: 3-5 FPS @ 640x640 input
- Suitable for lower-traffic roads

### Backend Selection

Detector auto-selects best available:
1. TensorRT (Jetson only, fastest)
2. ONNX Runtime + CUDA (any NVIDIA GPU)
3. ONNX Runtime CPU (universal fallback)

Logged on startup, operator can verify correct backend in use.

### Durable Buffering

All confirmed detections written to SQLite WAL before upload attempt:
- Survives process crashes
- Survives power loss
- Automatic retry with exponential backoff
- Max 10 retries before marking failed (manual review)

## Related Decisions

- ADR 002: PostgreSQL + PostGIS for geospatial backend
- ADR 004: YOLOv8n model architecture
- Future: ADR on centralized model registry

## References

- [ARCHITECTURE.md](../ARCHITECTURE.md) - System design overview
- [edge/README.md](../../edge/README.md) - Edge deployment guide
- Bandwidth calculations: [analysis/bandwidth-comparison.xlsx](#)

---

**Status:** ✅ Implemented in Phases 1-5  
**Reviewed by:** Architecture Team, Product, Engineering  
**Last Updated:** 2026-09-21

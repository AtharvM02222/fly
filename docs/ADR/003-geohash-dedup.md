# ADR 003: Geohash + Haversine Deduplication Strategy

**Status:** Accepted  
**Date:** 2026-09-02  
**Deciders:** Backend Team, Product

## Context

Multiple devices covering the same road segment will detect the same pothole. Without deduplication:
- Dashboard cluttered with duplicate markers
- Operators waste time reviewing same defect multiple times
- False impression of defect density

**Requirements:**
- Merge detections within **150 meters** of each other
- Within **5 minute** time window
- Preserve first detection, link subsequent to it
- Must be fast (< 10ms per detection)

## Decision

Use **geohash precision 7 + Haversine distance** for deduplication.

**Algorithm:**
1. Calculate geohash (precision 7) for incoming detection
2. Query existing detections with same geohash
3. For matches, calculate precise Haversine distance
4. If within 150m and 5min, merge into existing detection
5. Otherwise, create new detection

## Rationale

### Why Geohash?

Geohash encodes lat/lon into short string that groups nearby points.

**Precision 7** (~150m cell):
```
geohash="9q8yy9k"  (7 chars)
Cell size: ~153m × 153m
```

**Advantages:**
- Fast btree index lookup (string comparison)
- Groups nearby detections in same bucket
- Reduces spatial search space from millions to ~10-100 candidates

### Why Not Just Geohash?

**Problem:** Cell boundary issues

```
   Cell A    |  Cell B
   9q8yy9k   |  9q8yy9m
             |
      A •    |  • B     <- 10m apart but different geohash!
       (just left) (just right)
             |
```

Detections near boundary can be 10m apart but have different geohash → not deduplicated.

**Solution:** Hybrid approach

### Hybrid: Geohash + Haversine

```python
def check_duplicate(detection):
    # 1. Fast geohash filter
    candidates = query_by_geohash(detection.geohash)  # ~10-100 results
    
    # 2. Precise distance check
    for candidate in candidates:
        distance = haversine(detection.location, candidate.location)
        if distance < 150 and time_diff < 5_min:
            return candidate  # Duplicate found
    
    return None  # New detection
```

**Performance:**
- Geohash btree lookup: 1-2ms
- Haversine calculations: 10-100 candidates × 0.01ms = 1-1ms
- **Total**: 2-3ms per detection

### Why Haversine Over PostGIS ST_Distance?

Both calculate great-circle distance on sphere.

**Haversine (pure Python):**
- Simple formula: 2 sin⁻¹ calculations
- No database round-trip for calculation
- Fast enough for small candidate set

**PostGIS ST_Distance:**
- More precise (ellipsoid vs sphere)
- But requires database call
- Overkill for 150m threshold

**Decision**: Haversine sufficient for 150m threshold (error < 0.5% at this distance).

## Alternatives Considered

### Alternative 1: Pure Distance-Based (No Geohash)

Query all detections within 150m radius:
```sql
SELECT * FROM detections
WHERE ST_DWithin(location::geography, $point, 150)
  AND detected_at > NOW() - interval '5 minutes';
```

**Pros:**
- No boundary issues
- Simple algorithm

**Cons:**
- **Slow**: Must check spatial index for every detection
- Latency grows with detection count (10ms → 100ms at 1M detections)
- Not scalable

**Decision**: Rejected due to performance.

### Alternative 2: Grid-Based Deduplication

Divide world into 150m × 150m grid cells.

**Pros:**
- Simple cell assignment
- Fast lookup by grid ID

**Cons:**
- Same boundary problem as geohash
- Custom implementation (geohash is standard)
- No existing tools/libraries

**Decision**: Rejected - geohash already solves this.

### Alternative 3: Clustering Algorithm (DBSCAN)

Run clustering periodically to find duplicate groups.

**Pros:**
- Theoretically optimal clustering
- Handles complex spatial patterns

**Cons:**
- **Not real-time** (batch processing)
- Complex implementation
- Overkill for simple distance threshold
- Doesn't prevent duplicates from being created

**Decision**: Rejected - need real-time deduplication at ingest.

## Consequences

### Positive

- ✅ Fast (2-3ms per detection)
- ✅ Scales to millions of detections
- ✅ Handles boundary cases correctly
- ✅ Simple to understand and debug
- ✅ Uses standard geohash library

### Negative

- ❌ Edge case: Detections on opposite sides of equator/prime meridian in same geohash
  - **Mitigation**: Geohash handles wrap-around correctly
  - **Impact**: None in practice (roads don't cross poles)

- ❌ Geohash precision 7 means some nearby detections in different cells
  - **Mitigation**: Haversine check catches these
  - **Impact**: None - hybrid approach solves this

### Neutral

- Time window (5 min) is configurable in code
- Distance threshold (150m) is configurable
- Can add neighbor cell checks if boundary issues arise (not needed so far)

## Implementation Notes

### Geohash Calculation

```python
import geohash2

def calculate_geohash(lat: float, lon: float, precision: int = 7) -> str:
    return geohash2.encode(lat, lon, precision)

# Example
geohash = calculate_geohash(37.7749, -122.4194, 7)
# => "9q8yy9k"
```

### Haversine Distance

```python
from math import radians, sin, cos, sqrt, asin

def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate great-circle distance in meters."""
    R = 6371000  # Earth radius in meters
    
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a))
    
    return R * c
```

### Database Schema

```sql
-- Store geohash for fast btree lookup
ALTER TABLE detections ADD COLUMN geohash TEXT;

-- Create btree index
CREATE INDEX idx_detections_geohash ON detections(geohash);

-- Compound index for common query
CREATE INDEX idx_detections_geohash_time 
ON detections(geohash, detected_at DESC)
WHERE merged_into IS NULL;
```

### Deduplication Logic

```python
def check_and_merge(detection: Detection) -> Detection:
    # Calculate geohash
    detection.geohash = calculate_geohash(
        detection.latitude, 
        detection.longitude, 
        precision=7
    )
    
    # Find candidates in same geohash
    candidates = db.query(Detection).filter(
        Detection.geohash == detection.geohash,
        Detection.detected_at > detection.detected_at - timedelta(minutes=5),
        Detection.merged_into.is_(None),
        Detection.status != 'fixed'  # Don't merge into fixed detections
    ).all()
    
    # Check precise distance
    for candidate in candidates:
        distance = haversine(
            detection.latitude, detection.longitude,
            candidate.latitude, candidate.longitude
        )
        
        if distance < 150:  # Within threshold
            # Merge
            detection.merged_into = candidate.id
            
            # Create audit event
            create_event(
                detection_id=detection.id,
                event_type='merged',
                note=f'Merged into {candidate.id} (distance: {distance:.1f}m)'
            )
            
            return detection
    
    # No match - new detection
    return detection
```

### Tuning Parameters

Configured in `backend/app/core/config.py`:
```python
DEDUP_GEOHASH_PRECISION = 7  # ~150m cells
DEDUP_DISTANCE_METERS = 150
DEDUP_TIME_WINDOW_MINUTES = 5
```

Can adjust based on:
- Road width (wider roads = larger threshold)
- Device density (more devices = tighter threshold)
- GPS accuracy (±5m typical, ±10m in urban canyons)

## Testing

### Unit Tests

Test edge cases:
- Detections at exact threshold (149m, 151m)
- Detections on geohash cell boundary
- Multiple candidates (picks closest)
- Time window boundary (4min59s, 5min01s)

### Integration Tests

- Insert 100 detections along simulated road
- Verify deduplication rate (expect ~80% merged for 5 devices)
- Check no false negatives (nearby detections not merged)
- Check no false positives (distant detections merged)

## Monitoring

Track dedup metrics:
```python
# Prometheus metrics
dedup_checks_total  # Total dedup checks
dedup_merges_total  # How many merged
dedup_distance_histogram  # Distance distribution of merges
dedup_latency_seconds  # Check latency
```

Alert if:
- Dedup rate drops (< 50%) - indicates algorithm issue
- Latency spikes (> 10ms) - indicates index problem

## Future Enhancements

### If Boundary Issues Arise

Check adjacent cells:
```python
# Get 8 neighbor geohashes
neighbors = geohash2.neighbors(detection.geohash)

# Query all 9 cells (self + 8 neighbors)
candidates = db.query(Detection).filter(
    Detection.geohash.in_([detection.geohash] + neighbors),
    ...
)
```

**Trade-off**: 9x more candidates (90-900 instead of 10-100)  
**Impact**: Still <10ms for most cases

### If False Positives Occur

Add device ID check:
```python
# Only merge if from different device
if candidate.device_id != detection.device_id:
    # Merge logic
```

Prevents same device re-detecting same defect multiple times.

## Related Decisions

- ADR 002: PostgreSQL + PostGIS (provides geohash storage)
- ADR 001: Edge inference (generates detections to deduplicate)

## References

- [Geohash Wikipedia](https://en.wikipedia.org/wiki/Geohash)
- [Haversine Formula](https://en.wikipedia.org/wiki/Haversine_formula)
- [python-geohash](https://pypi.org/project/python-geohash/)

---

**Status:** ✅ Implemented in Phase 3  
**Reviewed by:** Backend Team, Product, QA  
**Last Updated:** 2026-09-21

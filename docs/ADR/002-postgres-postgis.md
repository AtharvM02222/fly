# ADR 002: PostgreSQL + PostGIS for Geospatial Storage

**Status:** Accepted  
**Date:** 2026-09-01  
**Deciders:** Architecture Team, Backend Team

## Context

Drone-CDS requires storing and querying road defect detections with geospatial coordinates. Key requirements:

1. Store detection locations (latitude/longitude)
2. Query detections within bounding box (map view)
3. Find nearby detections for deduplication (within 150m)
4. ACID guarantees for detection integrity
5. Support for spatial indexing (performance)

## Decision

We will use **PostgreSQL with PostGIS extension** as the primary database.

## Rationale

### Why PostgreSQL

1. **ACID Guarantees**
   - Strong consistency for detection records
   - Transaction support for deduplication
   - No "eventual consistency" issues

2. **Mature Ecosystem**
   - Well-understood operations
   - Excellent tooling (pg_admin, monitoring)
   - Large community, extensive documentation

3. **Performance**
   - Handles 10K+ writes/sec with proper indexing
   - Efficient connection pooling
   - Query optimization tools (EXPLAIN, pg_stat_statements)

### Why PostGIS

1. **Native Geography Types**
   ```sql
   location GEOGRAPHY(POINT, 4326)
   ```
   - True spherical distance calculations
   - No need for manual Haversine formulas
   - WGS84 (GPS) coordinate system built-in

2. **Spatial Indexing**
   - GIST indexes for fast bbox queries
   - `ST_DWithin()` for radius search (deduplication)
   - Sub-millisecond queries on millions of points

3. **Industry Standard**
   - Used by major GIS applications
   - Compatible with mapping tools (QGIS, ArcGIS)
   - Well-tested for production use

### Performance Characteristics

**Bbox Query** (map view):
```sql
SELECT * FROM detections
WHERE ST_DWithin(
  location::geography,
  ST_MakePoint(-122.4194, 37.7749)::geography,
  1000  -- 1km radius
)
LIMIT 1000;
```
- **Latency**: 5-20ms with GIST index
- **Scales to**: 10M+ detections

**Deduplication Query**:
```sql
SELECT id FROM detections
WHERE geohash = 'abc123'  -- btree index (fast)
  AND ST_DWithin(location::geography, point, 150)  -- GIST (fast)
  AND detected_at > NOW() - interval '5 minutes'  -- btree (fast)
  AND merged_into IS NULL
LIMIT 1;
```
- **Latency**: <10ms
- **Index strategy**: geohash (btree) narrows to ~100 candidates, then spatial filter

## Alternatives Considered

### Alternative 1: MongoDB with Geospatial Indexes

**Pros:**
- Native GeoJSON support
- 2dsphere indexes for spatial queries
- Flexible schema (no migrations)

**Cons:**
- **No ACID transactions** (critical for deduplication)
- Less mature geospatial features vs PostGIS
- Weaker consistency guarantees
- Team less familiar

**Decision**: Rejected due to transaction/consistency requirements.

### Alternative 2: TimescaleDB (Postgres extension)

**Pros:**
- Time-series optimized (natural fit for detections over time)
- Automatic partitioning by time
- Compression for old data
- Still Postgres (compatibility)

**Cons:**
- **Less mature** than vanilla Postgres
- Additional complexity (hypertables)
- Geospatial support less tested than PostGIS alone
- Overkill for current scale (< 1M detections/month)

**Decision**: Deferred - revisit if time-series queries become bottleneck.

### Alternative 3: Separate Spatial Index (Elasticsearch)

Use Postgres for data, Elasticsearch for spatial search.

**Pros:**
- Elasticsearch excellent for geospatial search
- Can handle massive scale
- Full-text search bonus

**Cons:**
- **Complexity**: Two databases to manage
- **Consistency**: Sync issues between Postgres → ES
- **Overkill**: Current scale doesn't require it
- **Cost**: Additional infrastructure

**Decision**: Rejected - premature optimization.

## Consequences

### Positive

- ✅ True geospatial calculations (spherical geometry)
- ✅ Fast spatial queries with GIST indexes
- ✅ ACID guarantees prevent duplicate detections
- ✅ Standard SQL tooling and expertise
- ✅ Battle-tested at scale

### Negative

- ❌ Postgres requires more tuning than simpler databases
- ❌ Vertical scaling only (replication for reads, but single write master)
- ❌ PostGIS adds ~100MB to image size

### Neutral

- Alembic migrations handle schema evolution cleanly
- Backup/restore well-understood
- Monitoring tooling mature (pg_stat_statements, pg_hero)

## Implementation Notes

### Schema Design

**Core Detection Table:**
```sql
CREATE TABLE detections (
  id UUID PRIMARY KEY,
  location GEOGRAPHY(POINT, 4326),  -- PostGIS type
  geohash TEXT,  -- For fast filtering before spatial calc
  -- ... other fields
);

-- Spatial index
CREATE INDEX idx_detections_location 
ON detections USING GIST (location);

-- Geohash index (fast pre-filter)
CREATE INDEX idx_detections_geohash 
ON detections(geohash);
```

### Geohash Strategy

Hybrid approach for deduplication:
1. **Geohash precision 7** (~150m cells) for coarse bucketing
2. **ST_DWithin()** for precise distance within bucket

Why hybrid?
- Pure geohash: Misses detections near cell boundaries
- Pure distance: Too slow (must check all detections)
- Hybrid: Fast btree lookup + precise spatial calc

### Connection Pooling

```python
# SQLAlchemy pool settings
DATABASE_POOL_SIZE = 20
DATABASE_MAX_OVERFLOW = 10
DATABASE_POOL_TIMEOUT = 30
```

For 3 backend replicas:
- 20 connections/replica = 60 total
- Postgres default max_connections = 100
- Leaves headroom for admin, monitoring

### Backup Strategy

- **Daily full backups** via pg_dump
- **WAL archiving** for point-in-time recovery
- **Retention**: 30 days full, 7 days WAL
- **Testing**: Monthly restore drill

## Performance Tuning

### Postgres Configuration

```conf
# postgresql.conf for detection workload
shared_buffers = 4GB           # 25% of RAM
effective_cache_size = 12GB    # 75% of RAM
work_mem = 64MB                # For complex queries
maintenance_work_mem = 1GB     # For index creation
max_connections = 100
random_page_cost = 1.1         # SSD
effective_io_concurrency = 200 # SSD
```

### Index Maintenance

```sql
-- Weekly vacuum to prevent bloat
VACUUM ANALYZE detections;

-- Monthly reindex (if needed)
REINDEX INDEX CONCURRENTLY idx_detections_location;
```

## Migration Path

If PostGIS becomes bottleneck (> 100M detections):

1. **Horizontal sharding** by geographic region
   - US-West shard, US-East shard, etc.
   - Application-level routing

2. **Read replicas** for analytics/dashboard
   - Separate read traffic from write master
   - Postgres streaming replication

3. **TimescaleDB migration**
   - Automatic time-based partitioning
   - Compression for old data

## Related Decisions

- ADR 003: Geohash-based deduplication
- ADR 001: Edge inference (generates detections)
- Future: ADR on sharding strategy (if needed)

## References

- [PostGIS Documentation](https://postgis.net/docs/)
- [Postgres Performance Tuning](https://wiki.postgresql.org/wiki/Performance_Optimization)
- [Geohash Documentation](http://geohash.org/)

---

**Status:** ✅ Implemented in Phase 2  
**Reviewed by:** Backend Team, DBA, Architecture  
**Last Updated:** 2026-09-21

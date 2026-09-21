# Drone-CDS Operations Runbook

**Version:** 1.0  
**Last Updated:** September 21, 2026

## Table of Contents

- [System Overview](#system-overview)
- [Common Operations](#common-operations)
- [Troubleshooting](#troubleshooting)
- [Emergency Procedures](#emergency-procedures)
- [Maintenance](#maintenance)
- [Monitoring](#monitoring)

## System Overview

Drone-CDS consists of three main components:

1. **Edge Pipeline** - Runs on devices (Jetson/Pi), performs detection
2. **Backend API** - FastAPI server with PostgreSQL/PostGIS
3. **Dashboard** - Next.js web interface for monitoring

### Architecture Diagram

```
┌─────────────┐
│ Edge Device │──┐
└─────────────┘  │
                 │ HTTPS
┌─────────────┐  │  ┌──────────────┐      ┌──────────────┐
│ Edge Device │──┼─>│ Backend API  │<────>│  Dashboard   │
└─────────────┘  │  └──────────────┘      └──────────────┘
                 │         │
┌─────────────┐  │         │
│ Edge Device │──┘         ▼
└─────────────┘      ┌──────────────┐
                     │  PostgreSQL  │
                     │  + PostGIS   │
                     └──────────────┘
```

### System Health Checks

```bash
# Backend
curl http://localhost:8000/healthz
curl http://localhost:8000/readyz

# Database
psql -U postgres -d dronecds -c "SELECT COUNT(*) FROM detections;"

# Dashboard
curl http://localhost:3000

# Edge (on device)
systemctl status drone-cds
```

---

## Common Operations

### 1. Device Down Procedure

**Symptoms:**
- Device status shows "offline" in dashboard
- No recent detections from device
- `last_seen_at` > 5 minutes ago

**Diagnosis Steps:**

1. **Check device status in dashboard:**
   ```
   Navigate to Devices page
   Find device → check last_seen_at
   ```

2. **SSH to device:**
   ```bash
   ssh drone@device-ip
   ```

3. **Check edge service:**
   ```bash
   # Check service status
   sudo systemctl status drone-cds
   
   # Check recent logs
   sudo journalctl -u drone-cds -n 100 --no-pager
   
   # Check for errors
   sudo journalctl -u drone-cds -p err -n 50
   ```

4. **Common issues:**

   a) **Network connectivity:**
   ```bash
   # Test backend connectivity
   curl -I https://backend.example.com/healthz
   
   # Test DNS
   nslookup backend.example.com
   
   # Check internet
   ping -c 3 8.8.8.8
   ```

   b) **GPS issues:**
   ```bash
   # Check GPS device
   ls -l /dev/ttyUSB0
   
   # Read GPS data
   cat /dev/ttyUSB0
   # Should see NMEA sentences like $GPGGA,...
   
   # If no data, check permissions
   sudo chmod 666 /dev/ttyUSB0
   ```

   c) **Camera issues:**
   ```bash
   # Test camera
   python3 -c "import cv2; cap = cv2.VideoCapture(0); print('OK' if cap.isOpened() else 'FAIL')"
   
   # Check camera device
   ls -l /dev/video0
   
   # View available cameras
   v4l2-ctl --list-devices
   ```

**Resolution:**

```bash
# Restart edge service
sudo systemctl restart drone-cds

# Check it started successfully
sudo systemctl status drone-cds

# Watch logs
sudo journalctl -u drone-cds -f
```

If restart doesn't help:
```bash
# Reboot device
sudo reboot

# After reboot, verify service is running
ssh drone@device-ip
sudo systemctl status drone-cds
```

---

### 2. Manual Deduplication Re-trigger

**When to use:**
- Deduplication service failed for a batch
- Duplicate detections visible in dashboard
- Need to reprocess historical data

**Procedure:**

1. **Identify date range with issues:**
   ```sql
   -- Connect to database
   psql -U postgres -d dronecds
   
   -- Find duplicates in spatial/temporal proximity
   SELECT 
       d1.id AS detection1,
       d2.id AS detection2,
       ST_Distance(d1.location::geography, d2.location::geography) AS distance_m,
       EXTRACT(EPOCH FROM (d2.detected_at - d1.detected_at)) / 60 AS time_diff_min
   FROM detections d1
   JOIN detections d2 ON d1.id < d2.id
   WHERE d1.detected_at >= '2026-09-20'
     AND d2.detected_at >= '2026-09-20'
     AND ST_DWithin(d1.location::geography, d2.location::geography, 150)
     AND d1.detected_at - d2.detected_at < interval '5 minutes'
     AND d1.merged_into IS NULL
     AND d2.merged_into IS NULL
   ORDER BY distance_m ASC;
   ```

2. **Run dedup script:**
   ```bash
   docker exec -it backend python -m app.scripts.rerun_dedup \
     --start-date 2026-09-20 \
     --end-date 2026-09-21 \
     --dry-run  # Preview only
   
   # If preview looks good, run for real
   docker exec -it backend python -m app.scripts.rerun_dedup \
     --start-date 2026-09-20 \
     --end-date 2026-09-21
   ```

3. **Verify results:**
   ```sql
   -- Check merged detections
   SELECT status, COUNT(*), COUNT(DISTINCT merged_into)
   FROM detections
   WHERE detected_at >= '2026-09-20'
   GROUP BY status;
   ```

---

### 3. API Key Rotation

**When to rotate:**
- Scheduled rotation (every 90 days recommended)
- Suspected key compromise
- Device decommission

**Procedure:**

1. **Generate new key (dashboard):**
   ```
   Login as admin
   Navigate to Devices
   Click device → "Rotate API Key"
   Copy new key (shown only once!)
   ```

2. **Or via CLI:**
   ```bash
   docker exec -it backend python -m app.scripts.rotate_device_key \
     --device-id uuid \
     --reason "Scheduled rotation"
   ```
   Output:
   ```
   New API key: dcs_live_abc123...
   Old key revoked
   ```

3. **Update device configuration:**
   ```bash
   # SSH to device
   ssh drone@device-ip
   
   # Update config
   sudo nano /opt/drone-cds/edge/config/production.yaml
   # Update device.api_key with new key
   
   # Restart service
   sudo systemctl restart drone-cds
   ```

4. **Verify new key works:**
   ```bash
   # Check logs for successful authentication
   sudo journalctl -u drone-cds -n 50 | grep "authentication\|401\|403"
   
   # Should see successful uploads, no 401 errors
   ```

5. **Old key is automatically revoked** - no additional steps needed

---

### 4. Database Backup & Restore

**Automated Backups:**

Backups run nightly at 2 AM UTC via cron:

```bash
# Check backup status
ls -lh /backups/postgres/

# Manual backup
docker exec postgres pg_dump -U postgres dronecds | gzip > backup-$(date +%Y%m%d).sql.gz
```

**Restore Procedure:**

```bash
# Stop backend to prevent writes
docker stop backend

# Restore from backup
gunzip < backup-20260921.sql.gz | docker exec -i postgres psql -U postgres -d dronecds

# Restart backend
docker start backend

# Verify data
docker exec postgres psql -U postgres -d dronecds -c "SELECT COUNT(*) FROM detections;"
```

**Point-in-Time Recovery (if WAL archiving enabled):**

```bash
# Restore to specific timestamp
docker exec postgres pg_restore --time '2026-09-21 10:30:00'
```

---

### 5. Scaling Backend Horizontally

**Add backend replicas:**

1. **Update docker-compose.yml:**
   ```yaml
   backend:
     deploy:
       replicas: 3
   ```

2. **Add load balancer:**
   ```yaml
   nginx:
     image: nginx:alpine
     volumes:
       - ./nginx.conf:/etc/nginx/nginx.conf
     ports:
       - "80:80"
     depends_on:
       - backend
   ```

3. **Configure nginx:**
   ```nginx
   upstream backend {
       least_conn;
       server backend:8000;
       server backend:8001;
       server backend:8002;
   }
   ```

4. **Apply changes:**
   ```bash
   docker-compose up -d --scale backend=3
   ```

---

## Troubleshooting

### Backend Issues

#### High CPU Usage

**Diagnosis:**
```bash
# Check CPU usage
docker stats backend

# Check running queries
docker exec postgres psql -U postgres -d dronecds -c \
  "SELECT pid, query, state, query_start FROM pg_stat_activity WHERE state != 'idle';"
```

**Resolution:**
```bash
# Kill long-running query
docker exec postgres psql -U postgres -d dronecds -c \
  "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE pid = <pid>;"

# Add missing index (if needed)
docker exec postgres psql -U postgres -d dronecds -c \
  "CREATE INDEX CONCURRENTLY idx_detections_device_status ON detections(device_id, status);"
```

#### Database Connection Pool Exhausted

**Symptoms:**
- Backend logs show "connection pool exhausted"
- 503 errors on API

**Resolution:**
```bash
# Increase pool size in backend config
# Edit app/core/config.py:
# DATABASE_POOL_SIZE=20  # was 10

# Restart backend
docker restart backend

# Monitor connections
watch 'docker exec postgres psql -U postgres -c "SELECT count(*) FROM pg_stat_activity;"'
```

#### Slow Detection Queries

**Diagnosis:**
```sql
-- Find slow queries
SELECT query, calls, mean_exec_time, max_exec_time
FROM pg_stat_statements
WHERE query LIKE '%detections%'
ORDER BY mean_exec_time DESC
LIMIT 10;
```

**Resolution:**
```sql
-- Add missing GIST index
CREATE INDEX CONCURRENTLY idx_detections_location_gist 
ON detections USING GIST (location);

-- Add bbox query index
CREATE INDEX CONCURRENTLY idx_detections_geohash 
ON detections(geohash);

-- Vacuum and analyze
VACUUM ANALYZE detections;
```

---

### Edge Device Issues

#### High Inference Latency

**Symptoms:**
- Logs show: "WARNING - Latency budget exceeded! p95=150ms > 100ms"
- Frame processing rate drops

**Diagnosis:**
```bash
# Check GPU usage (Jetson)
tegrastats

# Check temperature
cat /sys/devices/virtual/thermal/thermal_zone*/temp

# Check CPU frequency
cat /sys/devices/system/cpu/cpu*/cpufreq/scaling_cur_freq
```

**Resolution:**
```bash
# Enable max performance mode (Jetson)
sudo nvpmodel -m 0
sudo jetson_clocks

# Reduce input size in config
nano config/production.yaml
# detector.input_size: 416  # was 640

# Restart service
sudo systemctl restart drone-cds
```

#### Buffer Growing (Upload Failures)

**Symptoms:**
- Buffer stats show high pending count
- Logs show repeated upload failures

**Diagnosis:**
```bash
# Check buffer size
sqlite3 /opt/drone-cds/buffer.db "SELECT COUNT(*) FROM detections WHERE status='pending';"

# Check upload errors in logs
sudo journalctl -u drone-cds | grep "upload\|failed\|429\|503"
```

**Resolution:**
```bash
# Check network to backend
curl -I https://backend.example.com/healthz

# Check API key validity
# (401 errors indicate expired/invalid key)

# If backend is down/slow, detections buffer automatically
# Once backend recovers, uploads resume

# Manual buffer flush (if needed)
sudo systemctl restart drone-cds
# Service will attempt upload on startup
```

---

## Emergency Procedures

### 1. Complete System Outage

**Immediate Actions:**

1. **Check infrastructure:**
   ```bash
   # Server accessible?
   ping production-server
   ssh admin@production-server
   
   # Docker running?
   docker ps
   
   # Disk space?
   df -h
   ```

2. **Bring up core services:**
   ```bash
   cd /opt/drone-cds
   docker-compose up -d postgres redis
   
   # Wait for DB to be ready
   docker exec postgres pg_isready
   
   # Start backend
   docker-compose up -d backend
   
   # Start dashboard
   docker-compose up -d dashboard
   ```

3. **Verify recovery:**
   ```bash
   # Check all services
   docker-compose ps
   
   # Test API
   curl http://localhost:8000/healthz
   
   # Check dashboard
   curl http://localhost:3000
   ```

4. **Notify users:**
   - Post status update
   - Email/Slack notification
   - Update status page

---

### 2. Data Loss / Corruption

**If detections are lost:**

1. **Check backup integrity:**
   ```bash
   ls -lh /backups/postgres/backup-*.sql.gz
   
   # Test restore to temporary DB
   createdb test_restore
   gunzip < backup-latest.sql.gz | psql test_restore
   ```

2. **Edge devices buffer durably** - detections survive network outages
   ```bash
   # SSH to all devices
   # Check buffer for unuploaded detections
   sqlite3 /opt/drone-cds/buffer.db \
     "SELECT COUNT(*) FROM detections WHERE status='pending';"
   
   # Restart edge service to retry uploads
   sudo systemctl restart drone-cds
   ```

3. **Restore from backup** (last resort):
   ```bash
   # Follow "Database Backup & Restore" procedure above
   ```

---

## Maintenance

### Weekly Tasks

- [ ] Review detection accuracy (sample recent detections)
- [ ] Check device health (all devices reporting)
- [ ] Monitor disk usage (databases, logs, images)
- [ ] Review error logs for patterns

### Monthly Tasks

- [ ] Update dependencies (security patches)
- [ ] Review and optimize slow queries
- [ ] Clean old detection images (>90 days fixed/verified)
- [ ] Test backup restoration
- [ ] Review user access (remove inactive users)

### Quarterly Tasks

- [ ] Rotate API keys (all devices)
- [ ] Review and update documentation
- [ ] Capacity planning (storage, compute)
- [ ] Disaster recovery drill

---

## Monitoring

### Key Metrics

**Backend:**
- Request latency (p50, p95, p99)
- Error rate (4xx, 5xx)
- Ingest volume (detections/minute)
- Dedup merge rate
- Active device count

**Edge Devices:**
- Inference latency (p95 < 100ms)
- Frame processing rate (>10 FPS)
- Detection rate (per km)
- Buffer size (pending uploads)
- Error rate (< 1%)

**Database:**
- Connection pool usage
- Query latency
- Disk usage
- Index hit rate (> 99%)
- Replication lag (if using replicas)

### Alerting Rules

```yaml
# Example Prometheus alert rules
groups:
  - name: dronecds
    rules:
      - alert: DeviceOffline
        expr: time() - device_last_seen_seconds > 300
        labels:
          severity: warning
        annotations:
          summary: "Device {{ $labels.device_name }} offline for >5min"
      
      - alert: HighErrorRate
        expr: rate(api_errors_total[5m]) > 0.05
        labels:
          severity: critical
        annotations:
          summary: "API error rate >5%"
      
      - alert: DatabaseDiskFull
        expr: disk_usage_percent{mount="/var/lib/postgresql"} > 90
        labels:
          severity: critical
        annotations:
          summary: "Database disk >90% full"
```

---

## Contacts

**On-Call Rotation:**
- Primary: ops-team@example.com
- Secondary: dev-team@example.com
- Escalation: cto@example.com

**Vendor Support:**
- PostgreSQL: support@postgresql.org
- NVIDIA Jetson: developer.nvidia.com/support

**Documentation:**
- Architecture: [docs/ARCHITECTURE.md](ARCHITECTURE.md)
- API: [docs/API.md](API.md)
- ADRs: [docs/ADR/](ADR/)

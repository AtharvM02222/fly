/**
 * Map view - main dashboard page with Leaflet clustering.
 */

'use client';

import { useEffect, useState, useCallback } from 'react';
import dynamic from 'next/dynamic';
import { apiClient, getErrorMessage } from '@/lib/api-client';
import type { Detection, DetectionFilters, DetectionSeverity, DetectionStatus } from '@/lib/types';
import styles from './map.module.css';

// Dynamic import to avoid SSR issues with Leaflet
const Map = dynamic(() => import('@/components/map'), { ssr: false });

export default function MapPage() {
  const [detections, setDetections] = useState<Detection[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filters, setFilters] = useState<DetectionFilters>({
    page_size: 1000, // Load up to 1000 for map view
  });

  const loadDetections = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await apiClient.getDetections(filters);
      setDetections(response.items);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => {
    loadDetections();
  }, [loadDetections]);

  const handleFilterChange = (key: keyof DetectionFilters, value: any) => {
    setFilters((prev) => ({
      ...prev,
      [key]: value || undefined,
    }));
  };

  const handleMapBoundsChange = (bbox: { min_lat: number; min_lon: number; max_lat: number; max_lon: number }) => {
    setFilters((prev) => ({
      ...prev,
      bbox,
    }));
  };

  return (
    <div className={styles.container}>
      <div className={styles.sidebar}>
        <div className={styles.sidebarHeader}>
          <h2>Filters</h2>
          <button
            onClick={() => setFilters({ page_size: 1000 })}
            className={styles.clearButton}
          >
            Clear All
          </button>
        </div>

        <div className={styles.filterGroup}>
          <label>Status</label>
          <select
            value={filters.status || ''}
            onChange={(e) => handleFilterChange('status', e.target.value)}
            className={styles.select}
          >
            <option value="">All</option>
            <option value="new">New</option>
            <option value="confirmed">Confirmed</option>
            <option value="assigned">Assigned</option>
            <option value="fixed">Fixed</option>
            <option value="verified">Verified</option>
          </select>
        </div>

        <div className={styles.filterGroup}>
          <label>Severity</label>
          <select
            value={filters.severity || ''}
            onChange={(e) => handleFilterChange('severity', e.target.value)}
            className={styles.select}
          >
            <option value="">All</option>
            <option value="low">Low</option>
            <option value="medium">Medium</option>
            <option value="high">High</option>
          </select>
        </div>

        <div className={styles.filterGroup}>
          <label>Date Range</label>
          <input
            type="date"
            value={filters.start_date || ''}
            onChange={(e) => handleFilterChange('start_date', e.target.value)}
            className={styles.input}
            placeholder="Start date"
          />
          <input
            type="date"
            value={filters.end_date || ''}
            onChange={(e) => handleFilterChange('end_date', e.target.value)}
            className={styles.input}
            placeholder="End date"
          />
        </div>

        <div className={styles.stats}>
          <h3>Statistics</h3>
          <div className={styles.statItem}>
            <span>Total Detections:</span>
            <strong>{detections.length}</strong>
          </div>
          <div className={styles.statItem}>
            <span>New:</span>
            <strong className={styles.statusNew}>
              {detections.filter((d) => d.status === 'new').length}
            </strong>
          </div>
          <div className={styles.statItem}>
            <span>Confirmed:</span>
            <strong className={styles.statusConfirmed}>
              {detections.filter((d) => d.status === 'confirmed').length}
            </strong>
          </div>
          <div className={styles.statItem}>
            <span>Fixed:</span>
            <strong className={styles.statusFixed}>
              {detections.filter((d) => d.status === 'fixed').length}
            </strong>
          </div>
        </div>
      </div>

      <div className={styles.mapContainer}>
        {error && (
          <div className={styles.error}>
            <strong>Error loading detections:</strong> {error}
            <button onClick={loadDetections} className={styles.retryButton}>
              Retry
            </button>
          </div>
        )}
        
        {loading && (
          <div className={styles.loading}>
            <div className={styles.spinner} />
            <p>Loading detections...</p>
          </div>
        )}

        <Map
          detections={detections}
          onBoundsChange={handleMapBoundsChange}
        />
      </div>
    </div>
  );
}

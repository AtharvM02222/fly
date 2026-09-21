/**
 * Detection detail page - view and update individual detection.
 */

'use client';

import { useEffect, useState } from 'react';
import { useRouter, useParams } from 'next/navigation';
import { apiClient, getErrorMessage } from '@/lib/api-client';
import type { Detection, DetectionEvent, DetectionStatus, User } from '@/lib/types';
import styles from './detection-detail.module.css';

const STATUS_OPTIONS: { value: DetectionStatus; label: string }[] = [
  { value: 'new', label: 'New' },
  { value: 'confirmed', label: 'Confirmed' },
  { value: 'assigned', label: 'Assigned' },
  { value: 'fixed', label: 'Fixed' },
  { value: 'verified', label: 'Verified' },
];

export default function DetectionDetailPage() {
  const params = useParams();
  const router = useRouter();
  const detectionId = params.id as string;

  const [detection, setDetection] = useState<Detection | null>(null);
  const [events, setEvents] = useState<DetectionEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [updating, setUpdating] = useState(false);
  const [user, setUser] = useState<User | null>(null);

  // Status update form
  const [newStatus, setNewStatus] = useState<DetectionStatus>('new');
  const [note, setNote] = useState('');

  useEffect(() => {
    const currentUser = apiClient.getCurrentUser();
    setUser(currentUser);
    loadDetection();
    loadEvents();
  }, [detectionId]);

  const loadDetection = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await apiClient.getDetection(detectionId);
      setDetection(data);
      setNewStatus(data.status);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  const loadEvents = async () => {
    try {
      const data = await apiClient.getDetectionEvents(detectionId);
      setEvents(data);
    } catch (err) {
      console.error('Failed to load events:', err);
    }
  };

  const handleStatusUpdate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!detection) return;

    try {
      setUpdating(true);
      setError(null);
      
      const updated = await apiClient.updateDetection(detectionId, {
        status: newStatus,
        note: note.trim() || undefined,
      });
      
      setDetection(updated);
      setNote('');
      
      // Reload events to show the new status change
      await loadEvents();
      
      // Show success (optional toast notification)
      alert('Status updated successfully');
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setUpdating(false);
    }
  };

  const canUpdateStatus = user?.role === 'admin' || user?.role === 'operator';

  if (loading) {
    return (
      <div className={styles.loading}>
        <div className={styles.spinner} />
        <p>Loading detection...</p>
      </div>
    );
  }

  if (error || !detection) {
    return (
      <div className={styles.error}>
        <h2>Error Loading Detection</h2>
        <p>{error || 'Detection not found'}</p>
        <button onClick={() => router.back()} className={styles.backButton}>
          Go Back
        </button>
      </div>
    );
  }

  const getSeverityColor = (severity: string): string => {
    switch (severity) {
      case 'high': return '#e53e3e';
      case 'medium': return '#ed8936';
      case 'low': return '#ecc94b';
      default: return '#718096';
    }
  };

  const getStatusColor = (status: string): string => {
    switch (status) {
      case 'new': return '#3182ce';
      case 'confirmed': return '#38a169';
      case 'assigned': return '#d69e2e';
      case 'fixed': return '#718096';
      case 'verified': return '#805ad5';
      default: return '#718096';
    }
  };

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <button onClick={() => router.back()} className={styles.backButton}>
          ← Back
        </button>
        <h1>Detection Details</h1>
        <div className={styles.badges}>
          <span
            className={styles.badge}
            style={{ background: getSeverityColor(detection.severity) }}
          >
            {detection.severity.toUpperCase()}
          </span>
          <span
            className={styles.badge}
            style={{ background: getStatusColor(detection.status) }}
          >
            {detection.status.toUpperCase()}
          </span>
        </div>
      </div>

      <div className={styles.grid}>
        {/* Image Section */}
        <div className={styles.imageSection}>
          <div className={styles.card}>
            <h2>Detection Image</h2>
            {detection.image_url ? (
              <div className={styles.imageContainer}>
                <img
                  src={detection.image_url}
                  alt="Detection"
                  className={styles.image}
                />
                {detection.bbox && (
                  <div className={styles.bboxOverlay}>
                    <svg
                      viewBox="0 0 100 100"
                      preserveAspectRatio="none"
                      className={styles.bboxSvg}
                    >
                      <rect
                        x={detection.bbox.x1 * 100}
                        y={detection.bbox.y1 * 100}
                        width={(detection.bbox.x2 - detection.bbox.x1) * 100}
                        height={(detection.bbox.y2 - detection.bbox.y1) * 100}
                        fill="none"
                        stroke={getSeverityColor(detection.severity)}
                        strokeWidth="2"
                      />
                    </svg>
                  </div>
                )}
              </div>
            ) : (
              <div className={styles.noImage}>
                <p>No image available</p>
              </div>
            )}
            
            <div className={styles.metadata}>
              <div className={styles.metaItem}>
                <strong>Confidence:</strong>
                <span>{(detection.confidence * 100).toFixed(1)}%</span>
              </div>
              <div className={styles.metaItem}>
                <strong>Model Version:</strong>
                <span>{detection.model_version}</span>
              </div>
              {detection.is_interpolated && (
                <div className={styles.interpolatedBadge}>
                  ⚠️ GPS Interpolated
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Info Section */}
        <div className={styles.infoSection}>
          <div className={styles.card}>
            <h2>Detection Information</h2>
            
            <div className={styles.infoGrid}>
              <div className={styles.infoItem}>
                <label>ID</label>
                <span className={styles.monospace}>{detection.id}</span>
              </div>
              
              <div className={styles.infoItem}>
                <label>Client ID</label>
                <span className={styles.monospace}>{detection.client_detection_id}</span>
              </div>
              
              <div className={styles.infoItem}>
                <label>Device</label>
                <span>{detection.device?.name || detection.device_id}</span>
              </div>
              
              <div className={styles.infoItem}>
                <label>Detected At</label>
                <span>{new Date(detection.detected_at).toLocaleString()}</span>
              </div>
              
              <div className={styles.infoItem}>
                <label>Created At</label>
                <span>{new Date(detection.created_at).toLocaleString()}</span>
              </div>
              
              <div className={styles.infoItem}>
                <label>Location</label>
                <span>
                  {detection.latitude.toFixed(6)}, {detection.longitude.toFixed(6)}
                </span>
              </div>
              
              <div className={styles.infoItem}>
                <label>Geohash</label>
                <span className={styles.monospace}>{detection.geohash}</span>
              </div>
              
              {detection.merged_into && (
                <div className={styles.infoItem}>
                  <label>Merged Into</label>
                  <span className={styles.monospace}>{detection.merged_into}</span>
                </div>
              )}
            </div>

            <div className={styles.mapLink}>
              <a
                href={`https://www.google.com/maps?q=${detection.latitude},${detection.longitude}`}
                target="_blank"
                rel="noopener noreferrer"
                className={styles.button}
              >
                📍 View on Google Maps
              </a>
            </div>
          </div>

          {/* Status Update Form */}
          {canUpdateStatus && (
            <div className={styles.card}>
              <h2>Update Status</h2>
              <form onSubmit={handleStatusUpdate} className={styles.form}>
                <div className={styles.formGroup}>
                  <label htmlFor="status">New Status</label>
                  <select
                    id="status"
                    value={newStatus}
                    onChange={(e) => setNewStatus(e.target.value as DetectionStatus)}
                    className={styles.select}
                    disabled={updating}
                  >
                    {STATUS_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </div>

                <div className={styles.formGroup}>
                  <label htmlFor="note">Note (optional)</label>
                  <textarea
                    id="note"
                    value={note}
                    onChange={(e) => setNote(e.target.value)}
                    placeholder="Add a note about this status change..."
                    className={styles.textarea}
                    rows={3}
                    disabled={updating}
                  />
                </div>

                <button
                  type="submit"
                  className={styles.submitButton}
                  disabled={updating || newStatus === detection.status}
                >
                  {updating ? 'Updating...' : 'Update Status'}
                </button>
              </form>
            </div>
          )}
        </div>

        {/* Events Timeline */}
        <div className={styles.eventsSection}>
          <div className={styles.card}>
            <h2>Status History</h2>
            {events.length === 0 ? (
              <p className={styles.noEvents}>No status changes yet</p>
            ) : (
              <div className={styles.timeline}>
                {events.map((event) => (
                  <div key={event.id} className={styles.timelineItem}>
                    <div className={styles.timelineDot} />
                    <div className={styles.timelineContent}>
                      <div className={styles.timelineHeader}>
                        <strong>{event.event_type}</strong>
                        <span className={styles.timelineActor}>by {event.actor}</span>
                      </div>
                      {event.note && (
                        <p className={styles.timelineNote}>{event.note}</p>
                      )}
                      <span className={styles.timelineDate}>
                        {new Date(event.created_at).toLocaleString()}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

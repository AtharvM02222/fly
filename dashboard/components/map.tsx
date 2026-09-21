/**
 * Leaflet map component with marker clustering.
 */

'use client';

import { useEffect, useRef } from 'react';
import { useRouter } from 'next/navigation';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import 'leaflet.markercluster/dist/MarkerCluster.css';
import 'leaflet.markercluster/dist/MarkerCluster.Default.css';
import 'leaflet.markercluster';
import type { Detection } from '@/lib/types';
import styles from './map.module.css';

// Fix Leaflet default marker icon paths in Next.js
delete (L.Icon.Default.prototype as any)._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
  iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
  shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
});

interface MapProps {
  detections: Detection[];
  onBoundsChange?: (bbox: { min_lat: number; min_lon: number; max_lat: number; max_lon: number }) => void;
}

// Custom marker colors by severity
const getSeverityColor = (severity: string): string => {
  switch (severity) {
    case 'high':
      return '#e53e3e'; // red
    case 'medium':
      return '#ed8936'; // orange
    case 'low':
      return '#ecc94b'; // yellow
    default:
      return '#718096'; // gray
  }
};

// Custom marker HTML
const createCustomIcon = (detection: Detection): L.DivIcon => {
  const color = getSeverityColor(detection.severity);
  const isNew = detection.status === 'new';
  
  return L.divIcon({
    className: 'custom-marker',
    html: `
      <div style="
        width: 24px;
        height: 24px;
        background: ${color};
        border: 3px solid white;
        border-radius: 50%;
        box-shadow: 0 2px 4px rgba(0,0,0,0.3);
        ${isNew ? 'animation: pulse 2s infinite;' : ''}
      "></div>
    `,
    iconSize: [24, 24],
    iconAnchor: [12, 12],
    popupAnchor: [0, -12],
  });
};

export default function Map({ detections, onBoundsChange }: MapProps) {
  const mapRef = useRef<L.Map | null>(null);
  const markersRef = useRef<L.MarkerClusterGroup | null>(null);
  const router = useRouter();

  // Initialize map
  useEffect(() => {
    if (mapRef.current) return; // Already initialized

    // Default center (San Francisco)
    const map = L.map('map', {
      center: [37.7749, -122.4194],
      zoom: 13,
      zoomControl: true,
    });

    // Add tile layer (OpenStreetMap)
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
      maxZoom: 19,
    }).addTo(map);

    // Initialize marker cluster group
    const markers = L.markerClusterGroup({
      chunkedLoading: true,
      spiderfyOnMaxZoom: true,
      showCoverageOnHover: false,
      zoomToBoundsOnClick: true,
      maxClusterRadius: 50,
      iconCreateFunction: (cluster) => {
        const count = cluster.getChildCount();
        let size = 'small';
        
        if (count >= 100) size = 'large';
        else if (count >= 10) size = 'medium';

        return L.divIcon({
          html: `<div><span>${count}</span></div>`,
          className: `marker-cluster marker-cluster-${size}`,
          iconSize: L.point(40, 40),
        });
      },
    });

    map.addLayer(markers);

    // Listen for bounds changes
    map.on('moveend', () => {
      if (onBoundsChange) {
        const bounds = map.getBounds();
        onBoundsChange({
          min_lat: bounds.getSouth(),
          min_lon: bounds.getWest(),
          max_lat: bounds.getNorth(),
          max_lon: bounds.getEast(),
        });
      }
    });

    mapRef.current = map;
    markersRef.current = markers;

    // Cleanup on unmount
    return () => {
      map.remove();
      mapRef.current = null;
      markersRef.current = null;
    };
  }, [onBoundsChange]);

  // Update markers when detections change
  useEffect(() => {
    if (!markersRef.current) return;

    const markers = markersRef.current;
    markers.clearLayers();

    if (detections.length === 0) return;

    // Add markers
    detections.forEach((detection) => {
      const marker = L.marker([detection.latitude, detection.longitude], {
        icon: createCustomIcon(detection),
      });

      // Popup content
      const popupContent = `
        <div style="min-width: 200px; font-family: system-ui, -apple-system, sans-serif;">
          <div style="margin-bottom: 8px;">
            <strong style="font-size: 14px;">Detection ${detection.id.slice(0, 8)}</strong>
          </div>
          <div style="margin-bottom: 4px; font-size: 13px;">
            <strong>Severity:</strong>
            <span style="
              display: inline-block;
              padding: 2px 8px;
              margin-left: 4px;
              border-radius: 4px;
              font-size: 11px;
              font-weight: 600;
              text-transform: uppercase;
              background: ${getSeverityColor(detection.severity)};
              color: white;
            ">${detection.severity}</span>
          </div>
          <div style="margin-bottom: 4px; font-size: 13px;">
            <strong>Status:</strong> ${detection.status}
          </div>
          <div style="margin-bottom: 4px; font-size: 13px;">
            <strong>Confidence:</strong> ${(detection.confidence * 100).toFixed(1)}%
          </div>
          <div style="margin-bottom: 8px; font-size: 13px; color: #718096;">
            ${new Date(detection.detected_at).toLocaleString()}
          </div>
          <button
            onclick="window.location.href='/detections/${detection.id}'"
            style="
              width: 100%;
              padding: 6px 12px;
              font-size: 13px;
              font-weight: 500;
              color: white;
              background: #3182ce;
              border: none;
              border-radius: 4px;
              cursor: pointer;
            "
          >
            View Details
          </button>
        </div>
      `;

      marker.bindPopup(popupContent, {
        maxWidth: 250,
      });

      // Click handler for marker (alternative to popup button)
      marker.on('click', () => {
        // Popup will open automatically, button handles navigation
      });

      markers.addLayer(marker);
    });

    // Fit bounds to markers if we have detections
    if (detections.length > 0 && mapRef.current) {
      const bounds = markers.getBounds();
      if (bounds.isValid()) {
        mapRef.current.fitBounds(bounds, { padding: [50, 50] });
      }
    }
  }, [detections, router]);

  return (
    <>
      <style jsx global>{`
        @keyframes pulse {
          0%, 100% {
            opacity: 1;
            transform: scale(1);
          }
          50% {
            opacity: 0.7;
            transform: scale(1.1);
          }
        }

        .marker-cluster {
          background: rgba(49, 130, 206, 0.6);
          border-radius: 50%;
          text-align: center;
          font-weight: 700;
          border: 3px solid white;
          box-shadow: 0 2px 6px rgba(0, 0, 0, 0.3);
        }

        .marker-cluster div {
          width: 34px;
          height: 34px;
          margin: 3px;
          background: rgba(49, 130, 206, 0.8);
          border-radius: 50%;
          display: flex;
          align-items: center;
          justify-content: center;
        }

        .marker-cluster span {
          color: white;
          font-size: 13px;
        }

        .marker-cluster-small {
          background: rgba(49, 130, 206, 0.6);
        }

        .marker-cluster-small div {
          background: rgba(49, 130, 206, 0.8);
        }

        .marker-cluster-medium {
          background: rgba(237, 137, 54, 0.6);
        }

        .marker-cluster-medium div {
          background: rgba(237, 137, 54, 0.8);
        }

        .marker-cluster-large {
          background: rgba(229, 62, 62, 0.6);
        }

        .marker-cluster-large div {
          background: rgba(229, 62, 62, 0.8);
        }

        .leaflet-popup-content-wrapper {
          border-radius: 8px;
          box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
        }

        .leaflet-popup-content {
          margin: 12px;
        }
      `}</style>
      <div id="map" className={styles.map} />
    </>
  );
}

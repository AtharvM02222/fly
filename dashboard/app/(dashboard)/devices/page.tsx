'use client';
import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { apiClient } from '@/lib/api-client';
import type { Device } from '@/lib/types';
import { Cpu, AlertCircle, CheckCircle, Clock } from 'lucide-react';
import styles from './devices.module.css';
export default function DevicesPage() {
  const [devices, setDevices] = useState<Device[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();
  useEffect(() => {
    loadDevices();
    const interval = setInterval(loadDevices, 30000);
    return () => clearInterval(interval);
  }, []);
  const loadDevices = async () => {
    try {
      const data = await apiClient.getDevices();
      setDevices(data);
      setError(null);
    } catch (err) {
      setError('Failed to load devices');
      console.error('Failed to load devices:', err);
    } finally {
      setIsLoading(false);
    }
  };
  const getDeviceStatus = (device: Device): 'online' | 'offline' => {
    if (!device.last_seen_at) return 'offline';
    const lastSeen = new Date(device.last_seen_at);
    const now = new Date();
    const diffMinutes = (now.getTime() - lastSeen.getTime()) / 1000 / 60;
    return diffMinutes < 5 ? 'online' : 'offline';
  };
  const formatLastSeen = (lastSeenAt: string | null): string => {
    if (!lastSeenAt) return 'Never';
    const lastSeen = new Date(lastSeenAt);
    const now = new Date();
    const diffSeconds = Math.floor((now.getTime() - lastSeen.getTime()) / 1000);
    if (diffSeconds < 60) return `${diffSeconds}s ago`;
    if (diffSeconds < 3600) return `${Math.floor(diffSeconds / 60)}m ago`;
    if (diffSeconds < 86400) return `${Math.floor(diffSeconds / 3600)}h ago`;
    return `${Math.floor(diffSeconds / 86400)}d ago`;
  };
  if (isLoading) {
    return (
      <div className={styles.container}>
        <div className={styles.loading}>Loading devices...</div>
      </div>
    );
  }
  if (error) {
    return (
      <div className={styles.container}>
        <div className={styles.error}>
          <AlertCircle size={24} />
          <span>{error}</span>
        </div>
      </div>
    );
  }
  const onlineCount = devices.filter(d => getDeviceStatus(d) === 'online').length;
  const totalDetections = devices.reduce((sum, d) => sum + (d.detection_count || 0), 0);
  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h1 className={styles.title}>Device Fleet</h1>
        <button onClick={loadDevices} className={styles.refreshButton}>
          Refresh
        </button>
      </div>
      {}
      <div className={styles.summary}>
        <div className={styles.summaryCard}>
          <div className={styles.summaryIcon}>
            <Cpu size={24} />
          </div>
          <div>
            <div className={styles.summaryLabel}>Total Devices</div>
            <div className={styles.summaryValue}>{devices.length}</div>
          </div>
        </div>
        <div className={styles.summaryCard}>
          <div className={styles.summaryIcon} style={{ background: '#48bb78' }}>
            <CheckCircle size={24} />
          </div>
          <div>
            <div className={styles.summaryLabel}>Online</div>
            <div className={styles.summaryValue}>{onlineCount}</div>
          </div>
        </div>
        <div className={styles.summaryCard}>
          <div className={styles.summaryIcon} style={{ background: '#667eea' }}>
            <AlertCircle size={24} />
          </div>
          <div>
            <div className={styles.summaryLabel}>Total Detections</div>
            <div className={styles.summaryValue}>{totalDetections.toLocaleString()}</div>
          </div>
        </div>
      </div>
      {}
      <div className={styles.deviceList}>
        {devices.length === 0 ? (
          <div className={styles.empty}>
            <Cpu size={48} />
            <p>No devices registered yet</p>
          </div>
        ) : (
          devices.map((device) => {
            const status = getDeviceStatus(device);
            return (
              <div
                key={device.id}
                className={styles.deviceCard}
                onClick={() => router.push(`/devices/${device.id}`)}
              >
                <div className={styles.deviceHeader}>
                  <div className={styles.deviceInfo}>
                    <div className={styles.deviceName}>
                      <Cpu size={20} />
                      <span>{device.name}</span>
                    </div>
                    <div className={styles.deviceType}>
                      {device.device_type.charAt(0).toUpperCase() + device.device_type.slice(1)}
                    </div>
                  </div>
                  <div className={`${styles.statusBadge} ${styles[status]}`}>
                    {status === 'online' ? (
                      <>
                        <CheckCircle size={16} />
                        <span>Online</span>
                      </>
                    ) : (
                      <>
                        <AlertCircle size={16} />
                        <span>Offline</span>
                      </>
                    )}
                  </div>
                </div>
                <div className={styles.deviceStats}>
                  <div className={styles.stat}>
                    <Clock size={16} />
                    <span>Last seen: {formatLastSeen(device.last_seen_at)}</span>
                  </div>
                  <div className={styles.stat}>
                    <AlertCircle size={16} />
                    <span>Detections: {(device.detection_count || 0).toLocaleString()}</span>
                  </div>
                </div>
                <div className={styles.deviceFooter}>
                  <span className={styles.deviceId}>ID: {device.id.slice(0, 8)}</span>
                  <span className={styles.deviceCreated}>
                    Added {new Date(device.created_at).toLocaleDateString()}
                  </span>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}

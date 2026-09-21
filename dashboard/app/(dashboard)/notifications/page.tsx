/**
 * Notifications page - view and manage detection notifications.
 */

'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useNotifications } from '@/lib/use-notifications';
import { Bell, BellOff, Check, AlertCircle } from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';
import styles from './notifications.module.css';

export default function NotificationsPage() {
  const { notifications, unreadCount, isLoading, markAsRead } = useNotifications();
  const [filter, setFilter] = useState<'all' | 'unread'>('all');
  const router = useRouter();

  const filteredNotifications = filter === 'unread' 
    ? notifications.filter(n => n.status === 'unread')
    : notifications;

  const handleNotificationClick = async (notification: typeof notifications[0]) => {
    if (notification.status === 'unread') {
      await markAsRead(notification.id);
    }
    router.push(`/detections/${notification.detection_id}`);
  };

  const getSeverityColor = (severity?: string): string => {
    switch (severity) {
      case 'high': return '#e53e3e';
      case 'medium': return '#ed8936';
      case 'low': return '#ecc94b';
      default: return '#718096';
    }
  };

  if (isLoading) {
    return (
      <div className={styles.container}>
        <div className={styles.loading}>Loading notifications...</div>
      </div>
    );
  }

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <div>
          <h1 className={styles.title}>Notifications</h1>
          {unreadCount > 0 && (
            <p className={styles.subtitle}>
              {unreadCount} unread {unreadCount === 1 ? 'notification' : 'notifications'}
            </p>
          )}
        </div>

        <div className={styles.filters}>
          <button
            className={`${styles.filterButton} ${filter === 'all' ? styles.active : ''}`}
            onClick={() => setFilter('all')}
          >
            All ({notifications.length})
          </button>
          <button
            className={`${styles.filterButton} ${filter === 'unread' ? styles.active : ''}`}
            onClick={() => setFilter('unread')}
          >
            Unread ({unreadCount})
          </button>
        </div>
      </div>

      <div className={styles.content}>
        {filteredNotifications.length === 0 ? (
          <div className={styles.empty}>
            {filter === 'unread' ? (
              <>
                <BellOff size={48} />
                <p>No unread notifications</p>
                <span>You're all caught up!</span>
              </>
            ) : (
              <>
                <Bell size={48} />
                <p>No notifications yet</p>
                <span>New detection notifications will appear here</span>
              </>
            )}
          </div>
        ) : (
          <div className={styles.notificationList}>
            {filteredNotifications.map((notification) => {
              const detection = notification.detection;
              const isUnread = notification.status === 'unread';

              return (
                <div
                  key={notification.id}
                  className={`${styles.notification} ${isUnread ? styles.unread : ''}`}
                  onClick={() => handleNotificationClick(notification)}
                >
                  {isUnread && <div className={styles.unreadIndicator} />}

                  <div className={styles.notificationIcon}>
                    <AlertCircle 
                      size={24} 
                      color={getSeverityColor(detection?.severity)} 
                    />
                  </div>

                  <div className={styles.notificationContent}>
                    <div className={styles.notificationHeader}>
                      <h3 className={styles.notificationTitle}>
                        New {detection?.severity} severity detection
                      </h3>
                      {!isUnread && (
                        <span className={styles.readBadge}>
                          <Check size={14} />
                          Read
                        </span>
                      )}
                    </div>

                    {detection && (
                      <div className={styles.notificationDetails}>
                        <span>
                          <strong>Confidence:</strong> {(detection.confidence * 100).toFixed(1)}%
                        </span>
                        <span>
                          <strong>Status:</strong> {detection.status}
                        </span>
                        {detection.device && (
                          <span>
                            <strong>Device:</strong> {detection.device.name}
                          </span>
                        )}
                      </div>
                    )}

                    <div className={styles.notificationFooter}>
                      <span className={styles.timestamp}>
                        {formatDistanceToNow(new Date(notification.created_at), { addSuffix: true })}
                      </span>
                      <span className={styles.viewLink}>
                        View Details →
                      </span>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

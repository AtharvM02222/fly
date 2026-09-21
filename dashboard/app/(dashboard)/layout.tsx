/**
 * Dashboard layout with sidebar navigation and header.
 */

'use client';

import { useAuth } from '@/lib/auth-context';
import { useNotifications } from '@/lib/use-notifications';
import { ProtectedRoute } from '@/components/protected-route';
import { Bell, Map, ListChecks, Cpu, FileText, LogOut } from 'lucide-react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import styles from './layout.module.css';

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const { user, logout } = useAuth();
  const { unreadCount } = useNotifications();
  const pathname = usePathname();

  const navItems = [
    { href: '/', icon: Map, label: 'Map' },
    { href: '/detections', icon: ListChecks, label: 'Detections' },
    { href: '/devices', icon: Cpu, label: 'Devices' },
    { href: '/reports', icon: FileText, label: 'Reports' },
  ];

  return (
    <ProtectedRoute>
      <div className={styles.layout}>
        {/* Sidebar */}
        <aside className={styles.sidebar}>
          <div className={styles.sidebarHeader}>
            <h1 className={styles.logo}>Drone-CDS</h1>
            <p className={styles.tagline}>Detection & Monitoring</p>
          </div>

          <nav className={styles.nav}>
            {navItems.map((item) => {
              const Icon = item.icon;
              const isActive = pathname === item.href || 
                (item.href !== '/' && pathname?.startsWith(item.href));
              
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`${styles.navItem} ${isActive ? styles.active : ''}`}
                >
                  <Icon size={20} />
                  <span>{item.label}</span>
                </Link>
              );
            })}
          </nav>

          <div className={styles.sidebarFooter}>
            <div className={styles.userInfo}>
              <div className={styles.userName}>{user?.email}</div>
              <div className={styles.userRole}>
                {user?.role.charAt(0).toUpperCase()}{user?.role.slice(1)}
              </div>
            </div>
            <button onClick={logout} className={styles.logoutButton}>
              <LogOut size={16} />
              <span>Logout</span>
            </button>
          </div>
        </aside>

        {/* Main content area */}
        <div className={styles.main}>
          {/* Header */}
          <header className={styles.header}>
            <div className={styles.headerTitle}>
              {/* Empty for now, can add breadcrumbs or page title */}
            </div>
            <div className={styles.headerActions}>
              <Link href="/notifications" className={styles.notificationButton}>
                <Bell size={24} />
                {unreadCount > 0 && (
                  <span className={styles.badge}>{unreadCount}</span>
                )}
              </Link>
            </div>
          </header>

          {/* Page content */}
          <main className={styles.content}>
            {children}
          </main>
        </div>
      </div>
    </ProtectedRoute>
  );
}

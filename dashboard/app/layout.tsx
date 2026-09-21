import type { Metadata } from 'next'
import { AuthProvider } from '@/lib/auth-context'
import './globals.css'
export const metadata: Metadata = {
  title: 'Drone-CDS Dashboard',
  description: 'Road defect detection and alerting system',
}
export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body>
        <AuthProvider>
          {children}
        </AuthProvider>
      </body>
    </html>
  )
}

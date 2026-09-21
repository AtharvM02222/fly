import type { Metadata } from 'next'

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
      <body>{children}</body>
    </html>
  )
}

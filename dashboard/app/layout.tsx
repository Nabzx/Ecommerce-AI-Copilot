import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'TradeFlux AI Dashboard',
  description: 'Real-time cryptocurrency analytics dashboard',
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


import './globals.css';
import type { Metadata, Viewport } from 'next';
import Sidebar from '@/components/Sidebar';
import Providers from '@/components/Providers';
import ServiceWorkerRegister from '@/components/ServiceWorkerRegister';

export const metadata: Metadata = {
  title: 'DIEP Operations Portal',
  description: 'Unified operator interface for the DIEP energy platform',
  // Phase 11C — PWA: installable on a phone ("Add to Home Screen").
  manifest: '/manifest.webmanifest',
  icons: { icon: '/icon-192.png', apple: '/icon-192.png' },
  appleWebApp: { capable: true, statusBarStyle: 'black-translucent', title: 'DIEP' },
};

export const viewport: Viewport = {
  themeColor: '#0b1220',
  width: 'device-width',
  initialScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <Providers>
          <div className="flex min-h-screen">
            <Sidebar />
            <main className="flex-1 p-6 max-w-[1400px]">{children}</main>
          </div>
        </Providers>
        <ServiceWorkerRegister />
      </body>
    </html>
  );
}

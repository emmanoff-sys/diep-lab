'use client';

import { usePathname } from 'next/navigation';
import Sidebar from './Sidebar';

const BARE_PREFIXES = ['/login', '/forgot-password', '/reset-password'];

export default function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const bare = BARE_PREFIXES.some((p) => pathname?.startsWith(p));

  if (bare) {
    return <main className="min-h-screen">{children}</main>;
  }

  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <main className="flex-1 p-6 max-w-[1400px]">{children}</main>
    </div>
  );
}

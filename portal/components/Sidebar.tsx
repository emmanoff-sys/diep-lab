'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { GRAFANA_URL } from '@/lib/grafana';
import { usePolling } from '@/lib/hooks';

// ADMS M6 — one consistent GUI: nav grouped into SCADA / ADMS / Analytics so the
// SCADA, OMS, DMS(via API), DERMS, and analytics surfaces read as one platform.
type NavItem = { href: string; label: string; icon: string; roles?: string[] };
type NavGroup = { section: string; items: NavItem[] };

const NAV: NavGroup[] = [
  {
    section: 'SCADA',
    items: [
      { href: '/', label: 'Dashboard', icon: '◧' },
      { href: '/fleet', label: 'Fleet Management', icon: '⊞' },
      { href: '/twins', label: 'Digital Twins', icon: '◎' },
    ],
  },
  {
    section: 'ADMS',
    items: [
      { href: '/oms', label: 'OMS Dashboard', icon: '◉' },
      { href: '/derms', label: 'DERMS', icon: '⚡' },
      { href: '/forecasting', label: 'Load Forecasting', icon: '∿' },
    ],
  },
  {
    section: 'Analytics & Ops',
    items: [
      { href: '/ai-operations', label: 'AI Operations', icon: '✦' },
      { href: '/alarms', label: 'Alarms', icon: '⚠' },
      { href: '/reports', label: 'Reports', icon: '▤' },
      { href: '/administration', label: 'Administration', icon: '⚙', roles: ['admin', 'engineer'] },
    ],
  },
];

export default function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  // Phase 21 — now that the BFF forwards the caller's own JWT, /auth/whoami
  // reflects the logged-in user, not a shared admin identity.
  const whoami = usePolling<{ principal: string; role: string }>('/auth/whoami', 30000);
  const role = whoami.data?.role;

  const groups = NAV.map((g) => ({
    section: g.section,
    items: g.items.filter((item) => !item.roles || (role && item.roles.includes(role))),
  })).filter((g) => g.items.length > 0);

  async function logout() {
    await fetch('/api/auth/logout', { method: 'POST' });
    router.push('/login');
    router.refresh();
  }

  return (
    <aside className="w-60 shrink-0 h-screen sticky top-0 bg-[#0b0e12] border-r border-[#232a33] flex flex-col">
      <div className="px-5 py-4 border-b border-[#232a33]">
        <div className="text-lg font-semibold">DIEP</div>
        <div className="text-xs text-[#8b95a1]">ADMS Operations Portal</div>
      </div>
      <nav className="flex-1 py-2 overflow-y-auto">
        {groups.map((g) => (
          <div key={g.section} className="mb-1">
            <div className="px-5 pt-3 pb-1 text-[10px] uppercase tracking-wider text-[#5b6470]">
              {g.section}
            </div>
            {g.items.map((item) => {
              const active = item.href === '/' ? pathname === '/' : pathname.startsWith(item.href);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`flex items-center gap-3 px-5 py-2.5 text-sm border-l-2 ${
                    active
                      ? 'border-[#3b82f6] bg-[#161b22] text-white'
                      : 'border-transparent text-[#c2c9d1] hover:bg-[#11161c]'
                  }`}
                >
                  <span className="text-[#8b95a1] w-4 text-center">{item.icon}</span>
                  {item.label}
                </Link>
              );
            })}
          </div>
        ))}
      </nav>
      <a
        href={GRAFANA_URL}
        target="_blank"
        rel="noreferrer"
        className="px-5 py-3 text-sm text-[#5aa9e6] border-t border-[#232a33] hover:bg-[#11161c]"
      >
        ↗ Grafana monitoring
      </a>
      <div className="px-5 py-3 border-t border-[#232a33] flex items-center justify-between">
        <div className="text-xs">
          <div className="text-[#c2c9d1]">{whoami.data?.principal || '—'}</div>
          <div className="text-[#8b95a1]">{role || ''}</div>
        </div>
        <button onClick={logout} className="text-xs text-[#f87171] hover:underline">
          Sign out
        </button>
      </div>
    </aside>
  );
}

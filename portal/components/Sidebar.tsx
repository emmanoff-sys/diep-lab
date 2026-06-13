'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { GRAFANA_URL } from '@/lib/grafana';

const NAV = [
  { href: '/', label: 'Dashboard', icon: '◧' },
  { href: '/fleet', label: 'Fleet Management', icon: '⊞' },
  { href: '/twins', label: 'Digital Twins', icon: '◎' },
  { href: '/derms', label: 'DERMS', icon: '⚡' },
  { href: '/ai-operations', label: 'AI Operations', icon: '✦' },
  { href: '/alarms', label: 'Alarms', icon: '⚠' },
  { href: '/reports', label: 'Reports', icon: '▤' },
  { href: '/administration', label: 'Administration', icon: '⚙' },
];

export default function Sidebar() {
  const pathname = usePathname();
  return (
    <aside className="w-60 shrink-0 h-screen sticky top-0 bg-[#0b0e12] border-r border-[#232a33] flex flex-col">
      <div className="px-5 py-4 border-b border-[#232a33]">
        <div className="text-lg font-semibold">DIEP</div>
        <div className="text-xs text-[#8b95a1]">Operations Portal</div>
      </div>
      <nav className="flex-1 py-2 overflow-y-auto">
        {NAV.map((item) => {
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
      </nav>
      <a
        href={GRAFANA_URL}
        target="_blank"
        rel="noreferrer"
        className="px-5 py-3 text-sm text-[#5aa9e6] border-t border-[#232a33] hover:bg-[#11161c]"
      >
        ↗ Grafana monitoring
      </a>
    </aside>
  );
}

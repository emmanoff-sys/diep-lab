import { HEALTH_COLORS, SEVERITY_COLORS } from '@/lib/headlineMetrics';

type Kind = 'status' | 'health' | 'severity';

export default function StatusBadge({ label, kind = 'status' }: { label?: string; kind?: Kind }) {
  const text = (label || 'UNKNOWN').toUpperCase();
  let color = '#6b7280';
  if (kind === 'health') color = HEALTH_COLORS[text] || '#6b7280';
  else if (kind === 'severity') color = SEVERITY_COLORS[text] || '#6b7280';
  else color = text === 'ONLINE' ? '#1f9d55' : text === 'OFFLINE' ? '#b91c1c' : text === 'ACKED' ? '#1f9d55' : text === 'FAILED' ? '#b91c1c' : '#6b7280';
  return (
    <span
      style={{ background: color }}
      className="inline-block px-2 py-0.5 rounded-full text-white text-[11px] font-semibold tracking-wide"
    >
      {text}
    </span>
  );
}

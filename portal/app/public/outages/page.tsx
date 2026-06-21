// Public-facing Customer Outage Portal — no auth, no PII. Rendered server-side
// and fetched directly from the open FastAPI endpoint (/oms/public/outages),
// bypassing the per-user BFF since there is no session here. Allow-listed in
// middleware.ts so it is not redirected to /login.
import { API_BASE } from '@/lib/serverAuth';

export const dynamic = 'force-dynamic';

interface PublicOutage {
  area: string;
  status: string;
  customers_affected: number;
  detected_at: string;
}

async function getOutages(): Promise<{ outages: PublicOutage[]; active_outages: number; customers_affected: number }> {
  try {
    const res = await fetch(`${API_BASE}/oms/public/outages`, { cache: 'no-store' });
    if (!res.ok) throw new Error(String(res.status));
    return res.json();
  } catch {
    return { outages: [], active_outages: 0, customers_affected: 0 };
  }
}

export default async function PublicOutagesPage() {
  const data = await getOutages();
  return (
    <main style={{ minHeight: '100vh', background: '#0f1419', color: '#e6e6e6', padding: '2rem' }}>
      <div style={{ maxWidth: 720, margin: '0 auto' }}>
        <h1 style={{ fontSize: '1.5rem', fontWeight: 600 }}>DIEP — Outage Status</h1>
        <p style={{ color: '#8b95a1', fontSize: '0.875rem', marginTop: 4 }}>
          Current outages by area. Updated automatically.
        </p>

        <div style={{ display: 'flex', gap: '1rem', margin: '1.5rem 0' }}>
          <div style={{ background: '#161b22', border: '1px solid #232a33', borderRadius: 8, padding: '1rem', flex: 1 }}>
            <div style={{ color: '#8b95a1', fontSize: '0.75rem', textTransform: 'uppercase' }}>Active outages</div>
            <div style={{ fontSize: '1.75rem', fontWeight: 600 }}>{data.active_outages}</div>
          </div>
          <div style={{ background: '#161b22', border: '1px solid #232a33', borderRadius: 8, padding: '1rem', flex: 1 }}>
            <div style={{ color: '#8b95a1', fontSize: '0.75rem', textTransform: 'uppercase' }}>Customers affected</div>
            <div style={{ fontSize: '1.75rem', fontWeight: 600 }}>{data.customers_affected}</div>
          </div>
        </div>

        {data.outages.length === 0 ? (
          <div style={{ background: '#161b22', border: '1px solid #232a33', borderRadius: 8, padding: '1.5rem', textAlign: 'center', color: '#4ade80' }}>
            ✓ No outages currently reported.
          </div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse', background: '#161b22', borderRadius: 8 }}>
            <thead>
              <tr style={{ color: '#8b95a1', fontSize: '0.75rem', textAlign: 'left' }}>
                <th style={{ padding: '0.5rem 0.75rem' }}>Area</th>
                <th style={{ padding: '0.5rem 0.75rem' }}>Status</th>
                <th style={{ padding: '0.5rem 0.75rem' }}>Customers</th>
                <th style={{ padding: '0.5rem 0.75rem' }}>Reported</th>
              </tr>
            </thead>
            <tbody>
              {data.outages.map((o, i) => (
                <tr key={i} style={{ borderTop: '1px solid #232a33', fontSize: '0.875rem' }}>
                  <td style={{ padding: '0.5rem 0.75rem' }}>{o.area}</td>
                  <td style={{ padding: '0.5rem 0.75rem' }}>{o.status}</td>
                  <td style={{ padding: '0.5rem 0.75rem' }}>{o.customers_affected}</td>
                  <td style={{ padding: '0.5rem 0.75rem', color: '#8b95a1' }}>
                    {new Date(o.detected_at).toLocaleString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <p style={{ color: '#8b95a1', fontSize: '0.75rem', marginTop: '1.5rem' }}>
          For emergencies call your utility hotline. This page shows distribution-level outage status only.
        </p>
      </div>
    </main>
  );
}

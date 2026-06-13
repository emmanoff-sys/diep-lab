// Grafana stays the monitoring tool; the portal links out to it (does not
// reimplement Prometheus dashboards). Browser-reachable host URL.
export const GRAFANA_URL = process.env.NEXT_PUBLIC_GRAFANA_URL || 'http://localhost:3001';

// Other platform consoles surfaced on the Administration page.
export const CONSOLES: { name: string; url: string; note: string }[] = [
  { name: 'Grafana', url: GRAFANA_URL, note: 'Monitoring dashboards' },
  { name: 'Kafka UI', url: 'http://localhost:8081', note: 'Command topic' },
  { name: 'Node-RED', url: 'http://localhost:1880', note: 'Flow engine' },
  { name: 'MinIO', url: 'http://localhost:9002', note: 'Object storage' },
  { name: 'Prometheus', url: 'http://localhost:9090', note: 'Metrics store' },
];

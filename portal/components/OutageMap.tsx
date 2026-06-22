'use client';

import 'leaflet/dist/leaflet.css';
import { MapContainer, TileLayer, Marker, Polyline, Popup, Tooltip } from 'react-leaflet';
import L from 'leaflet';

export interface OutageMarker {
  case_id: string;
  affected_node_id: string | null;
  node_name?: string | null;
  latitude: number | null;
  longitude: number | null;
  status: string;
  customers_affected: number;
}

// --- read-only grid overlay (ADMS step 1) -----------------------------------
// Rendered from GET /topology/graph only; no control/execution paths here.
export interface GridNode {
  node_id: string;
  node_type: string;
  name: string | null;
  latitude: number | null;
  longitude: number | null;
  nominal_kv: number | null;
  device_id: string | null;
}
export interface GridEdge {
  edge_id: string;
  from_node: string;
  to_node: string;
  edge_type: string; // line | switch | transformer | tie
  is_switchable: boolean;
  normally_closed: boolean;
  is_closed: boolean;
  // device-backed switches carry the bound field device in attrs (P3: DNP3 RTU).
  attrs?: { device_id?: string; protocol?: string; role?: string } | null;
}
export interface GridGraph {
  nodes: GridNode[];
  edges: GridEdge[];
}

const COLORS = {
  energized: '#3b82f6',
  deEnergized: '#6b7280',
  switchClosed: '#22c55e',
  switchOpen: '#ef4444',
  tie: '#f59e0b',
  outage: '#ef4444',
};

// Energization = reachable from a substation source traversing only CLOSED edges.
// Closed conductors energize both ends, so we treat the closed-edge graph as
// undirected here. Mirrors the server-side _reach used by DMS, but computed
// client-side so the overlay needs nothing beyond /topology/graph.
function computeEnergized(nodes: GridNode[], edges: GridEdge[]): Set<string> {
  const adj = new Map<string, string[]>();
  const link = (a: string, b: string) => {
    if (!adj.has(a)) adj.set(a, []);
    adj.get(a)!.push(b);
  };
  for (const e of edges) {
    if (!e.is_closed) continue;
    link(e.from_node, e.to_node);
    link(e.to_node, e.from_node);
  }
  const seen = new Set<string>(nodes.filter((n) => n.node_type === 'substation').map((n) => n.node_id));
  const stack = [...seen];
  while (stack.length) {
    const cur = stack.pop()!;
    for (const nxt of adj.get(cur) ?? []) {
      if (!seen.has(nxt)) {
        seen.add(nxt);
        stack.push(nxt);
      }
    }
  }
  return seen;
}

function nodeIcon(energized: boolean): L.DivIcon {
  const color = energized ? COLORS.energized : COLORS.deEnergized;
  return L.divIcon({
    className: '',
    html: `<div style="width:11px;height:11px;border-radius:50%;background:${color};border:1.5px solid #0b0e12;box-shadow:0 0 3px ${color}"></div>`,
    iconSize: [11, 11],
    iconAnchor: [5.5, 5.5],
  });
}

// Switch = square (green closed / red hollow open); tie = amber diamond. Shape
// distinguishes a tie even when both are "open", per the legend.
function switchIcon(edge: GridEdge): L.DivIcon {
  const tie = edge.edge_type === 'tie';
  const color = tie ? COLORS.tie : edge.is_closed ? COLORS.switchClosed : COLORS.switchOpen;
  const fill = edge.is_closed ? color : 'transparent';
  const rot = tie ? 'transform:rotate(45deg);' : '';
  return L.divIcon({
    className: '',
    html: `<div style="width:12px;height:12px;background:${fill};border:2px solid ${color};${rot}box-shadow:0 0 0 1px #0b0e12"></div>`,
    iconSize: [12, 12],
    iconAnchor: [6, 6],
  });
}

const outageIcon = L.divIcon({
  className: '',
  html: `<div style="width:16px;height:16px;border-radius:50%;background:${COLORS.outage};border:2px solid #fff;box-shadow:0 0 0 2px ${COLORS.outage}"></div>`,
  iconSize: [16, 16],
  iconAnchor: [8, 8],
  popupAnchor: [0, -10],
});

function edgeStyle(edge: GridEdge, live: boolean) {
  if (edge.edge_type === 'tie') {
    return { color: COLORS.tie, weight: edge.is_closed ? 3 : 2, opacity: 0.9, dashArray: edge.is_closed ? undefined : '3 7' };
  }
  if (edge.edge_type === 'switch') {
    return {
      color: edge.is_closed ? COLORS.switchClosed : COLORS.switchOpen,
      weight: edge.is_closed ? 3 : 2,
      opacity: 0.95,
      dashArray: edge.is_closed ? undefined : '6 6',
    };
  }
  // line / transformer: blue when carrying, grey dashed when de-energized.
  return live
    ? { color: COLORS.energized, weight: 3, opacity: 0.85, dashArray: undefined }
    : { color: COLORS.deEnergized, weight: 2, opacity: 0.7, dashArray: '4 6' };
}

function midpoint(a: GridNode, b: GridNode): [number, number] {
  return [((a.latitude as number) + (b.latitude as number)) / 2, ((a.longitude as number) + (b.longitude as number)) / 2];
}

function LegendRow({ swatch, label }: { swatch: string; label: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, lineHeight: '16px' }}>
      <span style={{ width: 14, display: 'inline-flex', justifyContent: 'center' }} dangerouslySetInnerHTML={{ __html: swatch }} />
      <span>{label}</span>
    </div>
  );
}

export default function OutageMap({
  outages,
  grid = null,
  showGrid = false,
  height = 360,
}: {
  outages: OutageMarker[];
  grid?: GridGraph | null;
  showGrid?: boolean;
  height?: number;
}) {
  const withCoords = (outages || []).filter((o) => o.latitude != null && o.longitude != null);

  const gridOn = showGrid && grid != null;
  const nodes = gridOn ? grid!.nodes.filter((n) => n.latitude != null && n.longitude != null) : [];
  const byId = new Map(nodes.map((n) => [n.node_id, n]));
  const energized = gridOn ? computeEnergized(grid!.nodes, grid!.edges) : new Set<string>();

  // Center: outage first, else grid centroid, else default Abuja.
  let center: [number, number] = [9.0765, 7.3986];
  let zoom = 12;
  if (withCoords.length) {
    center = [withCoords[0].latitude as number, withCoords[0].longitude as number];
    zoom = gridOn ? 15 : 13;
  } else if (nodes.length) {
    center = [
      nodes.reduce((s, n) => s + (n.latitude as number), 0) / nodes.length,
      nodes.reduce((s, n) => s + (n.longitude as number), 0) / nodes.length,
    ];
    zoom = 15;
  }

  return (
    <div style={{ position: 'relative' }}>
      <MapContainer center={center} zoom={zoom} style={{ height, width: '100%', borderRadius: 8 }} scrollWheelZoom={false}>
        <TileLayer
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          attribution="&copy; OpenStreetMap contributors"
        />

        {/* Grid layer (read-only) — drawn beneath outage markers. */}
        {gridOn &&
          grid!.edges.map((e) => {
            const a = byId.get(e.from_node);
            const b = byId.get(e.to_node);
            if (!a || !b) return null; // endpoint without coords — skip
            const live = e.is_closed && energized.has(e.from_node) && energized.has(e.to_node);
            const isSwitch = e.edge_type === 'switch' || e.edge_type === 'tie';
            return (
              <Polyline
                key={e.edge_id}
                positions={[
                  [a.latitude as number, a.longitude as number],
                  [b.latitude as number, b.longitude as number],
                ]}
                pathOptions={edgeStyle(e, live)}
              >
                <Tooltip sticky>
                  <b>{e.edge_id}</b>
                  <br />
                  {e.edge_type}
                  {isSwitch && (
                    <>
                      {' · '}
                      {e.is_closed ? 'CLOSED' : 'OPEN'}
                      {e.edge_type === 'tie' ? ' (tie, normally open)' : ''}
                    </>
                  )}
                </Tooltip>
              </Polyline>
            );
          })}

        {gridOn &&
          nodes.map((n) => (
            <Marker key={n.node_id} position={[n.latitude as number, n.longitude as number]} icon={nodeIcon(energized.has(n.node_id))}>
              <Tooltip>
                <b>{n.name || n.node_id}</b>
                <br />
                {n.node_id} · {n.node_type}
                {n.nominal_kv != null && <> · {n.nominal_kv} kV</>}
                <br />
                {energized.has(n.node_id) ? 'Energized' : 'De-energized'}
              </Tooltip>
            </Marker>
          ))}

        {/* Switch / tie state markers at edge midpoints. */}
        {gridOn &&
          grid!.edges
            .filter((e) => e.edge_type === 'switch' || e.edge_type === 'tie')
            .map((e) => {
              const a = byId.get(e.from_node);
              const b = byId.get(e.to_node);
              if (!a || !b) return null;
              return (
                <Marker key={`sw-${e.edge_id}`} position={midpoint(a, b)} icon={switchIcon(e)}>
                  <Tooltip>
                    <b>{e.edge_id}</b>
                    <br />
                    {e.edge_type === 'tie' ? 'Tie switch' : 'Switch'} · {e.is_closed ? 'CLOSED' : 'OPEN'}
                    <br />
                    Normally {e.normally_closed ? 'closed' : 'open'}
                  </Tooltip>
                </Marker>
              );
            })}

        {/* Outage markers always on top. */}
        {withCoords.map((o) => (
          <Marker
            key={o.case_id}
            position={[o.latitude as number, o.longitude as number]}
            icon={outageIcon}
            zIndexOffset={1000}
          >
            <Popup>
              <b>{o.node_name || o.affected_node_id}</b>
              <br />
              {o.status}
              <br />
              {o.customers_affected} customer(s) affected
            </Popup>
          </Marker>
        ))}
      </MapContainer>

      {gridOn && (
        <div
          style={{
            position: 'absolute',
            bottom: 10,
            left: 10,
            zIndex: 1000,
            background: 'rgba(11,14,18,0.88)',
            border: '1px solid #232a33',
            borderRadius: 6,
            padding: '8px 10px',
            fontSize: 11,
            color: '#c2c9d1',
            pointerEvents: 'none',
          }}
        >
          <div style={{ color: '#8b95a1', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.04em', fontSize: 10 }}>
            Grid layer
          </div>
          <LegendRow swatch={`<span style="width:10px;height:10px;border-radius:50%;background:${COLORS.energized};display:inline-block"></span>`} label="Energized" />
          <LegendRow swatch={`<span style="width:10px;height:10px;border-radius:50%;background:${COLORS.deEnergized};display:inline-block"></span>`} label="De-energized" />
          <LegendRow swatch={`<span style="width:10px;height:10px;background:${COLORS.switchClosed};display:inline-block"></span>`} label="Switch closed" />
          <LegendRow swatch={`<span style="width:10px;height:10px;border:2px solid ${COLORS.switchOpen};display:inline-block"></span>`} label="Switch open" />
          <LegendRow swatch={`<span style="width:9px;height:9px;background:${COLORS.tie};display:inline-block;transform:rotate(45deg)"></span>`} label="Tie switch" />
          <LegendRow swatch={`<span style="width:10px;height:10px;border-radius:50%;background:${COLORS.outage};border:1.5px solid #fff;display:inline-block"></span>`} label="Outage" />
        </div>
      )}
    </div>
  );
}

'use client';

import 'leaflet/dist/leaflet.css';
import { MapContainer, TileLayer, Marker, Popup } from 'react-leaflet';
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

// Red divIcon for outages (distinct from the blue site markers on FleetMap).
const outageIcon = L.divIcon({
  className: '',
  html: '<div style="width:16px;height:16px;border-radius:50%;background:#ef4444;border:2px solid #fff;box-shadow:0 0 0 2px #ef4444"></div>',
  iconSize: [16, 16],
  iconAnchor: [8, 8],
  popupAnchor: [0, -10],
});

export default function OutageMap({ outages, height = 360 }: { outages: OutageMarker[]; height?: number }) {
  const withCoords = (outages || []).filter((o) => o.latitude != null && o.longitude != null);
  const center: [number, number] = withCoords.length
    ? [withCoords[0].latitude as number, withCoords[0].longitude as number]
    : [9.0765, 7.3986];

  return (
    <MapContainer center={center} zoom={12} style={{ height, width: '100%', borderRadius: 8 }} scrollWheelZoom={false}>
      <TileLayer
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        attribution="&copy; OpenStreetMap contributors"
      />
      {withCoords.map((o) => (
        <Marker key={o.case_id} position={[o.latitude as number, o.longitude as number]} icon={outageIcon}>
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
  );
}

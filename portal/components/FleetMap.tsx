'use client';

import 'leaflet/dist/leaflet.css';
import { MapContainer, TileLayer, Marker, Popup } from 'react-leaflet';
import L from 'leaflet';
import type { Site } from '@/lib/types';

// Bundlers break Leaflet's default marker asset paths; point them at the CDN
// (the map already needs internet for OSM tiles, so this is consistent).
const icon = new L.Icon({
  iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
  iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
  shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  popupAnchor: [1, -34],
  shadowSize: [41, 41],
});

export default function FleetMap({ sites, height = 420 }: { sites: Site[]; height?: number }) {
  const withCoords = (sites || []).filter((s) => s.latitude != null && s.longitude != null);
  const center: [number, number] = withCoords.length
    ? [withCoords[0].latitude as number, withCoords[0].longitude as number]
    : [9.0765, 7.3986];

  return (
    <MapContainer center={center} zoom={11} style={{ height, width: '100%', borderRadius: 8 }} scrollWheelZoom={false}>
      <TileLayer
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        attribution='&copy; OpenStreetMap contributors'
      />
      {withCoords.map((s) => (
        <Marker key={s.site_name} position={[s.latitude as number, s.longitude as number]} icon={icon}>
          <Popup>
            <b>{s.site_name}</b>
            <br />
            {s.site_type}
            <br />
            {s.online_assets}/{s.asset_count} online
          </Popup>
        </Marker>
      ))}
    </MapContainer>
  );
}

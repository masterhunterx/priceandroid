import React, { useEffect, useState } from 'react';
import { MapContainer, TileLayer, Marker, Popup, Polyline } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

// Fix for default marker icons in React Leaflet
delete (L.Icon.Default.prototype as any)._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon-2x.png',
  iconUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon.png',
  shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-shadow.png',
});

interface RouteMapProps {
  stores: { name: string; lat: number; lng: number }[];
}

const RouteMap: React.FC<RouteMapProps> = ({ stores }) => {
  const [center, setCenter] = useState<[number, number]>([-33.4489, -70.6693]); // Santiago Default
  
  useEffect(() => {
    if (stores.length > 0 && stores[0].lat && stores[0].lng) {
      setCenter([stores[0].lat, stores[0].lng]);
    }
  }, [stores]);

  const validStores = stores.filter(s => s.lat && s.lng);
  const routePositions: [number, number][] = validStores.map(s => [s.lat, s.lng]);

  if (validStores.length === 0) {
    return (
      <div className="w-full h-64 bg-slate-100 dark:bg-slate-800 rounded-2xl flex items-center justify-center border border-slate-200 dark:border-slate-700">
        <p className="text-slate-500 font-bold">Mapa no disponible para estas tiendas.</p>
      </div>
    );
  }

  return (
    <div className="w-full h-64 rounded-2xl overflow-hidden border border-slate-200 dark:border-slate-700 shadow-inner" style={{ zIndex: 0 }}>
      {/* Set z-index to 0 so it doesn't overlap sticky headers */}
      <MapContainer center={center} zoom={13} style={{ height: '100%', width: '100%', zIndex: 0 }}>
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        {validStores.map((store, i) => (
          <Marker key={i} position={[store.lat, store.lng]}>
            <Popup>
              <strong>{store.name}</strong>
              <br /> Parada {i + 1}
            </Popup>
          </Marker>
        ))}
        {routePositions.length > 1 && (
          <Polyline positions={routePositions} color="#10b981" weight={4} dashArray="10, 10" />
        )}
      </MapContainer>
    </div>
  );
};

export default RouteMap;

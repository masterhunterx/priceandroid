import React, { useEffect } from 'react';
import { MapContainer, TileLayer, Marker, Popup, useMap } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

// Fix for default marker icon in Leaflet + React
import markerIcon2x from 'leaflet/dist/images/marker-icon-2x.png';
import markerIcon from 'leaflet/dist/images/marker-icon.png';
import markerShadow from 'leaflet/dist/images/marker-shadow.png';

delete (L.Icon.Default.prototype as any)._getIconUrl;
L.Icon.Default.mergeOptions({
  iconUrl: markerIcon,
  iconRetinaUrl: markerIcon2x,
  shadowUrl: markerShadow,
});

interface BranchMapProps {
  lat: number;
  lng: number;
  name: string;
  address?: string;
}

// Component to handle map centering
function RecenterMap({ lat, lng }: { lat: number; lng: number }) {
  const map = useMap();
  useEffect(() => {
    map.flyTo([lat, lng], 17, {
      duration: 1.5,
      easeLinearity: 0.25
    });
  }, [lat, lng, map]);
  return null;
}

const BranchMap: React.FC<BranchMapProps> = ({ lat, lng, name, address }) => {
  return (
    <div className="w-full h-48 sm:h-64 rounded-2xl overflow-hidden border-2 border-slate-100 dark:border-slate-800 shadow-inner relative z-0">
      <MapContainer 
        center={[lat, lng]} 
        zoom={16} 
        scrollWheelZoom={false}
        className="w-full h-full"
      >
        {/* Satellite View from ESRI */}
        <TileLayer
          attribution='&copy; <a href="https://www.esri.com/">Esri</a> &mdash; Source: Esri, i-cubed, USDA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, UPR-EBP, and the GIS User Community'
          url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
        />
        <Marker position={[lat, lng]}>
          <Popup>
            <div className="p-1">
              <p className="font-bold text-xs m-0">{name}</p>
              {address && <p className="text-[10px] text-slate-500 m-0 mt-1">{address}</p>}
            </div>
          </Popup>
        </Marker>
        <RecenterMap lat={lat} lng={lng} />
      </MapContainer>
      
      {/* Overlay for address info */}
      <div className="absolute bottom-3 left-3 right-3 bg-white/90 dark:bg-slate-900/90 backdrop-blur-md px-3 py-2 rounded-xl shadow-lg border border-white/20 z-[1000]">
        <div className="flex items-center gap-2">
           <span className="material-symbols-outlined text-primary text-[18px]">location_on</span>
           <div className="min-w-0">
             <p className="text-[10px] font-black text-slate-500 uppercase tracking-tighter leading-none">Dirección Exacta</p>
             <p className="text-xs font-bold text-slate-900 dark:text-white truncate mt-1">
               {address || 'Dirección no disponible'}
             </p>
           </div>
        </div>
      </div>
    </div>
  );
};

export default BranchMap;

import React, { createContext, useContext, useState, useEffect, useRef, ReactNode } from 'react';
import { Branch } from '../types';
import { getNearestBranches } from '../lib/api';
import toast from 'react-hot-toast';

interface LocationContextType {
  coords: { lat: number; lng: number } | null;
  selectedBranches: Record<string, Branch>; // slug -> Branch
  loading: boolean;
  error: string | null;
  selectedLocationName: string | null;
  selectedStore: string | null;
  setSelectedStore: (slug: string | null) => void;
  updateLocation: (lat: number, lng: number, name?: string) => Promise<void>;
  clearLocation: () => void;
  selectBranch: (storeSlug: string, branch: Branch) => void;
  requestCurrentLocation: () => void;
  getBranchContext: () => Record<string, string>;
}

const LocationContext = createContext<LocationContextType | undefined>(undefined);

export const useLocation = () => {
  const context = useContext(LocationContext);
  if (!context) throw new Error('useLocation must be used within a LocationProvider');
  return context;
};

// Parsea JSON de localStorage de forma segura; limpia la clave si está corrompida.
function safeParse<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    localStorage.removeItem(key);
    return fallback;
  }
}

export const LocationProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const locationAbortRef = useRef<AbortController | null>(null);
  const [coords, setCoords] = useState<{ lat: number; lng: number } | null>(
    () => safeParse<{ lat: number; lng: number } | null>('user_coords', null)
  );

  const [selectedBranches, setSelectedBranches] = useState<Record<string, Branch>>(
    () => safeParse<Record<string, Branch>>('selected_branches', {})
  );

  const [selectedStore, setSelectedStoreState] = useState<string | null>(
    () => localStorage.getItem('selected_store')
  );

  const setSelectedStore = (slug: string | null) => {
    setSelectedStoreState(slug);
    if (slug) localStorage.setItem('selected_store', slug);
    else localStorage.removeItem('selected_store');
  };

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedLocationName, setSelectedLocationName] = useState<string | null>(
    () => localStorage.getItem('user_location_name')
  );

  // Sincronizar estado cuando otra pestaña modifica localStorage
  useEffect(() => {
    const handleStorage = (e: StorageEvent) => {
      if (e.key === 'user_coords') {
        if (!e.newValue) { setCoords(null); return; }
        try { setCoords(JSON.parse(e.newValue)); } catch { setCoords(null); }
      } else if (e.key === 'selected_branches') {
        if (!e.newValue) { setSelectedBranches({}); return; }
        try { setSelectedBranches(JSON.parse(e.newValue)); } catch { setSelectedBranches({}); }
      } else if (e.key === 'user_location_name') {
        setSelectedLocationName(e.newValue);
      }
    };
    window.addEventListener('storage', handleStorage);
    return () => window.removeEventListener('storage', handleStorage);
  }, []);
  
  const updateLocation = async (lat: number, lng: number, name?: string) => {
    // Cancelar cualquier búsqueda de sucursales previa que aún esté en curso
    locationAbortRef.current?.abort();
    const controller = new AbortController();
    locationAbortRef.current = controller;

    setLoading(true);
    setError(null);
    try {
      const point = { lat, lng };
      setCoords(point);
      localStorage.setItem('user_coords', JSON.stringify(point));

      if (name) {
        setSelectedLocationName(name);
        localStorage.setItem('user_location_name', name);
      }

      // Fetch new nearest branches automatically
      const nearest = await getNearestBranches(lat, lng);
      if (controller.signal.aborted) return;
      
      // Auto-select the absolute nearest for each store if none selected
      const newSelections = { ...selectedBranches };
      const stores = Array.from(new Set(nearest.map(b => b.store_id)));
      
      stores.forEach(sId => {
        const branch = nearest.find(b => b.store_id === sId);
        if (branch) {
          const slug = branch.store_name.toLowerCase().replaceAll(' ', '_');
          newSelections[slug] = branch;
        }
      });

      setSelectedBranches(newSelections);
      localStorage.setItem('selected_branches', JSON.stringify(newSelections));
      toast.success('Ubicación actualizada correctamente');
    } catch (err) {
      console.error('Error updating location:', err);
      setError('No se pudieron obtener las sucursales cercanas');
      toast.error('Error al actualizar ubicación');
    } finally {
      setLoading(false);
    }
  };
  
  const clearLocation = () => {
    setCoords(null);
    setSelectedBranches({});
    setSelectedLocationName(null);
    localStorage.removeItem('user_coords');
    localStorage.removeItem('selected_branches');
    localStorage.removeItem('user_location_name');
    localStorage.setItem('location_dismissed', 'true');
    toast.success('Usando precios web genéricos');
  };

  const selectBranch = (storeSlug: string, branch: Branch) => {
    const newSelections = { ...selectedBranches, [storeSlug]: branch };
    setSelectedBranches(newSelections);
    localStorage.setItem('selected_branches', JSON.stringify(newSelections));
    toast.success(`${branch.store_name}: ${branch.name} seleccionado`);
  };

  const requestCurrentLocation = () => {
    if (!navigator.geolocation) {
      toast.error('Geolocalización no soportada por su navegador');
      return;
    }

    setLoading(true);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        updateLocation(pos.coords.latitude, pos.coords.longitude);
      },
      (err) => {
        console.error('Geolocation error:', err);
        setLoading(false);
        toast.error('No se pudo obtener tu ubicación. Por favor, selecciónala manualmente.');
      },
      { enableHighAccuracy: true, timeout: 5000 }
    );
  };

  const getBranchContext = () => {
    const context: Record<string, string> = {};
    Object.entries(selectedBranches).forEach(([slug, branch]) => {
      context[slug] = (branch as Branch).external_store_id;
    });
    return context;
  };

  // Initial check: Disabled automatically as requested (Stand by)
  /*
  useEffect(() => {
    if (!coords && !localStorage.getItem('location_dismissed')) {
      requestCurrentLocation();
    }
  }, []);
  */

  return (
    <LocationContext.Provider value={{
      coords,
      selectedBranches,
      loading,
      error,
      selectedLocationName,
      selectedStore,
      setSelectedStore,
      updateLocation,
      clearLocation,
      selectBranch,
      requestCurrentLocation,
      getBranchContext
    }}>
      {children}
    </LocationContext.Provider>
  );
};

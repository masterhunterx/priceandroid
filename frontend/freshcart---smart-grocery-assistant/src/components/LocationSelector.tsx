import React, { useState, useEffect } from 'react';
import { useLocation } from '../context/LocationContext';
import { getNearestBranches, getLocationHierarchy } from '../lib/api';
import { Branch, LocationHierarchy, Comuna } from '../types';
import StoreLogo from './StoreLogo';
import toast from 'react-hot-toast';
import BranchMap from './BranchMap';

interface LocationSelectorProps {
  isOpen: boolean;
  onClose: () => void;
}

const LocationSelector: React.FC<LocationSelectorProps> = ({ isOpen, onClose }) => {
  const { coords, selectedBranches, selectBranch, requestCurrentLocation, loading, updateLocation, clearLocation, selectedLocationName } = useLocation();
  const [nearestBranches, setNearestBranches] = useState<Branch[]>();
  const [localLoading, setLocalLoading] = useState(false);
  const [selectedForMap, setSelectedForMap] = useState<Branch | null>(null);
  const [expandedBrand, setExpandedBrand] = useState<string | null>(null);

  // Auto-select first branch for map when nearest branches are loaded
  useEffect(() => {
    if (nearestBranches && nearestBranches.length > 0 && !selectedForMap) {
      setSelectedForMap(nearestBranches[0]);
      // Auto-expand the brand of the closest branch
      const firstBrand = nearestBranches[0].store_name.toLowerCase().replace(' ', '_');
      setExpandedBrand(firstBrand);
    }
  }, [nearestBranches, selectedForMap]);
  
  // Manual selection states
  const [hierarchy, setHierarchy] = useState<LocationHierarchy | null>(null);
  const [selectedRegion, setSelectedRegion] = useState<string>('');
  const [selectedComuna, setSelectedComuna] = useState<string>('');
  const [showManual, setShowManual] = useState(false);

  useEffect(() => {
    if (isOpen) {
      getLocationHierarchy()
        .then(data => {
          setHierarchy(data);
          // #8 — Fallback logic: if no coords, show manual selection automatically
          if (!coords) setShowManual(true);
        })
        .catch(err => {
          console.error('Error fetching hierarchy:', err);
          toast.error('No se pudo cargar la lista de regiones');
        });
    }
  }, [isOpen, coords]);

  useEffect(() => {
    if (isOpen && coords) {
      setLocalLoading(true);
      getNearestBranches(coords.lat, coords.lng)
        .then(data => setNearestBranches(data))
        .catch(console.error)
        .finally(() => setLocalLoading(false));
    }
  }, [isOpen, coords]);

  const handleManualSelect = async () => {
    if (!selectedRegion || !selectedComuna || !hierarchy) return;
    
    const comunaData = hierarchy[selectedRegion]?.find(c => c.name === selectedComuna);
    if (comunaData) {
      setSelectedForMap(null); // Reset map to trigger auto-select for new location
      await updateLocation(comunaData.lat, comunaData.lng, comunaData.name);
      // Automatically show the first branch on map if available
      setShowManual(false);
    }
  };

  const handleSelectBranch = (slug: string, branch: Branch) => {
    selectBranch(slug, branch);
    setSelectedForMap(branch);
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[100] flex items-end sm:items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="bg-white dark:bg-slate-900 w-full max-w-md rounded-t-3xl sm:rounded-3xl shadow-2xl overflow-hidden animate-in slide-in-from-bottom-10 duration-300">
        <div className="p-4 border-b border-slate-100 dark:border-slate-800 flex items-center justify-between">
          <h3 className="text-lg font-bold text-slate-900 dark:text-white">📍 Seleccionar Sucursal</h3>
          <button onClick={onClose} className="p-2 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200">
             <span className="material-symbols-outlined">close</span>
          </button>
        </div>

        <div className="p-4 max-h-[70vh] overflow-y-auto">
          <div className="flex flex-col gap-3 mb-6">
            <button 
              onClick={requestCurrentLocation}
              className="w-full flex items-center justify-center gap-2 py-3 px-4 bg-primary text-background-dark font-bold rounded-xl shadow-lg shadow-primary/20 hover:scale-[1.02] active:scale-95 transition-all"
            >
              <span className="material-symbols-outlined text-[20px]">my_location</span>
              Usar mi ubicación actual
            </button>

            <button 
              onClick={() => { clearLocation(); onClose(); }}
              className="w-full flex items-center justify-center gap-2 py-3 px-4 bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 font-bold rounded-xl hover:bg-slate-200 dark:hover:bg-slate-700 transition-all border border-slate-200 dark:border-slate-700"
            >
              <span className="material-symbols-outlined text-[20px]">public</span>
              Continuar con precios web genéricos
            </button>

            <button 
              onClick={() => setShowManual(!showManual)}
              className="w-full flex items-center justify-center gap-2 py-3 px-4 bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 font-bold rounded-xl hover:bg-slate-200 dark:hover:bg-slate-700 transition-all border border-slate-200 dark:border-slate-700"
            >
              <span className="material-symbols-outlined text-[20px]">map</span>
              {showManual ? 'Cerrar selección manual' : 'Seleccionar por Región/Comuna'}
            </button>
          </div>

          {showManual && hierarchy && (
            <div className="mb-8 p-4 bg-slate-50 dark:bg-slate-800/30 rounded-2xl border border-slate-100 dark:border-slate-800 animate-in slide-in-from-top-4 duration-300">
              <p className="text-[10px] font-black text-primary uppercase mb-4 tracking-tighter">Selección Manual de Comuna</p>
              
              <div className="space-y-4">
                <div>
                  <label className="block text-xs font-bold text-slate-500 mb-1.5 ml-1">Región</label>
                  <select 
                    value={selectedRegion}
                    onChange={(e) => { setSelectedRegion(e.target.value); setSelectedComuna(''); }}
                    className="w-full p-3 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm focus:ring-2 focus:ring-primary/20 outline-none transition-all dark:text-white"
                  >
                    <option value="">Selecciona una región...</option>
                    {Object.keys(hierarchy).sort().map(reg => (
                      <option key={reg} value={reg}>{reg}</option>
                    ))}
                  </select>
                </div>

                {selectedRegion && (
                  <div>
                    <label className="block text-xs font-bold text-slate-500 mb-1.5 ml-1">Comuna</label>
                    <select 
                      value={selectedComuna}
                      onChange={(e) => setSelectedComuna(e.target.value)}
                      className="w-full p-3 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm focus:ring-2 focus:ring-primary/20 outline-none transition-all dark:text-white"
                    >
                      <option value="">Selecciona una comuna...</option>
                      {hierarchy[selectedRegion].map(c => (
                        <option key={c.name} value={c.name}>
                          {c.name} ({c.details || `${c.store_count} tiendas`})
                        </option>
                      ))}
                    </select>
                  </div>
                )}

                <button 
                  disabled={!selectedComuna}
                  onClick={handleManualSelect}
                  className="w-full py-3 bg-primary text-background-dark font-black rounded-xl disabled:opacity-50 disabled:grayscale transition-all mt-2"
                >
                  Establecer Ubicación
                </button>
              </div>
            </div>
          )}

          {selectedForMap && selectedForMap.latitude && selectedForMap.longitude && (
            <div className="mb-6 animate-in zoom-in-95 duration-500">
              <BranchMap 
                lat={selectedForMap.latitude} 
                lng={selectedForMap.longitude} 
                name={selectedForMap.name} 
                address={selectedForMap.address} 
              />
            </div>
          )}

          {coords && (
            <div className="mb-6 flex items-center justify-between px-2">
              <p className="text-xs font-bold text-slate-400 uppercase tracking-widest">Tiendas Cercanas</p>
              {selectedLocationName && (
                <span className="text-[10px] font-bold text-primary bg-primary/10 px-2 py-0.5 rounded-full ring-1 ring-primary/20">
                  {selectedLocationName}
                </span>
              )}
            </div>
          )}
          
          {(loading || localLoading) ? (
            <div className="flex flex-col gap-3">
              {[1, 2, 3].map(i => (
                <div key={i} className="h-20 w-full animate-pulse bg-slate-100 dark:bg-slate-800 rounded-2xl"></div>
              ))}
            </div>
          ) : (nearestBranches && nearestBranches.length > 0) ? (
            <div className="space-y-6">
              {['jumbo', 'santa_isabel', 'unimarc', 'lider'].map(slug => {
                const storeBranches = nearestBranches.filter(b => b.store_name.toLowerCase().replace(' ', '_') === slug);
                if (storeBranches.length === 0) return null;

                const isExpanded = expandedBrand === slug;

                return (
                  <div key={slug} className="overflow-hidden border border-slate-100 dark:border-slate-800 rounded-2xl bg-slate-50/50 dark:bg-slate-800/30">
                    <button 
                      onClick={() => setExpandedBrand(isExpanded ? null : slug)}
                      className={`w-full flex items-center justify-between p-4 transition-all ${isExpanded ? 'bg-primary/5 border-b border-primary/10' : ''}`}
                    >
                      <div className="flex items-center gap-3">
                        <StoreLogo slug={slug} name={slug} className="size-6 drop-shadow-sm" />
                        <span className="text-sm font-black text-slate-700 dark:text-slate-200 uppercase tracking-tight">
                          {slug.replace('_', ' ')}
                        </span>
                        <span className="text-[10px] font-bold text-slate-400 bg-slate-100 dark:bg-slate-800 px-2 py-0.5 rounded-full">
                          {storeBranches.length}
                        </span>
                      </div>
                      <span className={`material-symbols-outlined text-slate-400 transition-transform duration-300 ${isExpanded ? 'rotate-180' : ''}`}>
                        expand_more
                      </span>
                    </button>
                    
                    <div className={`grid gap-2 p-2 transition-all duration-300 ${isExpanded ? 'opacity-100' : 'hidden opacity-0'}`}>
                      {storeBranches.map(branch => {
                        const isSelected = selectedBranches[slug]?.id === branch.id;
                        return (
                          <button
                            key={branch.id}
                            onClick={() => handleSelectBranch(slug, branch)}
                            className={`flex flex-col p-3 rounded-xl border text-left transition-all ${
                              isSelected 
                                ? 'border-primary bg-white dark:bg-slate-900 shadow-sm' 
                                : 'border-transparent hover:border-slate-200 dark:hover:border-slate-700 hover:bg-white dark:hover:bg-slate-800'
                            }`}
                          >
                            <div className="flex items-center justify-between">
                              <span className={`text-xs font-bold ${isSelected ? 'text-primary' : 'text-slate-900 dark:text-white'}`}>
                                {branch.name}
                              </span>
                              {isSelected && <span className="material-symbols-outlined text-primary text-[16px]">check_circle</span>}
                            </div>
                            <div className="flex items-center justify-between mt-1">
                              <span className="text-[10px] text-slate-500 truncate max-w-[150px]">{branch.address || branch.city}</span>
                              <span className={`text-[9px] font-black text-primary bg-primary/10 px-1.5 rounded uppercase ${branch.distance_km > 30 ? 'bg-amber-100 dark:bg-amber-900/30 text-amber-600' : ''}`}>
                                {branch.distance_km > 30 ? `Regional (${branch.distance_km} km)` : `${branch.distance_km} km`}
                              </span>
                            </div>
                          </button>
                        );
                      })}
                    </div>
                  </div>
                );
              })}
            </div>
          ) : coords ? (
            <div className="text-center py-8">
              <span className="material-symbols-outlined text-slate-300 text-[48px]">location_off</span>
              <p className="text-slate-500 mt-2">No se encontraron tiendas cercanas a tu ubicación.</p>
            </div>
          ) : (
            <div className="text-center py-12 px-6 bg-slate-50 dark:bg-slate-800/20 rounded-3xl border-2 border-dashed border-slate-200 dark:border-slate-800">
               <span className="material-symbols-outlined text-primary text-[48px] animate-bounce">location_on</span>
               <h4 className="text-sm font-bold text-slate-900 dark:text-white mt-4">Ubicación No Establecida</h4>
               <p className="text-xs text-slate-500 mt-2 leading-relaxed">
                 Usa el botón de arriba para detectar tu posición o selecciona una comuna manualmente para ver los precios de tu zona.
               </p>
            </div>
          )}
        </div>

        <div className="p-4 bg-slate-50 dark:bg-slate-800/50">
          <p className="text-[10px] text-slate-500 text-center uppercase tracking-tighter">
            Los precios se ajustarán automáticamente según tu selección.
          </p>
        </div>
      </div>
    </div>
  );
};

export default LocationSelector;

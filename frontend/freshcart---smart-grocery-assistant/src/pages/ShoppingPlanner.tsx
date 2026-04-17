import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { optimizeCart, formatCurrency, getFavorites, buyPantryItems } from '../lib/api';
import RouteMap from '../components/RouteMap';

const ShoppingPlanner: React.FC = () => {
  const navigate = useNavigate();
  const [result, setResult] = useState<any | null>(null);
  const [loading, setLoading] = useState(false);
  const [favorites, setFavorites] = useState<any[]>([]);
  const [showMap, setShowMap] = useState(false);

  const generateMockStores = (storeNames: string[]) => {
    const baseLat = -33.4489;
    const baseLng = -70.6693;
    return storeNames.map((name: string, index: number) => ({
      name,
      lat: baseLat + (index * 0.01) - 0.005,
      lng: baseLng + (index * 0.01) - 0.005,
    }));
  };

  const handleBuyCart = async () => {
    if (!result || !result.items) return;
    const pantryItems = result.items
        .filter((item: any) => item.status === 'optimized')
        .map((item: any) => ({ product_id: item.product_id || 1, stock_level: 'full' })); 
    
    try {
        await buyPantryItems(pantryItems);
        navigate('/pantry');
    } catch (error) {
        console.error(error);
        alert('Error al añadir a despensa');
    }
  };

  useEffect(() => {
    async function loadFavorites() {
      try {
        const data = await getFavorites();
        setFavorites(data);
      } catch (error) {
        console.error('Error loading favorites:', error);
      }
    }
    loadFavorites();
  }, []);

  const handleRunOptimization = async () => {
    if (favorites.length === 0) return;
    setLoading(true);
    try {
      // Use favorite names as queries for the optimizer
      const items = favorites.map(f => ({
        query: f.name || f.canonical_name,
        qty: 1
      }));
      const data = await optimizeCart(items);
      if (!data || !data.items) {
        throw new Error('Respuesta del servidor inválida');
      }
      setResult(data);
    } catch (error: any) {
      console.error('Optimization failed:', error);
      alert('KAIROS encontró un error al optimizar tu canasta. Por favor, intenta de nuevo. Detalle: ' + (error.message || 'Error desconocido'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-col min-h-screen bg-slate-50 dark:bg-[#0d1a12]">
      <header className="p-6 bg-white dark:bg-[#1a2e22]/50 backdrop-blur-md sticky top-0 z-10 border-b border-slate-100 dark:border-white/5">
        <div className="flex items-center gap-4 mb-2">
          <button onClick={() => navigate('/')} className="size-10 flex items-center justify-center rounded-full bg-slate-100 dark:bg-white/10 active:scale-95 transition-all text-slate-900 dark:text-white">
            <span className="material-symbols-outlined">arrow_back</span>
          </button>
          <h1 className="text-2xl font-black text-slate-900 dark:text-white tracking-tight">KAIROS Planner</h1>
        </div>
        <p className="text-slate-500 dark:text-[#9db9a8] text-sm">Optimización multibodega con inteligencia FluxEngine v5.0.</p>
      </header>

      <main className="flex-1 p-6 pb-24">
        {!result && !loading && (
          <div className="flex flex-col items-center justify-center py-20 text-center">
            <div className={`size-32 rounded-3xl ${favorites.length > 0 ? 'bg-primary/10 border-2 border-primary/20' : 'bg-slate-100'} flex items-center justify-center mb-8 relative`}>
               {favorites.length > 0 && (
                 <div className="absolute -top-2 -right-2 bg-primary text-background-dark text-[10px] font-black px-2 py-1 rounded-full animate-bounce">
                    {favorites.length}
                 </div>
               )}
               <span className={`material-symbols-outlined text-[64px] ${favorites.length > 0 ? 'text-primary' : 'text-slate-300'}`}>
                 {favorites.length > 0 ? 'auto_awesome' : 'favorite'}
               </span>
            </div>
            <h2 className="text-2xl font-black mb-3 text-slate-900 dark:text-white">
              {favorites.length > 0 ? 'Calculador de Ahorro Real' : 'Tu lista está vacía'}
            </h2>
            <p className="text-slate-500 dark:text-slate-400 text-sm mb-10 px-4 leading-relaxed">
              {favorites.length > 0 
                ? `KAIROS analizará miles de precios en segundos para encontrar la combinación más barata para tus productos.`
                : 'Marca productos con un corazón para que el optimizador pueda calcular tu ruta de compra ideal.'}
            </p>
            {favorites.length > 0 ? (
              <button 
                onClick={handleRunOptimization}
                disabled={loading}
                className="w-full max-w-xs bg-primary text-background-dark font-black px-12 py-5 rounded-2xl shadow-xl shadow-primary/20 active:scale-95 transition-all flex items-center justify-center gap-3 disabled:opacity-50 disabled:grayscale"
              >
                <span className="material-symbols-outlined">rocket_launch</span>
                Optimizar mi canasta
              </button>
            ) : (
              <button 
                onClick={() => navigate('/search')}
                className="w-full max-w-xs bg-slate-900 dark:bg-white text-white dark:text-slate-900 font-black px-12 py-5 rounded-2xl active:scale-95 transition-all"
              >
                Explorar Catálogo
              </button>
            )}
          </div>
        )}

        {loading && (
          <div className="flex flex-col items-center justify-center py-24">
             <div className="size-20 relative">
                <div className="absolute inset-0 border-[6px] border-primary/10 rounded-full"></div>
                <div className="absolute inset-0 border-[6px] border-primary border-t-transparent rounded-full animate-spin"></div>
                <div className="absolute inset-4 bg-primary/10 rounded-full animate-pulse"></div>
             </div>
             <p className="mt-8 text-primary font-black uppercase tracking-widest text-sm animate-pulse">KAIROS está pensando...</p>
             <p className="text-slate-500 text-xs mt-2 italic">Analizando Jumbo, Líder, Unimarc y Santa Isabel</p>
          </div>
        )}

        {result && (
          <div className="space-y-8 animate-in fade-in slide-in-from-bottom-6 duration-700">
            {/* Premium Result Card */}
            <div className="relative overflow-hidden bg-gradient-to-br from-[#1a2e22] to-[#122319] border border-primary/30 rounded-3xl p-8 shadow-2xl">
               <div className="absolute -top-10 -right-10 size-48 bg-primary/10 blur-[80px] rounded-full"></div>
               
               <div className="flex justify-between items-start relative z-10">
                  <div>
                    <div className="flex items-center gap-2 mb-2">
                       <span className="bg-primary/20 text-primary text-[10px] font-black px-2 py-0.5 rounded-full uppercase tracking-widest">Ahorro Máximo v5.0</span>
                    </div>
                    <p className="text-slate-400 text-xs font-bold uppercase tracking-widest mb-1">Total Optimizado</p>
                    <h3 className="text-4xl font-black text-white">{formatCurrency(result.total_cart_cost)}</h3>
                  </div>
                  <div className="size-16 bg-white/5 backdrop-blur-md rounded-2xl flex flex-col items-center justify-center border border-white/10">
                    <span className="text-primary font-black text-xl leading-none">{result.optimized_count}</span>
                    <span className="text-[8px] font-bold text-slate-500 uppercase tracking-tighter">Items</span>
                  </div>
               </div>

               <div className="mt-8 grid grid-cols-2 gap-4 pt-6 border-t border-white/5 relative z-10">
                  <div className="flex flex-col">
                    <span className="text-[10px] text-slate-500 uppercase font-bold tracking-widest">Ruta de Compra</span>
                    <p className="text-sm font-bold text-slate-200">{result.stores_visited.length} Supermercado{result.stores_visited.length > 1 ? 's' : ''}</p>
                  </div>
                  <div className="flex flex-col text-right">
                    <span className="text-[10px] text-slate-500 uppercase font-bold tracking-widest">Tiendas</span>
                    <p className="text-[10px] font-bold text-primary truncate max-w-[120px]">{result.stores_visited.join(', ')}</p>
                  </div>
               </div>
            </div>

            {/* List Header */}
            <div className="flex items-center justify-between px-2">
              <h3 className="text-lg font-black text-slate-900 dark:text-white uppercase tracking-tight">Tu Canasta Optimizada</h3>
              <span className="material-symbols-outlined text-slate-400">tune</span>
            </div>

            {/* Optimized Items */}
            <div className="space-y-4">
               {result.items.map((item: any, idx: number) => (
                 <div key={idx} className={`group flex items-center justify-between p-5 rounded-2xl border transition-all duration-300 ${
                   item.status === 'optimized' 
                   ? 'bg-white dark:bg-white/5 border-slate-100 dark:border-white/5 hover:border-primary/30' 
                   : 'bg-red-500/5 border-red-500/20 grayscale'
                 }`}>
                    <div className="flex items-center gap-4">
                       <div className={`size-14 rounded-xl flex items-center justify-center overflow-hidden border ${
                         item.status === 'optimized' ? 'bg-slate-50 dark:bg-white/5 border-slate-100 dark:border-white/5' : 'bg-red-100/10 border-red-500/20'
                       }`}>
                          {item.image_url ? (
                            <img src={item.image_url} alt={item.product_name} className="size-10 object-contain" />
                          ) : (
                            <span className="material-symbols-outlined text-slate-300">shopping_basket</span>
                          )}
                       </div>
                       <div className="flex flex-col">
                          <p className={`text-sm font-black leading-tight truncate w-36 ${item.status === 'optimized' ? 'text-slate-900 dark:text-white' : 'text-slate-500'}`}>
                            {item.product_name || item.query}
                          </p>
                          <div className="flex items-center gap-2 mt-1">
                             <span className="text-[10px] font-black text-primary uppercase">{item.store || 'Sin Stock'}</span>
                             {item.status === 'optimized' && (
                               <span className="text-[9px] text-slate-400 font-bold">• {item.qty} un</span>
                             )}
                          </div>
                       </div>
                    </div>
                    <div className="text-right">
                       <p className={`text-lg font-black ${item.status === 'optimized' ? 'text-slate-900 dark:text-white' : 'text-red-400'}`}>
                         {item.status === 'optimized' ? formatCurrency(item.total) : 'Agotado'}
                       </p>
                       {item.status === 'optimized' && (
                         <p className="text-[10px] text-slate-500 font-bold">Uni: {formatCurrency(item.unit_price)}</p>
                       )}
                    </div>
                 </div>
               ))}
            </div>

            <div className="pt-4 space-y-4">
              <button 
                onClick={() => setShowMap(!showMap)}
                className="w-full py-5 bg-slate-900 dark:bg-white text-white dark:text-slate-900 font-black rounded-2xl shadow-xl active:scale-95 transition-all text-sm uppercase tracking-widest"
              >
                {showMap ? 'Ocultar Direcciones' : 'Confirmar y Ver Direcciones'}
              </button>

              {showMap && result.stores_visited && (
                 <div className="mt-4 animate-in fade-in slide-in-from-top-4">
                    <RouteMap stores={generateMockStores(result.stores_visited)} />
                    <button 
                        onClick={handleBuyCart}
                        className="mt-4 w-full py-4 bg-primary text-background-dark font-black rounded-2xl shadow-xl active:scale-95 transition-all text-sm uppercase tracking-widest flex items-center justify-center gap-2"
                    >
                        <span className="material-symbols-outlined">inventory_2</span>
                        Simular Compra y añadir a despensa
                    </button>
                 </div>
              )}

              <button 
                onClick={() => { setResult(null); setShowMap(false); }}
                className="w-full py-4 text-slate-400 font-bold uppercase tracking-widest text-[10px] hover:text-primary transition-colors"
              >
                Reiniciar Planificación
              </button>
            </div>
          </div>
        )}
      </main>
    </div>
  );
};

export default ShoppingPlanner;

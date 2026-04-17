import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { getPantry, consumePantryItem } from '../lib/api';

interface PantryItem {
  id: number;
  product_name: string;
  image_url: string | null;
  current_stock_level: 'full' | 'medium' | 'low' | 'empty';
  days_remaining: number | null;
}

const Pantry: React.FC = () => {
  const navigate = useNavigate();
  const [items, setItems] = useState<PantryItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchPantry();
  }, []);

  const fetchPantry = async () => {
    try {
      const data = await getPantry();
      setItems(data);
    } catch (error) {
      console.error('Error fetching pantry:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleConsume = async (id: number) => {
    try {
      await consumePantryItem(id);
      fetchPantry();
    } catch (error) {
      console.error('Error consuming item:', error);
    }
  };

  const getStockColor = (level: string) => {
    switch (level) {
      case 'full': return 'bg-emerald-500 text-white';
      case 'medium': return 'bg-amber-500 text-white';
      case 'low': return 'bg-orange-500 text-white';
      case 'empty': return 'bg-red-500 text-white';
      default: return 'bg-slate-500 text-white';
    }
  };

  const getStockLabel = (level: string) => {
    switch (level) {
      case 'full': return 'Lleno';
      case 'medium': return 'Medio';
      case 'low': return 'Por agotarse';
      case 'empty': return 'Agotado';
      default: return level;
    }
  };

  return (
    <div className="flex flex-col min-h-screen bg-slate-50 dark:bg-[#0d1a12]">
      <header className="p-6 bg-white dark:bg-[#1a2e22]/50 backdrop-blur-md sticky top-0 z-10 border-b border-slate-100 dark:border-white/5">
        <div className="flex items-center gap-4 mb-2">
          <button onClick={() => navigate('/')} className="size-10 flex items-center justify-center rounded-full bg-slate-100 dark:bg-white/10 active:scale-95 transition-all text-slate-900 dark:text-white">
            <span className="material-symbols-outlined">arrow_back</span>
          </button>
          <h1 className="text-2xl font-black text-slate-900 dark:text-white tracking-tight">Mi Despensa</h1>
        </div>
        <p className="text-slate-500 dark:text-[#9db9a8] text-sm">Gestiona tu inventario con Inteligencia Proactiva KAIROS.</p>
      </header>

      <main className="flex-1 p-6 pb-24">
        {loading ? (
           <div className="flex justify-center p-8">
              <span className="material-symbols-outlined animate-spin text-primary text-4xl">sync</span>
           </div>
        ) : items.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 text-center">
             <div className="size-24 rounded-full bg-slate-200 dark:bg-slate-800 flex items-center justify-center mb-6">
                <span className="material-symbols-outlined text-4xl text-slate-400">inventory_2</span>
             </div>
             <h2 className="text-xl font-bold text-slate-900 dark:text-white mb-2">Despensa Vacía</h2>
             <p className="text-slate-500 dark:text-slate-400 mb-8">Tus productos comprados usando el Planner aparecerán aquí mágicamente.</p>
             <button onClick={() => navigate('/planner')} className="bg-primary text-background-dark font-bold px-8 py-3 rounded-full">
                Ir al Planner
             </button>
          </div>
        ) : (
          <div className="grid gap-4">
             {items.map(item => (
                <div key={item.id} className="bg-white dark:bg-slate-800 p-4 rounded-2xl shadow-sm flex items-center gap-4 border border-slate-100 dark:border-slate-700">
                   <div className="size-16 rounded-xl bg-slate-50 dark:bg-slate-900 overflow-hidden flex items-center justify-center border border-slate-100 dark:border-slate-700 shrink-0">
                      {item.image_url ? (
                        <img src={item.image_url} alt={item.product_name} className="size-12 object-contain" />
                      ) : (
                        <span className="material-symbols-outlined text-slate-300">shopping_basket</span>
                      )}
                   </div>
                   
                   <div className="flex-1 min-w-0">
                      <h3 className="font-bold text-slate-900 dark:text-white text-sm truncate">{item.product_name}</h3>
                      <div className="flex items-center gap-2 mt-1">
                         <span className={`text-[10px] font-black uppercase px-2 py-0.5 rounded-full ${getStockColor(item.current_stock_level)}`}>
                            {getStockLabel(item.current_stock_level)}
                         </span>
                         {item.days_remaining !== null && (
                            <span className="text-[10px] font-bold text-slate-500 dark:text-slate-400">
                               Estimado: {item.days_remaining} días
                            </span>
                         )}
                      </div>
                   </div>
                   
                   <button 
                      onClick={() => handleConsume(item.id)}
                      disabled={item.current_stock_level === 'empty'}
                      className="size-10 rounded-full bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300 flex items-center justify-center hover:bg-slate-200 dark:hover:bg-slate-600 transition-colors disabled:opacity-50"
                      title="Reducir Stock"
                   >
                      <span className="material-symbols-outlined">remove</span>
                   </button>
                </div>
             ))}
          </div>
        )}
      </main>
    </div>
  );
};

export default Pantry;

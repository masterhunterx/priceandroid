import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useLocation } from '../context/LocationContext';
import { useAuth } from '../context/AuthContext';

const STORES = [
  { slug: 'jumbo',        name: 'Jumbo',        color: '#00a650', description: 'Variedad y calidad' },
  { slug: 'santa_isabel', name: 'Santa Isabel', color: '#e30613', description: 'Precios convenientes' },
  { slug: 'lider',        name: 'Líder',        color: '#0071ce', description: 'Walmart Chile' },
  { slug: 'unimarc',      name: 'Unimarc',      color: '#da291c', description: 'Cerca de ti' },
];

const StoreSelect: React.FC = () => {
  const navigate = useNavigate();
  const { setSelectedStore } = useLocation();
  const { isGuest } = useAuth();

  const handleSelect = (slug: string) => {
    setSelectedStore(slug);
    navigate('/', { replace: true });
  };

  const handleAll = () => {
    setSelectedStore(null);
    navigate('/', { replace: true });
  };

  return (
    <div className="min-h-screen bg-white dark:bg-zinc-950 flex flex-col px-6 pt-16 pb-10">

      {/* Header */}
      <div className="mb-10">
        <p className="text-xs font-semibold text-slate-400 dark:text-zinc-500 uppercase tracking-widest mb-2">FreshCart</p>
        <h1 className="text-3xl font-black text-slate-900 dark:text-white leading-tight">
          ¿Dónde vas<br />a comprar?
        </h1>
        {isGuest && (
          <p className="text-sm text-slate-400 dark:text-zinc-500 mt-2">
            Explorando sin cuenta · <span className="text-primary cursor-pointer" onClick={() => navigate('/login')}>Conectar con Google</span>
          </p>
        )}
      </div>

      {/* Store list */}
      <div className="flex flex-col divide-y divide-slate-100 dark:divide-zinc-800">
        {STORES.map((store) => (
          <button
            key={store.slug}
            onClick={() => handleSelect(store.slug)}
            className="flex items-center gap-4 py-4 text-left active:bg-slate-50 dark:active:bg-zinc-900 transition-colors rounded-xl -mx-2 px-2"
          >
            <div
              className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 text-white font-black text-base"
              style={{ backgroundColor: store.color }}
            >
              {store.name[0]}
            </div>
            <div className="flex-1 min-w-0">
              <p className="font-semibold text-slate-900 dark:text-white text-[15px]">{store.name}</p>
              <p className="text-sm text-slate-400 dark:text-zinc-500">{store.description}</p>
            </div>
            <span className="material-symbols-outlined text-slate-300 dark:text-zinc-600 text-[20px]">chevron_right</span>
          </button>
        ))}
      </div>

      {/* Ver todos */}
      <button
        onClick={handleAll}
        className="mt-6 flex items-center justify-center gap-2 py-3 text-slate-400 dark:text-zinc-500 text-sm font-medium hover:text-slate-600 dark:hover:text-zinc-300 transition-colors"
      >
        <span className="material-symbols-outlined text-[16px]">apps</span>
        Comparar todos los supermercados
      </button>

    </div>
  );
};

export default StoreSelect;

import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useLocation } from '../context/LocationContext';

const STORES = [
  {
    slug: 'jumbo',
    name: 'Jumbo',
    bg: '#00a650',
    initial: 'J',
    description: 'Variedad y calidad',
  },
  {
    slug: 'santa_isabel',
    name: 'Santa Isabel',
    bg: '#e30613',
    initial: 'S',
    description: 'Precios convenientes',
  },
  {
    slug: 'lider',
    name: 'Líder',
    bg: '#0071ce',
    initial: 'L',
    sun: true,
    description: 'Walmart Chile',
  },
  {
    slug: 'unimarc',
    name: 'Unimarc',
    bg: '#da291c',
    initial: 'U',
    description: 'Cerca de ti',
  },
];

const StoreSelect: React.FC = () => {
  const navigate = useNavigate();
  const { setSelectedStore } = useLocation();

  const handleSelect = (slug: string) => {
    setSelectedStore(slug);
    navigate('/', { replace: true });
  };

  const handleAll = () => {
    setSelectedStore(null);
    navigate('/', { replace: true });
  };

  return (
    <div className="min-h-screen bg-background-light dark:bg-background-dark flex flex-col">
      {/* Header */}
      <div className="flex flex-col items-center pt-16 pb-8 px-6">
        <div className="flex items-center gap-2 mb-6">
          <span className="material-symbols-outlined text-primary text-[32px]">shopping_cart</span>
          <span className="text-2xl font-black text-slate-900 dark:text-white tracking-tight">FreshCart</span>
        </div>
        <h1 className="text-2xl font-black text-slate-900 dark:text-white text-center leading-tight">
          ¿Dónde vas a<br />comprar hoy?
        </h1>
        <p className="text-sm text-slate-500 dark:text-slate-400 mt-2 text-center">
          Selecciona tu supermercado y ve solo sus ofertas
        </p>
      </div>

      {/* Store grid */}
      <div className="flex-1 px-5">
        <div className="grid grid-cols-2 gap-4">
          {STORES.map((store) => (
            <button
              key={store.slug}
              onClick={() => handleSelect(store.slug)}
              className="relative flex flex-col items-center justify-center rounded-3xl p-6 shadow-lg active:scale-95 transition-transform overflow-hidden"
              style={{ backgroundColor: store.bg, minHeight: '160px' }}
            >
              {/* Decorative circle */}
              <div
                className="absolute -top-6 -right-6 w-24 h-24 rounded-full opacity-20"
                style={{ backgroundColor: 'white' }}
              />
              <div
                className="absolute -bottom-8 -left-4 w-20 h-20 rounded-full opacity-10"
                style={{ backgroundColor: 'white' }}
              />

              {/* Initial letter */}
              <div className="relative z-10 flex items-center justify-center w-14 h-14 rounded-2xl bg-white/20 mb-3">
                {store.sun ? (
                  <div className="relative flex items-center justify-center">
                    <span className="text-[#ffc220] text-3xl font-black">{store.initial}</span>
                    <span
                      className="absolute -top-1 -right-1 text-[#ffc220] text-[10px]"
                      style={{ fontSize: '8px' }}
                    >✦</span>
                  </div>
                ) : (
                  <span className="text-white text-3xl font-black">{store.initial}</span>
                )}
              </div>

              <span className="relative z-10 text-white font-black text-base leading-tight text-center">
                {store.name}
              </span>
              <span className="relative z-10 text-white/70 text-[11px] mt-1 text-center">
                {store.description}
              </span>
            </button>
          ))}
        </div>

        {/* All stores option */}
        <button
          onClick={handleAll}
          className="w-full mt-5 flex items-center justify-center gap-2 py-4 rounded-2xl border-2 border-dashed border-slate-300 dark:border-slate-600 text-slate-500 dark:text-slate-400 font-semibold text-sm active:scale-95 transition-transform"
        >
          <span className="material-symbols-outlined text-[18px]">store</span>
          Ver todas las tiendas
        </button>
      </div>

      <div className="pb-10" />
    </div>
  );
};

export default StoreSelect;

import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useLocation } from '../context/LocationContext';
import { useAuth } from '../context/AuthContext';

const STORES = [
  {
    slug: 'jumbo',
    name: 'Jumbo',
    tagline: 'Variedad y calidad',
    bg: 'bg-[#00a650]',
    shadow: 'shadow-green-500/30',
    logo: (
      <svg viewBox="0 0 60 60" className="w-14 h-14">
        <circle cx="30" cy="30" r="30" fill="#00a650" />
        <text x="30" y="38" textAnchor="middle" fontSize="26" fontWeight="900" fill="white" fontFamily="Arial">J</text>
      </svg>
    ),
  },
  {
    slug: 'lider',
    name: 'Líder',
    tagline: 'Walmart Chile',
    bg: 'bg-[#0071ce]',
    shadow: 'shadow-blue-500/30',
    logo: (
      <svg viewBox="0 0 60 60" className="w-14 h-14">
        <circle cx="30" cy="30" r="30" fill="#0071ce" />
        <circle cx="30" cy="30" r="10" fill="#ffc220" />
        {[0,45,90,135,180,225,270,315].map((deg, i) => (
          <line
            key={i}
            x1="30" y1="30"
            x2={30 + 20 * Math.cos((deg * Math.PI) / 180)}
            y2={30 + 20 * Math.sin((deg * Math.PI) / 180)}
            stroke="#ffc220" strokeWidth="3" strokeLinecap="round"
          />
        ))}
      </svg>
    ),
  },
  {
    slug: 'unimarc',
    name: 'Unimarc',
    tagline: 'Cerca de ti',
    bg: 'bg-[#da291c]',
    shadow: 'shadow-red-500/30',
    logo: (
      <svg viewBox="0 0 60 60" className="w-14 h-14">
        <circle cx="30" cy="30" r="30" fill="#da291c" />
        <text x="30" y="38" textAnchor="middle" fontSize="26" fontWeight="900" fill="white" fontFamily="Arial">U</text>
      </svg>
    ),
  },
  {
    slug: 'santa_isabel',
    name: 'Santa Isabel',
    tagline: 'Precios convenientes',
    bg: 'bg-[#e30613]',
    shadow: 'shadow-red-600/30',
    logo: (
      <svg viewBox="0 0 60 60" className="w-14 h-14">
        <circle cx="30" cy="30" r="30" fill="#e30613" />
        <text x="30" y="38" textAnchor="middle" fontSize="24" fontWeight="900" fill="white" fontFamily="Arial">SI</text>
      </svg>
    ),
  },
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
    <div className="min-h-screen bg-slate-50 dark:bg-zinc-950 flex flex-col px-5 pt-14 pb-8">

      {/* Header */}
      <div className="mb-8">
        <p className="text-xs font-bold text-primary uppercase tracking-widest mb-2">FreshCart</p>
        <h1 className="text-3xl font-black text-slate-900 dark:text-white leading-tight">
          ¿Dónde vas<br />a comprar hoy?
        </h1>
        {isGuest ? (
          <p className="text-sm text-slate-400 dark:text-zinc-500 mt-2">
            Explorando sin cuenta ·{' '}
            <span className="text-primary font-semibold cursor-pointer" onClick={() => navigate('/login')}>
              Iniciar sesión
            </span>
          </p>
        ) : (
          <p className="text-sm text-slate-400 dark:text-zinc-500 mt-2">
            Selecciona tu supermercado principal
          </p>
        )}
      </div>

      {/* Grid 2x2 de tiendas */}
      <div className="grid grid-cols-2 gap-4 flex-1">
        {STORES.map((store) => (
          <button
            key={store.slug}
            onClick={() => handleSelect(store.slug)}
            className={`
              flex flex-col items-center justify-center gap-3 rounded-3xl py-8 px-4
              bg-white dark:bg-zinc-900
              border border-slate-100 dark:border-zinc-800
              shadow-lg ${store.shadow}
              active:scale-95 transition-all duration-150
            `}
          >
            <div className="rounded-2xl overflow-hidden shadow-md">
              {store.logo}
            </div>
            <div className="text-center">
              <p className="font-bold text-slate-900 dark:text-white text-[15px] leading-tight">{store.name}</p>
              <p className="text-xs text-slate-400 dark:text-zinc-500 mt-0.5">{store.tagline}</p>
            </div>
          </button>
        ))}
      </div>

      {/* Ver todas */}
      <button
        onClick={handleAll}
        className="mt-6 w-full flex items-center justify-center gap-2.5 py-4 rounded-2xl bg-white dark:bg-zinc-900 border border-slate-200 dark:border-zinc-800 text-slate-600 dark:text-zinc-300 font-semibold text-sm active:scale-95 transition-all shadow-sm"
      >
        <span className="material-symbols-outlined text-primary text-[20px]">compare_arrows</span>
        Comparar todos los supermercados
      </button>

    </div>
  );
};

export default StoreSelect;

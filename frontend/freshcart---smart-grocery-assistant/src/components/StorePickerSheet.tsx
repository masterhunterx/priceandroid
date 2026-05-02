import React, { useEffect } from 'react';

const STORES = [
  { slug: 'jumbo',        name: 'Jumbo',        color: '#00a650', bg: 'bg-[#00a650]', label: 'J' },
  { slug: 'lider',        name: 'Líder',        color: '#0071ce', bg: 'bg-[#0071ce]', label: 'L' },
  { slug: 'unimarc',      name: 'Unimarc',      color: '#da291c', bg: 'bg-[#da291c]', label: 'U' },
  { slug: 'santa_isabel', name: 'Santa Isabel', color: '#e30613', bg: 'bg-[#e30613]', label: 'SI' },
];

interface StorePickerSheetProps {
  isOpen: boolean;
  currentStore: string | null;
  onSelect: (slug: string | null) => void;
  onClose: () => void;
}

const StorePickerSheet: React.FC<StorePickerSheetProps> = ({ isOpen, currentStore, onSelect, onClose }) => {
  // Bloquear scroll del body cuando el sheet está abierto
  useEffect(() => {
    if (isOpen) document.body.style.overflow = 'hidden';
    else document.body.style.overflow = '';
    return () => { document.body.style.overflow = ''; };
  }, [isOpen]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[100] flex flex-col justify-end">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Sheet */}
      <div className="relative bg-white dark:bg-zinc-900 rounded-t-3xl px-5 pt-4 pb-10 shadow-2xl animate-slide-up">
        {/* Handle */}
        <div className="w-10 h-1 rounded-full bg-slate-200 dark:bg-zinc-700 mx-auto mb-5" />

        <h3 className="text-lg font-black text-slate-900 dark:text-white mb-1">Cambiar supermercado</h3>
        <p className="text-sm text-slate-400 dark:text-zinc-500 mb-5">Selecciona dónde quieres comparar precios</p>

        {/* Grid 2x2 */}
        <div className="grid grid-cols-2 gap-3 mb-4">
          {STORES.map((store) => {
            const isActive = currentStore === store.slug;
            return (
              <button
                key={store.slug}
                onClick={() => { onSelect(store.slug); onClose(); }}
                className={`
                  flex items-center gap-3 p-3.5 rounded-2xl border-2 transition-all active:scale-95
                  ${isActive
                    ? 'border-current bg-opacity-10'
                    : 'border-slate-100 dark:border-zinc-800 bg-slate-50 dark:bg-zinc-800'}
                `}
                style={isActive ? { borderColor: store.color, backgroundColor: store.color + '15' } : undefined}
              >
                {/* Logo */}
                <div
                  className={`w-10 h-10 rounded-xl flex items-center justify-center shrink-0 ${store.bg}`}
                >
                  <span className="text-white font-black text-sm">{store.label}</span>
                </div>
                <div className="text-left min-w-0">
                  <p className="font-bold text-slate-900 dark:text-white text-sm truncate">{store.name}</p>
                  {isActive && (
                    <p className="text-[11px] font-semibold" style={{ color: store.color }}>Activa</p>
                  )}
                </div>
                {isActive && (
                  <span className="material-symbols-outlined ml-auto shrink-0 text-[18px]" style={{ color: store.color }}>
                    check_circle
                  </span>
                )}
              </button>
            );
          })}
        </div>

        {/* Todas las tiendas */}
        <button
          onClick={() => { onSelect(null); onClose(); }}
          className={`
            w-full flex items-center justify-center gap-2.5 py-3.5 rounded-2xl border-2 transition-all active:scale-95
            ${!currentStore
              ? 'border-primary bg-primary/10'
              : 'border-slate-200 dark:border-zinc-700 bg-slate-50 dark:bg-zinc-800'}
          `}
        >
          <span className="material-symbols-outlined text-primary text-[20px]">compare_arrows</span>
          <span className={`font-bold text-sm ${!currentStore ? 'text-primary' : 'text-slate-700 dark:text-zinc-300'}`}>
            Comparar todas las tiendas
          </span>
          {!currentStore && (
            <span className="material-symbols-outlined text-primary text-[18px]">check_circle</span>
          )}
        </button>
      </div>
    </div>
  );
};

export default StorePickerSheet;

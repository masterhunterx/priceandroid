import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useCart } from '../context/CartContext';
import { formatCurrency } from '../lib/api';
import { toast } from 'react-hot-toast';

const STORE_BADGE: Record<string, string> = {
  optimal:       'bg-primary text-black',
  jumbo:         'bg-blue-500 text-white',
  lider:         'bg-yellow-500 text-white',
  unimarc:       'bg-emerald-500 text-white',
  'santa-isabel':'bg-red-500 text-white',
  santa_isabel:  'bg-red-500 text-white',
  santaisabel:   'bg-red-500 text-white',
};

const Cart: React.FC = () => {
  const { cart, clearCart } = useCart();
  const navigate = useNavigate();

  if (!cart) {
    return (
      <div className="flex flex-col items-center justify-center h-[calc(100vh-80px)] gap-4 px-8 text-center">
        <span className="material-symbols-outlined text-6xl text-slate-300 dark:text-slate-600">
          shopping_cart
        </span>
        <h2 className="text-xl font-black text-slate-700 dark:text-slate-300">Tu carro está vacío</h2>
        <p className="text-sm text-slate-500 dark:text-slate-400">
          Busca productos y agrégalos al carro desde la pantalla de búsqueda.
        </p>
        <button
          onClick={() => navigate('/search')}
          className="mt-2 px-6 py-3 rounded-full bg-primary text-black font-black text-sm active:scale-95 transition-all"
        >
          Buscar productos
        </button>
      </div>
    );
  }

  const foundItems  = cart.items.filter(i => i.status === 'found');
  const missingItems = cart.items.filter(i => i.status === 'not_found');
  const badgeClass  = STORE_BADGE[cart.store_slug] ?? 'bg-slate-500 text-white';
  const addedDate   = new Date(cart.added_at).toLocaleDateString('es-CL', {
    day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit',
  });

  const handleClear = () => {
    clearCart();
    toast.success('Carro vaciado');
  };

  return (
    <div className="flex flex-col min-h-[calc(100vh-80px)] bg-slate-50 dark:bg-[#050c08]">

      {/* Header */}
      <header className="px-4 py-4 bg-white dark:bg-[#0a150f] border-b border-slate-200 dark:border-slate-800 flex items-center gap-3">
        <button onClick={() => navigate(-1)} className="size-9 rounded-full flex items-center justify-center text-slate-500 hover:bg-slate-100 dark:hover:bg-white/5 transition-all">
          <span className="material-symbols-outlined">arrow_back</span>
        </button>
        <div className="flex-1">
          <h1 className="font-black text-base leading-tight">Mi Carro</h1>
          <p className="text-[10px] text-slate-400">Generado por KAIROS · {addedDate}</p>
        </div>
        <button
          onClick={handleClear}
          className="text-[11px] font-bold text-red-400 hover:text-red-500 transition-colors px-2"
        >
          Vaciar
        </button>
      </header>

      {/* Store badge */}
      <div className="px-4 py-3 bg-white dark:bg-[#0a150f] border-b border-slate-100 dark:border-white/5 flex items-center gap-3">
        <span className={`text-xs font-black px-3 py-1.5 rounded-full ${badgeClass}`}>
          {cart.emoji} {cart.store}
        </span>
        <span className="text-xs text-slate-500 dark:text-slate-400">
          {foundItems.length} productos listos
          {missingItems.length > 0 && ` · ${missingItems.length} no encontrados`}
        </span>
      </div>

      {/* Items list */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3">

        {foundItems.map((item, i) => (
          <div key={i} className="bg-white dark:bg-[#0a150f] rounded-2xl border border-slate-100 dark:border-slate-800 p-3 flex gap-3 items-center shadow-sm">
            {/* Image */}
            {item.image_url ? (
              <img
                src={item.image_url}
                alt={item.name}
                className="size-14 rounded-xl object-contain bg-slate-50 dark:bg-[#14261c] shrink-0"
                onError={e => { (e.target as HTMLImageElement).style.display = 'none'; }}
              />
            ) : (
              <div className="size-14 rounded-xl bg-slate-100 dark:bg-[#14261c] shrink-0 flex items-center justify-center">
                <span className="material-symbols-outlined text-slate-300 text-2xl">image</span>
              </div>
            )}

            {/* Info */}
            <div className="flex-1 min-w-0">
              <p className="text-xs font-bold text-slate-800 dark:text-white leading-tight line-clamp-2">{item.name}</p>
              {item.brand && (
                <p className="text-[10px] text-slate-400 mt-0.5">{item.brand}</p>
              )}
              <div className="flex items-center justify-between mt-1.5">
                <span className="text-[10px] text-slate-400">
                  {item.qty} × {formatCurrency(item.price)}
                </span>
                <span className="text-sm font-black text-primary">{formatCurrency(item.total)}</span>
              </div>
            </div>
          </div>
        ))}

        {/* Missing items */}
        {missingItems.length > 0 && (
          <div className="mt-4">
            <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2 px-1">
              No encontrados en {cart.store}
            </p>
            {missingItems.map((item, i) => (
              <div key={i} className="bg-slate-100/60 dark:bg-white/5 rounded-xl px-3 py-2 flex items-center gap-2 mb-2">
                <span className="material-symbols-outlined text-slate-400 text-base">search_off</span>
                <p className="text-xs text-slate-400 italic">{item.name || item.query}</p>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Total footer */}
      <div className="bg-white dark:bg-[#0a150f] border-t border-slate-200 dark:border-slate-800 px-4 py-4">
        <div className="flex items-center justify-between mb-3">
          <div>
            <p className="text-[10px] text-slate-400 uppercase font-black tracking-widest">Total estimado</p>
            <p className="text-2xl font-black text-primary">{formatCurrency(cart.total_cost)}</p>
          </div>
          <div className="text-right">
            <p className="text-[10px] text-slate-400">{foundItems.length} de {cart.items.length} productos</p>
            <p className="text-[10px] text-slate-400 mt-0.5">Precios en {cart.store}</p>
          </div>
        </div>

        <div className="flex gap-2">
          <button
            onClick={() => navigate('/assistant')}
            className="flex-1 py-3 rounded-full border border-primary/40 text-primary font-black text-sm active:scale-95 transition-all"
          >
            Cambiar Plan
          </button>
          <button
            onClick={() => toast.success('¡Lista lista! Lleva el carro al supermercado.', { duration: 3000 })}
            className="flex-1 py-3 rounded-full bg-primary text-black font-black text-sm active:scale-95 transition-all flex items-center justify-center gap-1.5"
          >
            <span className="material-symbols-outlined text-lg">check_circle</span>
            Listo, voy al super
          </button>
        </div>
      </div>
    </div>
  );
};

export default Cart;

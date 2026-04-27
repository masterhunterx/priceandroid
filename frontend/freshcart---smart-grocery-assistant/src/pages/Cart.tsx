import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useCart, CartItem } from '../context/CartContext';
import { formatCurrency } from '../lib/api';
import StoreLogo from '../components/StoreLogo';
import { toast } from 'react-hot-toast';

const STORE_COLORS: Record<string, string> = {
  jumbo:        '#00a650',
  lider:        '#0071ce',
  santa_isabel: '#e30613',
  unimarc:      '#da291c',
};

interface StoreGroup {
  store_slug: string;
  store_name: string;
  items: CartItem[];
  subtotal: number;
}

const Cart: React.FC = () => {
  const { items, total, updateQty, removeItem, clearCart } = useCart();
  const navigate = useNavigate();

  if (items.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-[calc(100vh-80px)] gap-4 px-8 text-center">
        <span className="material-symbols-outlined text-6xl text-slate-300 dark:text-slate-600">
          shopping_cart
        </span>
        <h2 className="text-xl font-black text-slate-700 dark:text-slate-300">Tu carro está vacío</h2>
        <p className="text-sm text-slate-500 dark:text-slate-400">
          Toca el ícono <span className="font-bold">🛒</span> en cualquier producto para agregarlo aquí.
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

  // Agrupar por tienda
  const storeMap: Record<string, StoreGroup> = {};
  items.forEach(item => {
    const key = item.store_slug || 'other';
    if (!storeMap[key]) {
      storeMap[key] = { store_slug: item.store_slug, store_name: item.store_name, items: [], subtotal: 0 };
    }
    storeMap[key].items.push(item);
    storeMap[key].subtotal += item.price * item.qty;
  });
  const storeGroups = Object.values(storeMap);

  const handleClear = () => {
    clearCart();
    toast.success('Carro vaciado');
  };

  return (
    <div className="flex flex-col min-h-[calc(100vh-80px)] bg-slate-50 dark:bg-[#050c08]">
      {/* Header */}
      <header className="px-4 py-4 bg-white dark:bg-[#0a150f] border-b border-slate-200 dark:border-slate-800 flex items-center gap-3">
        <button
          onClick={() => navigate(-1)}
          className="size-9 rounded-full flex items-center justify-center text-slate-500 hover:bg-slate-100 dark:hover:bg-white/5 transition-all"
        >
          <span className="material-symbols-outlined">arrow_back</span>
        </button>
        <div className="flex-1">
          <h1 className="font-black text-base leading-tight">Mi Carro</h1>
          <p className="text-[10px] text-slate-400">{items.length} producto{items.length !== 1 ? 's' : ''} · {storeGroups.length} tienda{storeGroups.length !== 1 ? 's' : ''}</p>
        </div>
        <button
          onClick={handleClear}
          className="text-[11px] font-bold text-red-400 hover:text-red-500 transition-colors px-2"
        >
          Vaciar
        </button>
      </header>

      {/* Items por tienda */}
      <div className="flex-1 overflow-y-auto p-4 space-y-5 pb-36">
        {storeGroups.map(group => (
          <section key={group.store_slug}>
            {/* Store header */}
            <div
              className="flex items-center gap-2 px-3 py-2 rounded-xl mb-2"
              style={{ backgroundColor: (STORE_COLORS[group.store_slug] ?? '#64748b') + '18' }}
            >
              <StoreLogo slug={group.store_slug} name={group.store_name} className="size-5" />
              <span
                className="text-sm font-black"
                style={{ color: STORE_COLORS[group.store_slug] ?? '#64748b' }}
              >
                {group.store_name || group.store_slug}
              </span>
              <span className="ml-auto text-xs font-bold text-slate-500 dark:text-slate-400">
                {formatCurrency(group.subtotal)}
              </span>
            </div>

            {/* Products */}
            <div className="space-y-2">
              {group.items.map(item => (
                <div
                  key={String(item.product_id)}
                  className="bg-white dark:bg-[#0a150f] rounded-2xl border border-slate-100 dark:border-slate-800 p-3 flex gap-3 items-center shadow-sm"
                >
                  {/* Image */}
                  <div
                    className="size-14 rounded-xl bg-slate-50 dark:bg-[#14261c] shrink-0 flex items-center justify-center overflow-hidden cursor-pointer"
                    onClick={() => navigate(`/product/${item.product_id}`)}
                  >
                    {item.image_url ? (
                      <img
                        src={item.image_url}
                        alt={item.name}
                        className="size-full object-contain"
                        onError={e => { (e.target as HTMLImageElement).style.opacity = '0.3'; }}
                      />
                    ) : (
                      <span className="material-symbols-outlined text-slate-300 text-2xl">image</span>
                    )}
                  </div>

                  {/* Info */}
                  <div className="flex-1 min-w-0">
                    <p
                      className="text-xs font-bold text-slate-800 dark:text-white leading-tight line-clamp-2 cursor-pointer"
                      onClick={() => navigate(`/product/${item.product_id}`)}
                    >
                      {item.name}
                    </p>
                    {item.brand && (
                      <p className="text-[10px] text-slate-400 mt-0.5">{item.brand}</p>
                    )}
                    <p className="text-[10px] text-slate-400 mt-0.5">
                      {formatCurrency(item.price)} c/u
                    </p>
                  </div>

                  {/* Qty controls */}
                  <div className="flex flex-col items-end gap-1.5 shrink-0">
                    <span className="text-sm font-black text-primary">
                      {formatCurrency(item.price * item.qty)}
                    </span>
                    <div className="flex items-center gap-1">
                      <button
                        onClick={() => updateQty(item.product_id, -1)}
                        className="size-7 rounded-full flex items-center justify-center bg-slate-100 dark:bg-white/10 text-slate-600 dark:text-slate-300 active:scale-90 transition-all font-bold text-lg leading-none"
                      >
                        −
                      </button>
                      <span className="w-5 text-center text-sm font-black text-slate-800 dark:text-white">
                        {item.qty}
                      </span>
                      <button
                        onClick={() => updateQty(item.product_id, 1)}
                        className="size-7 rounded-full flex items-center justify-center active:scale-90 transition-all font-bold text-lg leading-none"
                        style={{ backgroundColor: 'var(--store-primary)', color: 'var(--store-primary-text)' }}
                      >
                        +
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </section>
        ))}
      </div>

      {/* Total footer */}
      <div className="fixed bottom-20 left-0 right-0 z-30 bg-white dark:bg-[#0a150f] border-t border-slate-200 dark:border-slate-800 px-4 pt-3 pb-3">
        {storeGroups.length > 1 && (
          <div className="space-y-0.5 mb-2">
            {storeGroups.map(g => (
              <div key={g.store_slug} className="flex justify-between text-[10px] text-slate-400">
                <span>{g.store_name}</span>
                <span>{formatCurrency(g.subtotal)}</span>
              </div>
            ))}
          </div>
        )}
        <div className="flex items-center justify-between">
          <div>
            <p className="text-[10px] text-slate-400 uppercase font-black tracking-widest">Total estimado</p>
            <p className="text-2xl font-black text-primary">{formatCurrency(total)}</p>
          </div>
          <button
            onClick={() => navigate('/search')}
            className="px-5 py-3 rounded-full bg-primary text-background-dark font-black text-sm active:scale-95 transition-all flex items-center gap-1.5"
          >
            <span className="material-symbols-outlined text-lg">add_shopping_cart</span>
            Agregar más
          </button>
        </div>
      </div>
    </div>
  );
};

export default Cart;

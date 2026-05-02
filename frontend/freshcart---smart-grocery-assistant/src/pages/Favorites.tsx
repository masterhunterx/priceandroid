import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { getFavorites, formatCurrency } from '../lib/api';
import { Product } from '../types';
import StoreLogo from '../components/StoreLogo';
import { useAuth } from '../context/AuthContext';

const PAGE_SIZE = 20;

const Favorites: React.FC = () => {
  const navigate = useNavigate();
  const { isGuest } = useAuth();

  if (isGuest) return <GuestCTA title="Tus favoritos" description="Guarda productos para compararlos luego y recibir alertas de precio." navigate={navigate} />;

  const [favorites, setFavorites] = useState<Product[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const [page, setPage] = useState(0);

  async function loadFavorites(pageNum: number, append = false, cancelled?: { value: boolean }) {
    try {
      const data = await getFavorites(PAGE_SIZE, pageNum * PAGE_SIZE);
      if (cancelled?.value) return;
      setFavorites(prev => append ? [...prev, ...data] : data);
      setHasMore(data.length === PAGE_SIZE);
    } catch (error) {
      if (cancelled?.value) return;
      console.error('Error loading favorites:', error);
    } finally {
      if (!cancelled?.value) {
        if (!append) setLoading(false);
        setLoadingMore(false);
      }
    }
  }

  useEffect(() => {
    const cancelled = { value: false };
    loadFavorites(0, false, cancelled);
    return () => { cancelled.value = true; };
  }, []);

  const handleLoadMore = () => {
    const nextPage = page + 1;
    setPage(nextPage);
    setLoadingMore(true);
    loadFavorites(nextPage, true);
  };

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen animate-pulse">
        <div className="h-8 w-48 bg-slate-200 dark:bg-slate-800 rounded-lg"></div>
      </div>
    );
  }

  return (
    <div className="flex flex-col min-h-screen pb-32">
      <header className="sticky top-0 z-50 bg-background-light/80 dark:bg-background-dark/80 backdrop-blur-md p-4">
        <h1 className="text-2xl font-black tracking-tight text-slate-900 dark:text-white">Mi Seguimiento</h1>
        <p className="text-sm text-slate-500 dark:text-[#9db9a8]">Productos monitoreados por KAIROS</p>
      </header>

      <main className="flex-1 px-4 py-4">
        {favorites.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 text-center">
            <span className="material-symbols-outlined text-6xl text-slate-300 mb-4">analytics</span>
            <h3 className="text-lg font-bold text-slate-400">No tienes productos en seguimiento</h3>
            <p className="text-sm text-slate-500 mt-2 px-10">Dale al corazón en cualquier producto para que KAIROS empiece a monitorearlo.</p>
            <button 
              onClick={() => navigate('/')}
              className="mt-6 bg-primary/10 text-primary font-bold px-6 py-2 rounded-full border border-primary/20"
            >
              Explorar Productos
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-4">
            {favorites.map((product) => (
              <div
                key={product.id}
                onClick={() => navigate(`/product/${product.id}`)}
                className="group relative overflow-hidden bg-white dark:bg-slate-800/40 border border-slate-200 dark:border-slate-700/50 rounded-2xl p-4 flex items-center gap-4 transition-all hover:border-primary/30 active:scale-[0.98]"
              >
                {/* Score Badge */}
                {product.price_insight && (
                  <div className={`absolute top-0 right-0 px-3 py-1 rounded-bl-xl text-[10px] font-black uppercase tracking-tighter ${
                    product.price_insight.deal_score >= 70 ? 'bg-primary text-background-dark' : 'bg-slate-200 dark:bg-slate-700 text-slate-500'
                  }`}>
                    {product.price_insight.deal_score} IQ
                  </div>
                )}

                <div className="size-20 bg-white rounded-xl p-2 flex items-center justify-center shrink-0 shadow-sm border border-slate-100">
                  <img src={product.image_url} alt={product.name} className="max-w-full max-h-full object-contain" />
                </div>

                <div className="flex-1 min-w-0">
                  <h4 className="font-bold text-slate-900 dark:text-white truncate pr-16">{product.name}</h4>
                  <p className="text-[10px] text-slate-500 font-medium uppercase mt-0.5">{product.brand}</p>
                  
                  <div className="flex items-center gap-3 mt-3">
                    <div className="flex flex-col">
                      <span className="text-[9px] text-slate-400 uppercase font-bold">Mejor Precio</span>
                      <span className="text-sm font-black text-primary">{formatCurrency(product.price_insight?.min_price_all_time || 0)}</span>
                    </div>
                    {product.price_insight?.price_trend === 'falling' && (
                      <div className="flex items-center gap-1 text-[#2bee79] animate-pulse">
                        <span className="material-symbols-outlined text-[10px]">trending_down</span>
                        <span className="text-[9px] font-bold uppercase">Baja</span>
                      </div>
                    )}
                  </div>
                </div>

                <button className="material-symbols-outlined text-slate-300 group-hover:text-primary transition-colors">
                  chevron_right
                </button>
              </div>
            ))}
            {hasMore && (
              <button
                onClick={handleLoadMore}
                disabled={loadingMore}
                className="w-full py-3 rounded-2xl border border-primary/30 text-primary font-bold text-sm hover:bg-primary/5 active:scale-95 transition-all disabled:opacity-50"
              >
                {loadingMore ? 'Cargando...' : 'Cargar más'}
              </button>
            )}
          </div>
        )}
      </main>
    </div>
  );
};

const GuestCTA: React.FC<{ title: string; description: string; navigate: (path: string) => void }> = ({ title, description, navigate }) => (
  <div className="min-h-screen bg-background-light dark:bg-background-dark flex flex-col items-center justify-center px-6 text-center">
    <div className="w-16 h-16 rounded-2xl bg-primary/10 flex items-center justify-center mb-4">
      <span className="material-symbols-outlined text-primary text-[32px]">favorite</span>
    </div>
    <h2 className="text-xl font-bold text-slate-900 dark:text-white mb-2">{title}</h2>
    <p className="text-slate-500 dark:text-slate-400 text-sm mb-6 max-w-xs">{description}</p>
    <button
      onClick={() => navigate('/login')}
      className="w-full max-w-xs h-12 flex items-center justify-center gap-3 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-600 rounded-2xl font-semibold text-slate-700 dark:text-slate-200 text-sm shadow-sm hover:bg-slate-50 active:scale-95 transition-all"
    >
      <svg width="18" height="18" viewBox="0 0 48 48" xmlns="http://www.w3.org/2000/svg">
        <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/>
        <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/>
        <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"/>
        <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/>
        <path fill="none" d="M0 0h48v48H0z"/>
      </svg>
      Conectar con Google
    </button>
    <p className="text-xs text-slate-400 mt-3">Tu carrito y búsquedas se conservan</p>
  </div>
);

export default Favorites;

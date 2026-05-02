import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { getFavorites, formatCurrency } from '../lib/api';
import { Product } from '../types';
import StoreLogo from '../components/StoreLogo';
import { useAuth } from '../context/AuthContext';
import GuestCTA from '../components/GuestCTA';

const PAGE_SIZE = 20;

const Favorites: React.FC = () => {
  const navigate = useNavigate();
  const { isGuest } = useAuth();

  if (isGuest) return <GuestCTA title="Tus favoritos" icon="favorite" description="Guarda productos para compararlos luego y recibir alertas de precio." buttonText="Conectar con Google" onButton={() => navigate('/login')} />;

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

export default Favorites;

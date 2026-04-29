import React, { useEffect, useState, useCallback, useRef } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { BarChart, Bar, ResponsiveContainer, Cell, XAxis, YAxis, Tooltip } from 'recharts';
import { getProductDetails, formatCurrency, toggleFavorite, syncProduct, readPriceSnapshots, writePriceSnapshots } from '../lib/api';
import { Product, PricePoint } from '../types';
import StoreLogo from '../components/StoreLogo';
import { toast } from 'react-hot-toast';
import { useLocation } from '../context/LocationContext';
import { useCart } from '../context/CartContext';

/** Genera URL de búsqueda abreviada (3 palabras clave) para el botón "Buscar en tienda" */
function buildStoreSearchUrl(storeSlug: string, productName: string): string {
  let clean = productName.replace(/\b\d+[\d.,]*\s*(kg|g|ml|l|lt|un|cc|oz|pack)\b/gi, '');
  clean = clean.replace(/\b(sin|con|extra|ultra|super|light|zero|plus|mini|maxi|especial|original|clásico|clasico|natural|premium)\b/gi, '');
  const words = clean.replace(/\s+/g, ' ').trim().split(' ').filter(w => w.length > 1).slice(0, 3).join(' ')
    || productName.split(' ').slice(0, 2).join(' ');
  const q = encodeURIComponent(words);
  const slug = storeSlug.toLowerCase().replace(/[-_]/g, '');
  switch (slug) {
    case 'jumbo':        return `https://www.jumbo.cl/buscar?query=${q}`;
    case 'santaisabel':  return `https://www.santaisabel.cl/busqueda?ft=${q}`;
    case 'lider':        return `https://www.lider.cl/supermercado/search?currentPage=0&pageSize=40&query=${q}`;
    case 'unimarc':      return `https://www.unimarc.cl/busqueda?q=${q}`;
    default:             return `https://www.google.com/search?q=${encodeURIComponent(words + ' supermercado')}`;
  }
}

// buildVtexFullSearchUrl eliminada: VTEX interpreta nombres completos como slugs de producto
// y redirige a páginas que pueden estar descontinuadas → 404. Se usa buildStoreSearchUrl para todo.


const ProductDetails: React.FC = () => {
  const navigate = useNavigate();
  const { id } = useParams();
  const { getBranchContext } = useLocation();
  const { addItem, removeItem, isInCart } = useCart();
  const [product, setProduct] = useState<Product | null>(null);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [substitutes, setSubstitutes] = useState<Product[]>([]);
  const [isFavorite, setIsFavorite] = useState(false);
  const [selectedPricePoint, setSelectedPricePoint] = useState<PricePoint | null>(null);
  const [pullRefreshing, setPullRefreshing] = useState(false);
  const [pullY, setPullY] = useState(0);
  const touchStartY = useRef(0);
  const PULL_THRESHOLD = 70;

  const loadProduct = async (silent = false, cancelled?: { value: boolean }) => {
    if (!id) return;
    const numericId = parseInt(id, 10);
    if (isNaN(numericId)) return;
    if (!silent) setLoading(true);
    try {
      const branchContext = getBranchContext();
      const data = await getProductDetails(numericId, branchContext);
      if (cancelled?.value) return;
      setProduct(data);
      setIsFavorite(data.is_favorite ?? false);
      const bestPoint = data.prices?.find(p => p.in_stock && p.price === data.best_price) ?? data.prices?.find(p => p.in_stock) ?? null;
      setSelectedPricePoint(prev => prev ?? bestPoint);
      // Guardar snapshot de precio para detección de "Bajó de precio" en Home
      if (data.best_price != null) {
        const snaps = readPriceSnapshots();
        snaps[String(data.id)] = {
          price: data.best_price,
          storeSlug: data.best_store_slug ?? '',
          storeName: data.best_store ?? '',
          name: data.name,
          imageUrl: data.image_url,
          savedAt: Date.now(),
        };
        writePriceSnapshots(snaps);
      }
    } catch (error) {
      console.error('Error loading product details:', error);
    } finally {
      if (!cancelled?.value && !silent) setLoading(false);
    }
  };

  useEffect(() => {
    const cancelled = { value: false };
    loadProduct(false, cancelled);
    return () => { cancelled.value = true; };
  }, [id]);

  useEffect(() => {
    if (!product?.category) return;
    let cancelled = false;
    import('../lib/api').then(({ searchProducts }) =>
      searchProducts('', product.category, 1, 4, 'price_asc')
    ).then(results => {
      if (!cancelled)
        setSubstitutes(results.results.filter(p => p.id.toString() !== id?.toString()));
    }).catch(() => {});
    return () => { cancelled = true; };
  }, [product?.id, product?.category]);

  const handleSync = async () => {
    if (!id || !product) return;
    setSyncing(true);
    try {
      const loadingToast = toast.loading('Sincronizando precios en vivo...');
      const result = await syncProduct(id);
      await loadProduct(true);
      toast.dismiss(loadingToast);
      if (result?.updated_count > 0) {
        toast.success('Precios actualizados', { style: { borderRadius: '10px', background: '#333', color: '#fff' } });
      } else {
        toast('No se pudo verificar ahora — la tienda bloqueó la solicitud. Intenta en unos minutos.', { icon: '⚠️', duration: 4000 });
      }
    } catch (error) {
      console.error('Error syncing product:', error);
      toast.error('Error al sincronizar precios');
    } finally {
      setSyncing(false);
    }
  };

  const getRelativeTime = (isoString: string) => {
    if (!isoString) return 'Pendiente';
    const date = new Date(isoString);
    const now = new Date();
    const diffInMinutes = Math.floor((now.getTime() - date.getTime()) / 60000);
    
    if (diffInMinutes < 1) return 'Hace un momento';
    if (diffInMinutes < 60) return `Hace ${diffInMinutes} min`;
    const diffInHours = Math.floor(diffInMinutes / 60);
    if (diffInHours < 24) return `Hace ${diffInHours}h`;
    return date.toLocaleDateString();
  };

  const handleToggleFavorite = () => {
    if (!product) return;
    setIsFavorite(prev => !prev);
    toggleFavorite(product.id).catch(() => setIsFavorite(prev => !prev));
  };

  const handleShare = async () => {
    if (!product) return;
    const shareData = {
      title: product.name,
      text: `¡Mira esta oferta en FreshCart! ${product.name} a solo ${product.best_price != null ? formatCurrency(product.best_price) : 'precio no disponible'}`,
      url: window.location.href,
    };

    try {
      if (navigator.share) {
        await navigator.share(shareData);
      } else {
        await navigator.clipboard.writeText(window.location.href);
        toast.success('Enlace copiado al portapapeles');
      }
    } catch (err) {
      console.error('Error sharing:', err);
    }
  };

  const handleAddToCart = () => {
    if (!product) return;
    if (isInCart(product.id)) {
      removeItem(product.id);
      toast('Eliminado del carro', { icon: '🗑️', style: { borderRadius: '10px', background: '#333', color: '#fff' } });
    } else {
      const pp = selectedPricePoint ?? product.prices?.find(p => p.in_stock && p.price === product.best_price);
      addItem({
        product_id: product.id,
        name: product.name,
        brand: product.brand || '',
        image_url: product.image_url || '',
        price: pp?.price || product.best_price || 0,
        store_slug: pp?.store_slug || '',
        store_name: pp?.store_name || product.best_store || '',
      });
      toast.success(`Agregado al carro — ${pp?.store_name || product.best_store}`, { icon: '🛒', style: { borderRadius: '10px', background: '#333', color: '#fff' } });
    }
  };

  const handleTouchStart = (e: React.TouchEvent) => {
    if (window.scrollY === 0) touchStartY.current = e.touches[0].clientY;
  };
  const handleTouchMove = (e: React.TouchEvent) => {
    if (window.scrollY > 0 || pullRefreshing) return;
    const delta = e.touches[0].clientY - touchStartY.current;
    if (delta > 0) setPullY(Math.min(delta * 0.4, PULL_THRESHOLD));
  };
  const handleTouchEnd = async () => {
    if (pullY >= PULL_THRESHOLD && !pullRefreshing) {
      setPullRefreshing(true);
      setSelectedPricePoint(null);
      await loadProduct();
      setPullRefreshing(false);
    }
    setPullY(0);
  };

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen bg-background-light dark:bg-background-dark">
        <div className="size-20 border-4 border-primary border-t-transparent rounded-full animate-spin mb-8"></div>
        <div className="w-64 h-64 bg-slate-200 dark:bg-slate-800 rounded-2xl mb-8 animate-pulse shadow-xl"></div>
        <h2 className="text-xl font-bold text-slate-900 dark:text-white mb-2">Conectando con {product?.best_store || 'el supermercado'}</h2>
        <p className="text-slate-500 dark:text-slate-400 font-medium animate-pulse text-center px-10">
          Estamos verificando el stock y las ofertas exclusivas para asegurar el máximo ahorro.
        </p>
      </div>
    );
  }

  if (!product) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-center">
          <h2 className="text-xl font-bold">Producto no encontrado</h2>
          <button onClick={() => navigate('/')} className="text-primary mt-4 font-bold">Volver al Inicio</button>
        </div>
      </div>
    );
  }

  const chartData = (product.price_history || []).map((ph, idx) => ({
    name: idx.toString(),
    price: ph.price,
    date: new Date(ph.scraped_at).toLocaleDateString('es-CL'),
  }));

  return (
    <div
      className="flex flex-col pb-32"
      onTouchStart={handleTouchStart}
      onTouchMove={handleTouchMove}
      onTouchEnd={handleTouchEnd}
      style={{ transform: pullY > 0 ? `translateY(${pullY}px)` : undefined, transition: pullY === 0 ? 'transform 0.3s ease' : undefined }}
    >
      {/* Pull-to-refresh indicator */}
      {pullY > 0 && (
        <div className="fixed top-0 left-0 right-0 z-50 flex justify-center" style={{ transform: `translateY(${pullY - 40}px)` }}>
          <div className={`size-9 rounded-full bg-primary flex items-center justify-center shadow-lg transition-transform ${pullY >= PULL_THRESHOLD ? 'scale-110' : 'scale-90'}`}>
            <span className={`material-symbols-outlined text-background-dark text-lg ${pullRefreshing ? 'animate-spin' : ''}`}>refresh</span>
          </div>
        </div>
      )}
      <header className="sticky top-0 z-50 bg-background-light/80 dark:bg-background-dark/80 backdrop-blur-md">
        <div className="flex items-center p-4 pb-2 justify-between">
          <div
            onClick={() => navigate(-1)}
            className="flex size-12 shrink-0 items-center cursor-pointer"
          >
            <span className="material-symbols-outlined text-2xl">arrow_back_ios</span>
          </div>
          <h2 className="text-lg font-bold flex-1 text-center">Detalle del Producto</h2>
          <div className="flex w-12 items-center justify-end">
            <button
              onClick={handleToggleFavorite}
              className={`flex size-10 items-center justify-center rounded-full transition-all active:scale-90 ${
                isFavorite
                ? 'bg-red-500/10 text-red-500'
                : 'bg-slate-100 dark:bg-slate-800 text-slate-400'
              }`}
            >
              <span className="material-symbols-outlined text-2xl" style={{ fontVariationSettings: isFavorite ? "'FILL' 1" : "'FILL' 0" }}>
                favorite
              </span>
            </button>
            <button 
              onClick={handleShare}
              className="flex size-10 items-center justify-center rounded-full bg-slate-100 dark:bg-slate-800 text-slate-400 active:scale-90 ml-2"
            >
              <span className="material-symbols-outlined text-2xl">share</span>
            </button>
          </div>
        </div>
      </header>

      <main className="pb-44">
        {/* Image */}
        <div className="px-4 py-2">
          <div className="w-full bg-white dark:bg-slate-800 rounded-xl overflow-hidden min-h-[320px] shadow-lg flex items-center justify-center p-8">
            <img
              src={product.image_url}
              alt={product.name}
              className="max-w-full max-h-[280px] object-contain"
            />
          </div>
        </div>

        {/* Info */}
        <div className="px-4 pt-4">
          <div className="flex justify-between items-start">
            <div>
              <h2 className="text-2xl font-bold leading-tight tracking-tight text-slate-900 dark:text-white">{product.name}</h2>
              <p className="text-slate-400 text-xs mt-1">{product.weight_value} {product.weight_unit} • {product.category}</p>
              
                <div className="flex items-center gap-2 mt-4">
                  {(() => {
                    const latestSync = product.prices?.reduce((latest, p) => {
                      if (!p.last_sync) return latest;
                      const current = new Date(p.last_sync).getTime();
                      return current > latest ? current : latest;
                    }, 0);
                    
                    const isValidDate = latestSync > 0;
                    const isVeryFresh = isValidDate && (new Date().getTime() - latestSync) < 600000; // 10 min
                    
                    return (
                      <div className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full border ${isVeryFresh ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-500' : 'bg-amber-500/10 border-amber-500/20 text-amber-500'}`}>
                         <span className="material-symbols-outlined text-[14px]">{isVeryFresh ? 'verified' : 'history'}</span>
                         <span className="text-[10px] font-bold uppercase tracking-wider">
                           {!isValidDate ? 'Sinc: Pendiente' : isVeryFresh ? 'Actualizado ahora' : `Verificado ${getRelativeTime(new Date(latestSync).toISOString())}`}
                         </span>
                      </div>
                    );
                  })()}
                </div>
            </div>
            <div className="flex flex-col items-end">
              <div className="flex items-center gap-1 bg-primary/20 text-primary px-2 py-1 rounded-lg">
                <span className="material-symbols-outlined text-sm fill-1">verified</span>
                <span className="text-sm font-bold">Match</span>
              </div>
            </div>
          </div>
        </div>

        {/* Price Chart */}
        {(product.price_history && product.price_history.length > 1) && (
          <div className="px-4 py-6">
            <div className="bg-slate-100 dark:bg-slate-800/50 rounded-xl p-4 border border-slate-200 dark:border-slate-700">
              <div className="flex justify-between items-center mb-4">
                <h3 className="font-bold text-xs uppercase tracking-wider text-slate-500 dark:text-slate-400">Historial de Precios</h3>
                <span className="text-primary text-xs font-bold flex items-center gap-1">
                  <span className="material-symbols-outlined text-xs">trending_down</span>
                  Seguimiento de oferta
                </span>
              </div>
              <div className="h-32 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={chartData}>
                    <Bar dataKey="price" radius={[4, 4, 0, 0]}>
                      {chartData.map((entry, index) => (
                        <Cell
                          key={`cell-${index}`}
                          fill={index === chartData.length - 1 ? '#2bee79' : '#2bee7960'}
                        />
                      ))}
                    </Bar>
                    <Tooltip 
                      contentStyle={{ backgroundColor: '#1a2e22', border: 'none', borderRadius: '8px', color: '#fff' }}
                      labelFormatter={() => ''}
                      formatter={(value: number) => [formatCurrency(value), 'Precio']}
                    />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>
        )}
        {/* AI Intelligence Layer - Insights & Prediction */}
        {product.price_insight && (
          <div className="px-4 py-4 space-y-4">
            <div className="relative overflow-hidden bg-gradient-to-br from-[#1a2e22] to-[#122319] border border-primary/20 rounded-2xl p-5 shadow-2xl shadow-primary/5">
              {/* Prediction Banner */}
              <div className="flex items-center gap-3 mb-6 pb-4 border-b border-white/5">
                <div className="size-10 rounded-full bg-primary/20 flex items-center justify-center animate-pulse">
                   <span className="material-symbols-outlined text-primary">psychology</span>
                </div>
                <div>
                   <h4 className="text-[10px] font-black uppercase tracking-tighter text-primary">Predicción de KAIROS</h4>
                   <p className="text-white text-sm font-bold">
                     {product.price_insight.price_trend === 'falling' 
                       ? '🚨 ¡Espera! El precio está bajando.' 
                       : product.price_insight.deal_score >= 80 
                       ? '✅ ¡Compra ahora! No bajará más pronto.' 
                       : '⚖️ Precio estable, puedes comprar hoy.'}
                   </p>
                </div>
              </div>

              <div className="flex items-center justify-between relative z-10">
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="bg-primary/20 text-primary text-[10px] font-bold px-2 py-0.5 rounded-full uppercase tracking-tighter">Dream System Insight</span>
                  </div>
                  <h3 className="text-xl font-bold text-white leading-tight">
                    {product.price_insight.deal_score >= 80 ? '¡Oferta Excepcional!' : 
                     product.price_insight.deal_score >= 50 ? 'Buen Momento para Comprar' : 
                     'Precio Habitual'}
                  </h3>
                  <div className="flex items-center gap-4 mt-3">
                    <div className="flex flex-col">
                      <span className="text-[10px] text-slate-500 uppercase font-bold">Tendencia</span>
                      <div className="flex items-center gap-1">
                        <span className={`material-symbols-outlined text-sm ${
                          product.price_insight.price_trend === 'falling' ? 'text-primary' : 
                          product.price_insight.price_trend === 'rising' ? 'text-red-400' : 'text-slate-400'
                        }`}>
                          {product.price_insight.price_trend === 'falling' ? 'trending_down' : 
                           product.price_insight.price_trend === 'rising' ? 'trending_up' : 'trending_flat'}
                        </span>
                        <span className="text-sm font-bold text-slate-300 capitalize">{
                          product.price_insight.price_trend === 'falling' ? 'Bajando' : 
                          product.price_insight.price_trend === 'rising' ? 'Subiendo' : 'Estable'
                        }</span>
                      </div>
                    </div>
                    <div className="h-8 w-px bg-slate-800"></div>
                    <div className="flex flex-col">
                      <span className="text-[10px] text-slate-500 uppercase font-bold">Promedio</span>
                      <span className="text-sm font-bold text-slate-200">{formatCurrency(product.price_insight.avg_price)}</span>
                    </div>
                  </div>
                </div>
                
                {/* Deal Score Radial */}
                <div className="flex flex-col items-center justify-center size-20 rounded-full border-4 border-slate-800 relative">
                  <svg className="size-full -rotate-90">
                    <circle
                      cx="40" cy="40" r="34"
                      fill="transparent"
                      stroke={product.price_insight.deal_score >= 70 ? '#2bee79' : '#f59e0b'}
                      strokeWidth="4"
                      strokeDasharray={2 * Math.PI * 34}
                      strokeDashoffset={2 * Math.PI * 34 * (1 - product.price_insight.deal_score / 100)}
                      strokeLinecap="round"
                    />
                  </svg>
                  <div className="absolute inset-0 flex flex-col items-center justify-center">
                    <span className="text-xl font-black text-white leading-none">{product.price_insight.deal_score}</span>
                    <span className="text-[8px] font-bold text-slate-500 uppercase">Score</span>
                  </div>
                </div>
              </div>
            </div>

            {/* Smart Substitutes */}
            {substitutes.length > 0 && (
              <div className="bg-slate-50 dark:bg-white/5 border border-slate-100 dark:border-white/5 rounded-2xl p-5">
                 <h4 className="text-[10px] font-black uppercase tracking-widest text-slate-500 mb-4 flex items-center gap-2">
                   <span className="material-symbols-outlined text-[16px] text-primary">swap_horiz</span>
                   Sustitutos de Ahorro
                 </h4>
                 <div className="flex gap-3 overflow-x-scroll no-scrollbar -mx-2 px-2">
                   {substitutes.map(sub => (
                     <div 
                      key={sub.id} 
                      onClick={() => navigate(`/product/${sub.id}`)}
                      className="flex-none w-32 bg-white dark:bg-slate-800 p-3 rounded-xl shadow-sm border border-slate-100 dark:border-slate-700 cursor-pointer active:scale-95 transition-all"
                     >
                        <img src={sub.image_url} alt={sub.name} className="size-16 object-contain mb-2 mx-auto" />
                        <h5 className="text-[10px] font-bold text-slate-900 dark:text-white truncate">{sub.name}</h5>
                        <p className="text-[12px] font-black text-primary mt-1">{formatCurrency(sub.best_price)}</p>
                        {product.best_price && sub.best_price && sub.best_price < product.best_price && (
                          <div className="mt-1 text-[8px] font-bold text-emerald-500 bg-emerald-500/10 px-1 py-0.5 rounded inline-block">
                             AHORRA {formatCurrency(product.best_price - (sub.best_price || 0))}
                          </div>
                        )}
                     </div>
                   ))}
                 </div>
              </div>
            )}
          </div>
        )}

        {/* Compare Stores */}
        <div className="px-4 mt-6">
          <div className="flex justify-between items-end mb-4">
            <h3 className="text-lg font-bold leading-tight tracking-tight">Comparar en Tiendas</h3>
            <button 
              onClick={handleSync}
              disabled={syncing}
              className={`flex items-center gap-1 text-[10px] font-bold uppercase tracking-widest text-primary hover:opacity-80 transition-all ${syncing ? 'animate-pulse' : ''}`}
            >
              <span className={`material-symbols-outlined text-sm ${syncing ? 'animate-spin' : ''}`}>sync</span>
              {syncing ? 'Verificando...' : 'Verificar Ahora'}
            </button>
          </div>
          <div className="space-y-3">
            {(product.prices ?? [])
              .sort((a, b) => {
                const stockA = a.in_stock ? 0 : 1;
                const stockB = b.in_stock ? 0 : 1;
                if (stockA !== stockB) return stockA - stockB;
                return (a.price || Infinity) - (b.price || Infinity);
              })
              .map((pricePoint) => {
                const isBest = product.best_price === pricePoint.price && product.best_store === pricePoint.store_name;
                const isSelected = selectedPricePoint?.store_id === pricePoint.store_id;

                return (
                  <div
                    key={`store-${pricePoint.store_id}-p-${pricePoint.price}`}
                    onClick={() => pricePoint.in_stock && setSelectedPricePoint(pricePoint)}
                    className={`relative overflow-hidden rounded-xl p-4 border-2 transition-all duration-300 ${!pricePoint.in_stock ? 'opacity-60' : 'cursor-pointer active:scale-[0.98]'} ${isSelected && pricePoint.in_stock ? 'bg-primary/10 dark:bg-primary/5 border-primary shadow-lg shadow-primary/5' : 'bg-slate-100 dark:bg-slate-800/40 border-slate-200 dark:border-slate-700'}`}
                  >
                    {isBest && pricePoint.in_stock && (
                      <div className="absolute top-0 right-0 bg-primary text-background-dark text-[10px] font-bold px-3 py-1 rounded-bl-lg uppercase">
                        Mejor Precio
                      </div>
                    )}
                    {isSelected && pricePoint.in_stock && (
                      <div className="absolute top-2 left-2 size-5 rounded-full bg-primary flex items-center justify-center">
                        <span className="material-symbols-outlined text-background-dark" style={{ fontSize: '14px' }}>check</span>
                      </div>
                    )}
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <div className="size-10 flex items-center justify-center">
                          <StoreLogo slug={pricePoint.store_slug} name={pricePoint.store_name} className="size-8 shadow-sm" />
                        </div>
                        <div>
                          <p className="font-bold text-base text-slate-900 dark:text-white">{pricePoint.store_name}</p>
                          <div className="flex flex-wrap gap-1.5 mt-1">
                            {pricePoint.in_stock ? (
                              <span className="bg-emerald-100 text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-400 text-[10px] font-bold px-1.5 py-0.5 rounded">En Stock</span>
                            ) : (
                              <span className="bg-red-100 text-red-700 dark:bg-red-500/20 dark:text-red-400 text-[10px] font-bold px-1.5 py-0.5 rounded">Sin Stock</span>
                            )}
                            {pricePoint.promo_description && (
                              <span className={`flex items-center gap-0.5 text-[10px] font-bold px-1.5 py-0.5 rounded ${
                                pricePoint.offer_type === 'card' ? 'bg-amber-100 text-amber-700 dark:bg-amber-500/20 dark:text-amber-400' :
                                pricePoint.offer_type === 'internet' ? 'bg-indigo-100 text-indigo-700 dark:bg-indigo-500/20 dark:text-indigo-400' :
                                pricePoint.offer_type === 'app' ? 'bg-purple-100 text-purple-700 dark:bg-purple-500/20 dark:text-purple-400' :
                                'bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-300'
                              }`}>
                                <span className="material-symbols-outlined" style={{fontSize:'11px'}}>
                                  {pricePoint.offer_type === 'card' ? 'credit_card' :
                                   pricePoint.offer_type === 'internet' ? 'public' :
                                   pricePoint.offer_type === 'app' ? 'smartphone' : 'local_offer'}
                                </span>
                                {pricePoint.card_label || pricePoint.promo_description}
                              </span>
                            )}
                            {pricePoint.is_stale ? (
                              <span className="text-[9px] text-amber-500 font-bold flex items-center gap-0.5">
                                <span className="material-symbols-outlined text-[10px]">warning</span>
                                {pricePoint.store_slug === 'lider' ? 'Posible bloqueo PerimeterX' : 'Dato desactualizado +6h'}
                              </span>
                            ) : (
                              <span className="text-[9px] text-slate-400 font-medium">Sinc: {getRelativeTime(pricePoint.last_sync)}</span>
                            )}
                          </div>
                        </div>
                      </div>
                      <div className="text-right flex flex-col items-end gap-1">
                        {pricePoint.in_stock ? (
                          <>
                            {/* Multipack / Unit Price (The absolute best) */}
                            {pricePoint.unit_price ? (
                              <>
                                <p className={`text-xl font-black ${isBest ? 'text-primary' : 'text-slate-900 dark:text-white'}`}>
                                  {formatCurrency(pricePoint.unit_price)}
                                </p>
                                <p className="text-[9px] text-emerald-500 font-bold uppercase tracking-tighter bg-emerald-500/10 px-1 rounded">Precio por unidad</p>
                              </>
                            ) : null}

                            {/* Main Display Price (could be Club or Internet) */}
                            {!pricePoint.unit_price && pricePoint.price != null && (
                               <p className={`text-xl font-bold ${isBest ? 'text-primary' : 'text-slate-900 dark:text-white'}`}>
                                 {formatCurrency(pricePoint.price)}
                               </p>
                            )}

                            {/* Tiered breakdown */}
                            <div className="flex flex-col items-end mt-1">
                               {/* Club Price label if current price is club, otherwise secondary */}
                               {pricePoint.club_price && (
                                 <p className="text-[10px] text-amber-500 font-bold flex items-center gap-0.5">
                                   <span className="material-symbols-outlined text-[11px]">credit_card</span>
                                   Socio: {formatCurrency(pricePoint.club_price)}
                                 </p>
                               )}

                               {/* Always show the normal/list price if it's different */}
                               {(pricePoint.list_price && pricePoint.list_price > (pricePoint.unit_price || pricePoint.price || 0)) && (
                                 <p className="text-[10px] text-slate-400 line-through">Normal: {formatCurrency(pricePoint.list_price)}</p>
                               )}

                               {/* Normalized unit price ($/100g or $/100ml) */}
                               {pricePoint.price_per_unit != null && pricePoint.unit_label && (
                                 <p className="text-[9px] text-sky-400 font-bold mt-0.5 bg-sky-500/10 px-1.5 py-0.5 rounded">
                                   ~{formatCurrency(pricePoint.price_per_unit)}/{pricePoint.unit_label.replace('$/', '')}
                                 </p>
                               )}
                            </div>
                          </>
                        ) : (
                          <p className="text-sm font-bold text-slate-400 line-through">---</p>
                        )}
                      </div>
                    </div>
                    {pricePoint.in_stock && (() => {
                        const directUrl = pricePoint.product_url
                          ? (pricePoint.product_url.startsWith('http') ? pricePoint.product_url : `https://${pricePoint.product_url}`)
                          : null;
                        return (
                          <div className="mt-3 flex gap-2">
                            <a
                              href={buildStoreSearchUrl(pricePoint.store_slug, product.name)}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="flex-1 flex items-center justify-center gap-1 text-[10px] text-primary font-bold uppercase tracking-widest border border-primary/30 rounded-lg py-1.5 hover:bg-primary/10 transition-colors"
                            >
                              <span className="material-symbols-outlined text-[13px]">search</span>
                              Buscar en tienda
                            </a>
                            {directUrl && (
                              <a
                                href={directUrl}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="flex items-center justify-center gap-1 px-2.5 text-[10px] text-slate-400 font-bold border border-slate-200 dark:border-slate-700 rounded-lg py-1.5 hover:border-primary/30 transition-colors"
                              >
                                <span className="material-symbols-outlined text-[13px]">open_in_new</span>
                                Ver producto
                              </a>
                            )}
                          </div>
                        );
                      })()}
                  </div>
                );
              })}
          </div>
        </div>
      </main>

      {/* Sticky Footer — bottom-20 para quedar sobre el BottomNav (h-20) */}
      {(() => {
        const pp = selectedPricePoint;
        const hasStock = pp ? pp.in_stock : product.best_price != null;
        const displayPrice = pp?.price ?? product.best_price;
        const displayStore = pp?.store_name ?? product.best_store;
        return (
          <div className="fixed bottom-20 left-0 right-0 z-30 p-4 bg-white/90 dark:bg-[#102217]/90 backdrop-blur-xl border-t border-slate-200 dark:border-slate-800">
            <div className="max-w-md mx-auto flex items-center gap-4">
              <div className="flex flex-col">
                <span className="text-slate-400 text-[10px] font-bold uppercase tracking-wider">
                  {hasStock ? (displayStore || 'Mejor Precio') : 'Stock'}
                </span>
                <span className={`text-2xl font-bold ${hasStock ? 'text-primary' : 'text-red-500'}`}>
                  {hasStock ? formatCurrency(displayPrice) : 'Sin Stock'}
                </span>
              </div>
              <button
                onClick={handleAddToCart}
                disabled={!hasStock}
                className={`flex-1 font-bold py-4 rounded-xl flex items-center justify-center gap-2 shadow-lg transition-all ${
                  !hasStock
                    ? 'bg-slate-200 dark:bg-slate-700 text-slate-400 cursor-not-allowed'
                    : isInCart(product.id)
                    ? 'bg-red-500 text-white shadow-red-500/20 active:scale-95'
                    : 'bg-primary text-background-dark shadow-primary/20 active:scale-95'
                }`}
              >
                <span className="material-symbols-outlined">
                  {!hasStock ? 'inventory_2' : isInCart(product.id) ? 'remove_shopping_cart' : 'add_shopping_cart'}
                </span>
                {!hasStock ? 'No disponible' : isInCart(product.id) ? 'Quitar del carro' : 'Agregar al carro'}
              </button>
            </div>
          </div>
        );
      })()}
    </div>
  );
};

export default ProductDetails;

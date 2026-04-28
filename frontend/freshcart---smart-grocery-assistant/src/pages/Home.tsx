import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { getDeals, getCategories, formatCurrency, getNotifications, getHistoricLows, refreshNotifications, searchProducts, readPriceSnapshots, writePriceSnapshots, PriceSnapshotMap } from '../lib/api';
import { Deal, Category, Notification, Branch, Product, HistoricLow } from '../types';

interface PriceDropItem {
  productId: number;
  name: string;
  imageUrl: string;
  currentPrice: number;
  previousPrice: number;
  storeSlug: string;
  storeName: string;
  dropAmount: number;
  dropPercent: number;
}
import { useAuth } from '../context/AuthContext';
import HomeHeader from '../components/HomeHeader';

import StoreLogo from '../components/StoreLogo';
import { useLocation } from '../context/LocationContext';
import { useTheme } from '../context/ThemeContext';
import LocationSelector from '../components/LocationSelector';

const STORE_META: Record<string, { name: string; color: string }> = {
  jumbo:        { name: 'Jumbo',        color: '#00a650' },
  santa_isabel: { name: 'Santa Isabel', color: '#e30613' },
  lider:        { name: 'Líder',        color: '#0071ce' },
  unimarc:      { name: 'Unimarc',      color: '#da291c' },
};

const CATEGORY_SEARCH_OVERRIDES: Record<string, string> = {
  'Lácteos y Huevos':   'Lácteos',
  'Limpieza del Hogar': 'Limpieza',
  'Panadería y Dulces': 'Panadería',
  'Hogar y Tecnología': 'Hogar',
  'Bebidas y Licores':  'Bebidas',
  'Bebés y Niños':      'Bebé',
  'Quesos y Fiambres':  'Quesos',
  'Carnes y Pescados':  'Carnes',
  'Frutas y Verduras':  'Frutas',
  'Comidas Preparadas': 'Preparad',
};

const Home: React.FC = () => {
  const navigate = useNavigate();
  const { coords, selectedBranches, selectedStore, setSelectedStore } = useLocation();
  const { theme, toggleTheme } = useTheme();
  const { username: authUsername } = useAuth();
  const username = authUsername || 'Usuario';
  const [isLocationOpen, setIsLocationOpen] = useState(false);
  const [priceDrops, setPriceDrops] = useState<PriceDropItem[]>([]);
  const [deals, setDeals] = useState<Deal[]>([]);
  const [essentialProducts, setEssentialProducts] = useState<Product[]>([]);
  const [historicLows, setHistoricLows] = useState<HistoricLow[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchingDeals, setSearchingDeals] = useState(true);
  const [dealsOffset, setDealsOffset] = useState(0);
  const [refreshingDeals, setRefreshingDeals] = useState(false);
  const DEALS_PAGE_SIZE = 10;

  // Logic to get a friendly location name
  const getFriendlyLocation = () => {
    const branches = Object.values(selectedBranches) as Branch[];
    if (branches.length > 0) {
      return branches[0].city || 'Mi Ubicación';
    }
    return coords ? 'Buscando tiendas...' : 'Chile';
  };

  const getTodayNotifications = () => {
    const today = new Date().toDateString();
    return notifications.filter(n => new Date(n.created_at).toDateString() === today);
  };

  useEffect(() => {
    setDealsOffset(0);
    setDeals([]);
    setEssentialProducts([]);
    setHistoricLows([]);
    setPriceDrops([]);
    setSearchingDeals(true);
    async function loadData() {
      try {
        const results = await Promise.allSettled([
          getDeals(DEALS_PAGE_SIZE, 0, selectedStore ?? undefined),
          getCategories(selectedStore ?? undefined),
          getHistoricLows(5)
        ]);

        let loadedDeals: Deal[] = [];
        let loadedLows: HistoricLow[] = [];

        if (results[0].status === 'fulfilled') {
          loadedDeals = results[0].value;
          const filtered = selectedStore
            ? loadedDeals.filter(d => d.store_slug === selectedStore)
            : loadedDeals;
          setDeals(filtered);

          // Si hay pocas ofertas para esta tienda, complementar con productos populares
          if (filtered.length < 5 && selectedStore) {
            try {
              const { results: ess } = await searchProducts('', undefined, 1, 12, 'price_asc', selectedStore);
              setEssentialProducts(ess);
            } catch {
              setEssentialProducts([]);
            }
          }
        }
        if (results[1].status === 'fulfilled') setCategories(results[1].value);
        if (results[2].status === 'fulfilled') {
          loadedLows = results[2].value;
          setHistoricLows(loadedLows);
        }

        // Comparar precios actuales contra snapshots guardados → detectar bajadas
        const snapshots = readPriceSnapshots();
        const newSnapshots: PriceSnapshotMap = { ...snapshots };
        const dropMap = new Map<number, PriceDropItem>();

        const processItem = (
          productId: number, name: string, imageUrl: string,
          price: number, storeSlug: string, storeName: string,
        ) => {
          const key = String(productId);
          const old = snapshots[key];
          if (old && price < old.price * 0.99 && !dropMap.has(productId)) {
            dropMap.set(productId, {
              productId, name, imageUrl,
              currentPrice: price, previousPrice: old.price,
              storeSlug, storeName,
              dropAmount: old.price - price,
              dropPercent: ((old.price - price) / old.price) * 100,
            });
          }
          const existing = newSnapshots[key];
          if (!existing || price < existing.price) {
            newSnapshots[key] = { price, storeSlug, storeName, name, imageUrl, savedAt: Date.now() };
          }
        };

        for (const deal of loadedDeals) {
          if (deal.price != null) processItem(deal.product_id, deal.product_name, deal.image_url, deal.price, deal.store_slug, deal.store_name);
        }
        for (const hl of loadedLows) {
          if (hl.min_price_all_time != null) processItem(hl.product_id, hl.product_name, hl.image_url ?? '', hl.min_price_all_time, hl.store_slug ?? '', hl.store_name);
        }

        setPriceDrops([...dropMap.values()].sort((a, b) => b.dropAmount - a.dropAmount));
        writePriceSnapshots(newSnapshots);
      } catch (error) {
        console.error('Error loading home data:', error);
      } finally {
        setSearchingDeals(false);
        setLoading(false);
      }
    }
    loadData();
  }, [selectedStore]);

  const filterByStore = (raw: typeof deals) =>
    selectedStore ? raw.filter(d => d.store_slug === selectedStore) : raw;

  const handleRefreshDeals = async () => {
    if (refreshingDeals) return;
    setRefreshingDeals(true);
    try {
      const nextOffset = dealsOffset + DEALS_PAGE_SIZE;
      const newDeals = filterByStore(
        await getDeals(DEALS_PAGE_SIZE, nextOffset, selectedStore ?? undefined)
      );
      if (newDeals.length > 0) {
        setDeals(newDeals);
        setDealsOffset(nextOffset);
      } else {
        // Sin más páginas: traer un pool amplio, mezclar y mostrar para dar variedad
        const pool = filterByStore(
          await getDeals(DEALS_PAGE_SIZE * 5, 0, selectedStore ?? undefined)
        );
        const shuffled = [...pool].sort(() => Math.random() - 0.5);
        setDeals(shuffled.slice(0, DEALS_PAGE_SIZE));
        setDealsOffset(0);
      }
    } catch (err) {
      console.error('Error refreshing deals:', err);
    } finally {
      setRefreshingDeals(false);
    }
  };

  const getCategoryIcon = (name: string) => {
    const n = name.toLowerCase();
    if (n.includes('leche') || n.includes('lacteos')) return 'local_drink';
    if (n.includes('fruta') || n.includes('verdura')) return 'eco';
    if (n.includes('carne') || n.includes('pollo')) return 'restaurant';
    if (n.includes('arroz') || n.includes('despensa')) return 'inventory_2';
    if (n.includes('bebida') || n.includes('jugo')) return 'local_drink';
    if (n.includes('limpieza') || n.includes('detergente')) return 'cleaning_services';
    return 'shopping_basket';
  };

  return (
    <div className="flex flex-col">
      <LocationSelector isOpen={isLocationOpen} onClose={() => setIsLocationOpen(false)} />
      
      <HomeHeader
        username={username}
        selectedStore={selectedStore}
        theme={theme}
        notifications={notifications}
        toggleTheme={toggleTheme}
        onOpenLocation={() => setIsLocationOpen(true)}
      />

      {/* Main Content */}
      <main>
        {/* Categories */}
        <section>
          <div data-tour="categories" className="flex items-center justify-between px-4 pt-4 pb-2">
            <h3 className="text-slate-900 dark:text-white text-lg font-bold tracking-tight">Categorías</h3>
            <button 
              onClick={() => navigate('/categories')}
              className="text-primary text-sm font-semibold"
            >
              Ver todas
            </button>
          </div>
          <div className="flex gap-3 px-4 py-3 overflow-x-auto no-scrollbar">
            {categories.map((cat, idx) => (
              <div
                key={cat.name}
                onClick={() => navigate(`/search?category=${encodeURIComponent(CATEGORY_SEARCH_OVERRIDES[cat.name] ?? cat.name)}${selectedStore ? `&store=${selectedStore}` : ''}`)}
                className={`flex h-10 shrink-0 items-center justify-center gap-x-2 rounded-xl px-4 border cursor-pointer border-slate-100 dark:border-slate-700 bg-white dark:bg-slate-800`}
              >
                <span className="material-symbols-outlined text-[20px] text-primary">
                  {getCategoryIcon(cat.name)}
                </span>
                <p className="text-sm font-semibold text-slate-700 dark:text-slate-300">
                  {cat.name}
                </p>
                <span className="text-[10px] text-slate-400">({cat.product_count})</span>
              </div>
            ))}
            {loading && [1,2,3].map(i => (
               <div key={i} className="flex h-10 w-24 shrink-0 animate-pulse bg-slate-200 dark:bg-slate-700 rounded-xl"></div>
            ))}
          </div>
        </section>

        {/* Deals */}
        <section className="mt-4">
          <div className="flex items-center justify-between px-4 pb-4">
            <h3 className="text-slate-900 dark:text-white text-lg font-bold tracking-tight">
              {!searchingDeals && deals.length === 0 && essentialProducts.length > 0
                ? `Productos en ${selectedStore && STORE_META[selectedStore] ? STORE_META[selectedStore].name : 'la tienda'}`
                : selectedStore && STORE_META[selectedStore]
                  ? `Ofertas en ${STORE_META[selectedStore].name}`
                  : 'Mejores Ofertas de Hoy'}
            </h3>
            <div className="flex items-center gap-2">
              <div className="flex items-center gap-1 text-primary text-sm font-semibold">
                <span className="material-symbols-outlined text-sm">bolt</span>
                Ofertas Flash
              </div>
              <button
                onClick={handleRefreshDeals}
                disabled={refreshingDeals || searchingDeals}
                className="flex items-center justify-center size-8 rounded-full bg-primary/10 text-primary border border-primary/20 active:scale-90 transition-all disabled:opacity-40"
                title="Ver más ofertas"
              >
                <span className={`material-symbols-outlined text-[18px] ${refreshingDeals ? 'animate-spin' : ''}`}>
                  refresh
                </span>
              </button>
            </div>
          </div>
          <div className="flex gap-4 px-4 overflow-x-auto no-scrollbar pb-4">
            {searchingDeals ? (
              <div className="flex flex-col items-center justify-center w-full py-12 px-8 bg-slate-50 dark:bg-[#1a2e22]/30 rounded-3xl border-2 border-dashed border-slate-200 dark:border-primary/20 animate-in fade-in zoom-in duration-500">
                <div className="relative">
                  <span className="material-symbols-outlined text-primary text-[48px] animate-spin-slow">cyclone</span>
                  <span className="absolute -top-1 -right-1 flex h-3 w-3">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary opacity-75"></span>
                    <span className="relative inline-flex rounded-full h-3 w-3 bg-primary"></span>
                  </span>
                </div>
                <h4 className="text-sm font-bold text-slate-900 dark:text-white mt-4 text-center">Buscando las mejores ofertas diarias...</h4>
                <p className="text-[10px] text-slate-500 mt-2 uppercase tracking-widest font-black flex items-center gap-1">
                  BUSCANDO OFERTAS
                </p>
                <div className="mt-6 flex gap-1.5">
                  <div className="w-1.5 h-1.5 bg-primary rounded-full animate-bounce [animation-delay:-0.3s]"></div>
                  <div className="w-1.5 h-1.5 bg-primary rounded-full animate-bounce [animation-delay:-0.15s]"></div>
                  <div className="w-1.5 h-1.5 bg-primary rounded-full animate-bounce"></div>
                </div>
              </div>
            ) : (deals.length > 0 || essentialProducts.length > 0) ? (
              <>
                {deals.map((deal) => (
                  <div
                    key={`${deal.product_id}-${deal.store_slug}`}
                    onClick={() => navigate(`/product/${deal.product_id}`)}
                    className="flex-none w-48 bg-white dark:bg-slate-800 rounded-xl overflow-hidden border border-slate-100 dark:border-slate-700 shadow-sm cursor-pointer hover:shadow-md transition-all active:scale-95 group"
                  >
                    <div className="relative h-32 w-full bg-slate-50 dark:bg-slate-900 flex items-center justify-center">
                      {deal.discount_percent && (
                        <div className="absolute top-2 left-2 z-10 bg-red-500 text-white text-[10px] font-bold px-2 py-0.5 rounded-full uppercase">
                          -{Math.round(deal.discount_percent)}%
                        </div>
                      )}
                      <div className="absolute top-2 right-2 z-10 size-6 overflow-hidden">
                        <StoreLogo slug={deal.store_slug} name={deal.store_name} className="size-full shadow-sm" />
                      </div>
                      <img src={deal.image_url} alt={deal.product_name} className="size-full object-contain p-4 group-hover:scale-110 transition-transform" />
                    </div>
                    <div className="p-3">
                      <h4 className="text-slate-900 dark:text-white text-sm font-bold truncate">{deal.product_name}</h4>
                      <p className="text-slate-500 text-[10px] mt-1">{deal.store_name} • {deal.brand}</p>
                      <div className="flex items-center gap-2 mt-2">
                        <span className="text-primary text-lg font-bold">{formatCurrency(deal.price)}</span>
                        {deal.list_price && (
                          <span className="text-slate-400 text-xs line-through">{formatCurrency(deal.list_price)}</span>
                        )}
                      </div>
                      <button className="w-full mt-3 bg-primary hover:bg-primary/90 text-background-dark text-xs font-bold py-2 rounded-lg transition-colors">
                        Ver Comparación
                      </button>
                    </div>
                  </div>
                ))}
                {essentialProducts.map((product) => {
                  const storePrice = product.prices?.find(p => p.store_slug === selectedStore);
                  const price = storePrice?.price ?? product.best_price;
                  const listPrice = storePrice?.list_price;
                  return (
                    <div
                      key={`ess-${product.id}`}
                      onClick={() => navigate(`/product/${product.id}`)}
                      className="flex-none w-44 bg-white dark:bg-slate-800 rounded-xl overflow-hidden border border-slate-100 dark:border-slate-700 shadow-sm cursor-pointer hover:shadow-md transition-all active:scale-95 group"
                    >
                      <div className="relative h-28 w-full bg-slate-50 dark:bg-slate-900 flex items-center justify-center">
                        <img
                          src={product.image_url || ''}
                          alt={product.name}
                          className="size-full object-contain p-3 group-hover:scale-110 transition-transform"
                        />
                      </div>
                      <div className="p-3">
                        <h4 className="text-slate-900 dark:text-white text-xs font-bold leading-tight line-clamp-2 mb-1">{product.name}</h4>
                        {product.brand && <p className="text-slate-400 text-[10px] truncate">{product.brand}</p>}
                        <div className="flex items-center gap-1.5 mt-2">
                          <span style={{ color: 'var(--store-primary)' }} className="text-base font-bold">
                            {price !== null ? formatCurrency(price) : '—'}
                          </span>
                          {listPrice && listPrice > (price ?? 0) && (
                            <span className="text-slate-400 text-[10px] line-through">{formatCurrency(listPrice)}</span>
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </>
            ) : (
              <div className="text-center py-8 w-full">
                <span className="material-symbols-outlined text-slate-300 text-[40px]">local_offer</span>
                <p className="text-slate-500 text-sm mt-2">Sin ofertas registradas hoy.</p>
                <button
                  onClick={() => navigate(`/search?store=${selectedStore ?? ''}`)}
                  className="mt-3 text-xs font-bold underline underline-offset-2"
                  style={{ color: 'var(--store-primary)' }}
                >
                  Ver todos los productos →
                </button>
              </div>
            )}
          </div>
        </section>

        {/* Título de sección cuando muestra productos esenciales en vez de ofertas */}
        {!searchingDeals && deals.length === 0 && essentialProducts.length > 0 && (
          <p className="px-4 -mt-2 mb-2 text-xs text-slate-400 italic">
            Sin ofertas registradas hoy — mostrando productos disponibles en {selectedStore && STORE_META[selectedStore] ? STORE_META[selectedStore].name : 'la tienda'}.
          </p>
        )}

        {/* Historic Lows — filtrados por tienda activa */}
        {(() => {
          const visibleLows = selectedStore
            ? historicLows.filter(h => h.store_slug === selectedStore)
            : historicLows;
          if (visibleLows.length === 0) return null;
          return (
          <section className="mt-6">
            <div className="flex items-center justify-between px-4 pb-4">
              <h3 className="text-slate-900 dark:text-white text-lg font-bold tracking-tight">Mínimos Históricos</h3>
              <div className="flex items-center gap-1 text-primary text-sm font-semibold">
                <span className="material-symbols-outlined text-sm">trending_down</span>
                Precios mínimos
              </div>
            </div>
            <div className="flex gap-4 px-4 overflow-x-auto no-scrollbar pb-4">
              {visibleLows.map((deal) => (
                <div
                  key={`historic-${deal.product_id}`}
                  onClick={() => navigate(`/product/${deal.product_id}`)}
                  className="flex-none w-64 bg-emerald-50 dark:bg-emerald-900/20 rounded-xl overflow-hidden border border-emerald-200 dark:border-emerald-800/30 shadow-sm cursor-pointer hover:shadow-md transition-all active:scale-95 group flex items-center p-3 gap-3"
                >
                  <div className="relative size-16 bg-white dark:bg-slate-900 rounded-lg flex items-center justify-center shrink-0 border border-emerald-100 dark:border-emerald-800/50">
                    <img src={deal.image_url} alt={deal.product_name} className="size-12 object-contain group-hover:scale-110 transition-transform" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <h4 className="text-slate-900 dark:text-white text-xs font-bold truncate leading-tight mb-1">{deal.product_name}</h4>
                    <p className="text-emerald-600 dark:text-emerald-400 text-xs font-black">{formatCurrency(deal.min_price_all_time)}</p>
                    <p className="text-slate-400 text-[9px] mt-0.5 truncate flex items-center gap-1">
                       <span className="material-symbols-outlined text-[10px]">storefront</span> {deal.store_name}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </section>
          );
        })()}

        {/* Bajó de precio */}
        {priceDrops.length > 0 && (
          <section className="mt-6 mb-6">
            <div className="flex items-center justify-between px-4 pb-3">
              <div>
                <h3 className="text-slate-900 dark:text-white text-lg font-bold tracking-tight">📉 Bajó de precio</h3>
                <p className="text-[11px] text-slate-500 dark:text-slate-400 mt-0.5">
                  Productos más baratos que la última vez que los viste
                </p>
              </div>
              <div className="flex items-center gap-1 text-red-500 text-sm font-semibold">
                <span className="material-symbols-outlined text-[16px]">arrow_downward</span>
                Bajan ahora
              </div>
            </div>
            <div className="flex gap-4 px-4 overflow-x-auto no-scrollbar pb-2">
              {priceDrops.map((drop) => (
                <div
                  key={`drop-${drop.productId}`}
                  onClick={() => navigate(`/product/${drop.productId}`)}
                  className="flex-none w-52 bg-red-50 dark:bg-red-900/10 rounded-xl overflow-hidden border border-red-200 dark:border-red-800/30 shadow-sm cursor-pointer hover:shadow-md transition-all active:scale-95 group"
                >
                  <div className="relative h-28 w-full bg-white dark:bg-slate-900 flex items-center justify-center">
                    <div className="absolute top-2 left-2 z-10 bg-red-500 text-white text-[10px] font-bold px-2 py-0.5 rounded-full uppercase">
                      -{Math.round(drop.dropPercent)}%
                    </div>
                    <div className="absolute top-2 right-2 z-10 size-6 overflow-hidden">
                      <StoreLogo slug={drop.storeSlug} name={drop.storeName} className="size-full shadow-sm" />
                    </div>
                    <img src={drop.imageUrl} alt={drop.name} className="size-full object-contain p-3 group-hover:scale-110 transition-transform" />
                  </div>
                  <div className="p-3">
                    <h4 className="text-slate-900 dark:text-white text-xs font-bold leading-tight line-clamp-2 mb-2">{drop.name}</h4>
                    <div className="flex items-baseline gap-2 flex-wrap">
                      <span className="text-red-600 dark:text-red-400 text-base font-bold">{formatCurrency(drop.currentPrice)}</span>
                      <span className="text-slate-400 text-xs line-through">{formatCurrency(drop.previousPrice)}</span>
                    </div>
                    <p className="text-red-500 dark:text-red-400 text-[10px] font-bold mt-1">
                      Ahorrás {formatCurrency(drop.dropAmount)} en {drop.storeName}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* Savings Card deshabilitada — KAIROS inactivo */}
      </main>
    </div>
  );
};

export default Home;

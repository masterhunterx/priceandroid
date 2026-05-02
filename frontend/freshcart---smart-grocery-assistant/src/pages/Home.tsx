import React, { useEffect, useState, useRef, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { getDeals, getCategories, formatCurrency, getNotifications, getHistoricLows, refreshNotifications, searchProducts, readPriceSnapshots, writePriceSnapshots, PriceSnapshotMap } from '../lib/api';
import { Deal, Category, Notification, Branch, Product, HistoricLow } from '../types';

interface BasketItem {
  label: string;
  icon: string;
  productId: number;
  name: string;
  price: number;
  imageUrl: string;
}

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
import StorePickerSheet from '../components/StorePickerSheet';
import StoreLogo from '../components/StoreLogo';
import { useLocation } from '../context/LocationContext';
import { useTheme } from '../context/ThemeContext';
import LocationSelector from '../components/LocationSelector';
import { useCart } from '../context/CartContext';

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
  const { addItem, isInCart } = useCart();
  const username = authUsername || 'Usuario';
  const [isLocationOpen, setIsLocationOpen] = useState(false);
  const [isStorePickerOpen, setIsStorePickerOpen] = useState(false);
  const [priceDrops, setPriceDrops] = useState<PriceDropItem[]>([]);
  const [basket, setBasket] = useState<BasketItem[]>([]);
  const [loadingBasket, setLoadingBasket] = useState(true);
  const [deals, setDeals] = useState<Deal[]>([]);
  const [essentialProducts, setEssentialProducts] = useState<Product[]>([]);
  const [historicLows, setHistoricLows] = useState<HistoricLow[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchingDeals, setSearchingDeals] = useState(true);
  const [dealsOffset, setDealsOffset] = useState(0);
  const [refreshingDeals, setRefreshingDeals] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const [pullY, setPullY] = useState(0);
  const [pullRefreshing, setPullRefreshing] = useState(false);
  const touchStartY = useRef(0);
  const PULL_THRESHOLD = 70;
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
    const controller = new AbortController();
    let cancelled = false;

    setDealsOffset(0);
    setDeals([]);
    setEssentialProducts([]);
    setHistoricLows([]);
    setPriceDrops([]);
    setBasket([]);
    setLoadingBasket(true);
    setSearchingDeals(true);

    async function loadAll() {
      // ── Fase 1: datos principales + canasta en paralelo ──────────────────
      const BASKET_ESSENTIALS = [
        { label: 'Leche',  icon: 'local_drink',  terms: ['leche'] },
        { label: 'Pan',    icon: 'bakery_dining', terms: ['pan de molde', 'pan'] },
        { label: 'Huevos', icon: 'egg',           terms: ['huevo'] },
        { label: 'Arroz',  icon: 'rice_bowl',     terms: ['arroz'] },
        { label: 'Pollo',  icon: 'set_meal',      terms: ['pollo'] },
        { label: 'Aceite', icon: 'water_drop',    terms: ['aceite'] },
      ];

      const [dealsRes, catsRes, lowsRes, basketRes] = await Promise.allSettled([
        getDeals(DEALS_PAGE_SIZE, 0, selectedStore ?? undefined),
        getCategories(selectedStore ?? undefined),
        getHistoricLows(5),
        // Una sola búsqueda amplia para la canasta (en vez de 6 paralelas)
        searchProducts('', undefined, 1, 50, 'price_asc', selectedStore ?? ''),
      ]);

      if (cancelled) return;

      // ── Categorías ────────────────────────────────────────────────────────
      if (catsRes.status === 'fulfilled') setCategories(catsRes.value);

      // ── Canasta básica (filtrar localmente el resultado amplio) ────────────
      if (basketRes.status === 'fulfilled') {
        const allProds = basketRes.value.results;
        const usedIds = new Set<number>();
        const items: BasketItem[] = [];
        for (const e of BASKET_ESSENTIALS) {
          const match = allProds.find(p =>
            !usedIds.has(p.id) &&
            p.best_price != null &&
            e.terms.some(t => p.name.toLowerCase().includes(t))
          );
          if (match && match.best_price != null) {
            items.push({ label: e.label, icon: e.icon, productId: match.id, name: match.name, price: match.best_price, imageUrl: match.image_url });
            usedIds.add(match.id);
          }
        }
        if (!cancelled) setBasket(items);
      }
      if (!cancelled) setLoadingBasket(false);

      // ── Deals + essentials fallback ───────────────────────────────────────
      let loadedDeals: Deal[] = [];
      let loadedLows: HistoricLow[] = [];

      if (dealsRes.status === 'fulfilled') {
        loadedDeals = dealsRes.value;
        const filtered = selectedStore
          ? loadedDeals.filter(d => d.store_slug === selectedStore)
          : loadedDeals;
        if (!cancelled) setDeals(filtered);

        if (filtered.length < 10) {
          try {
            // Reusar el resultado de canasta si hay suficientes productos
            const poolProds = basketRes.status === 'fulfilled' ? basketRes.value.results : [];
            if (poolProds.length >= 3) {
              if (!cancelled) setEssentialProducts(poolProds.slice(0, 12));
            } else {
              // Fallback explícito sin filtro de tienda
              const { results: global } = await searchProducts('', undefined, 1, 12, 'price_asc', '');
              if (!cancelled) setEssentialProducts(global);
            }
          } catch {
            // silencioso
          }
        }
      }

      if (lowsRes.status === 'fulfilled') {
        loadedLows = lowsRes.value;
        if (!cancelled) setHistoricLows(loadedLows);
      }

      // ── Price drops ───────────────────────────────────────────────────────
      if (!cancelled) {
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
      }

      if (!cancelled) {
        setSearchingDeals(false);
        setLoading(false);
      }
    }

    loadAll().catch(err => {
      if (!cancelled) {
        console.error('Error loading home data:', err);
        setSearchingDeals(false);
        setLoading(false);
        setLoadingBasket(false);
      }
    });

    return () => { cancelled = true; controller.abort(); };
  }, [selectedStore, refreshKey]);

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
      setRefreshKey(k => k + 1);
      await new Promise(r => setTimeout(r, 800));
      setPullRefreshing(false);
    }
    setPullY(0);
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

  const heroItem = deals[0] ?? null;
  const storeName = selectedStore && STORE_META[selectedStore] ? STORE_META[selectedStore].name : null;
  const totalBasket = basket.reduce((s, i) => s + i.price, 0);
  const allAlerts = useMemo(() => [
    ...priceDrops.map(d => ({ type: 'drop' as const, id: d.productId, name: d.name, imageUrl: d.imageUrl, price: d.currentPrice, oldPrice: d.previousPrice, pct: d.dropPercent, storeSlug: d.storeSlug, storeName: d.storeName })),
    ...(selectedStore ? historicLows.filter(h => h.store_slug === selectedStore) : historicLows).map(h => ({ type: 'low' as const, id: h.product_id, name: h.product_name, imageUrl: h.image_url ?? '', price: h.min_price_all_time, oldPrice: null, pct: null, storeSlug: h.store_slug ?? '', storeName: h.store_name })),
  ], [priceDrops, historicLows, selectedStore]);

  return (
    <div
      className="flex flex-col pb-24"
      onTouchStart={handleTouchStart}
      onTouchMove={handleTouchMove}
      onTouchEnd={handleTouchEnd}
      style={{ transform: pullY > 0 ? `translateY(${pullY}px)` : undefined, transition: pullY === 0 ? 'transform 0.3s ease' : undefined }}
    >
      {pullY > 0 && (
        <div className="fixed top-0 left-0 right-0 z-50 flex justify-center pointer-events-none" style={{ transform: `translateY(${pullY - 40}px)` }}>
          <div className={`size-9 rounded-full bg-primary flex items-center justify-center shadow-lg transition-transform ${pullY >= PULL_THRESHOLD ? 'scale-110' : 'scale-90'}`}>
            <span className={`material-symbols-outlined text-background-dark text-lg ${pullRefreshing ? 'animate-spin' : ''}`}>refresh</span>
          </div>
        </div>
      )}

      <LocationSelector isOpen={isLocationOpen} onClose={() => setIsLocationOpen(false)} />
      <StorePickerSheet
        isOpen={isStorePickerOpen}
        currentStore={selectedStore}
        onSelect={(slug) => { setSelectedStore(slug); }}
        onClose={() => setIsStorePickerOpen(false)}
      />
      <HomeHeader username={username} selectedStore={selectedStore} theme={theme} notifications={notifications} toggleTheme={toggleTheme} onOpenLocation={() => setIsLocationOpen(true)} onOpenStorePicker={() => setIsStorePickerOpen(true)} />

      <main className="space-y-6 pb-4">

        {/* ── HERO KAIROS ─────────────────────────────────────────────────── */}
        {!loading && heroItem && (
          <div
            onClick={() => navigate(`/product/${heroItem.product_id}`)}
            className="mx-4 mt-4 rounded-2xl overflow-hidden cursor-pointer active:scale-[0.98] transition-transform bg-white dark:bg-slate-900 border border-slate-100 dark:border-slate-800 shadow-sm"
          >
            {/* Borde superior del color de la tienda — única línea de color */}
            <div className="h-0.5 w-full bg-primary" />
            <div className="flex items-center gap-4 p-4">
              <div className="size-24 shrink-0 bg-slate-50 dark:bg-slate-800 rounded-xl flex items-center justify-center overflow-hidden">
                <img src={heroItem.image_url} alt={heroItem.product_name} className="size-20 object-contain" loading="lazy" />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1">Mejor deal hoy</p>
                <h3 className="text-slate-900 dark:text-white font-bold text-sm leading-tight line-clamp-2 mb-2">{heroItem.product_name}</h3>
                <div className="flex items-baseline gap-2">
                  <span className="text-primary text-2xl font-black">{formatCurrency(heroItem.price)}</span>
                  {heroItem.list_price && (
                    <span className="text-slate-400 text-sm line-through">{formatCurrency(heroItem.list_price)}</span>
                  )}
                </div>
                <div className="flex items-center gap-1.5 mt-1.5">
                  <StoreLogo slug={heroItem.store_slug} name={heroItem.store_name} className="size-4" />
                  <span className="text-slate-500 dark:text-slate-400 text-[11px]">{heroItem.store_name}</span>
                  {heroItem.discount_percent && (
                    <span className="ml-auto bg-red-500 text-white text-[10px] font-bold px-2 py-0.5 rounded-full">
                      -{Math.round(heroItem.discount_percent)}%
                    </span>
                  )}
                </div>
              </div>
            </div>
          </div>
        )}
        {loading && (
          <div className="mx-4 mt-4 h-32 rounded-2xl bg-slate-200 dark:bg-slate-800 animate-pulse" />
        )}

        {/* ── CATEGORÍAS (scroll horizontal compacto) ─────────────────────── */}
        <div className="px-4">
          <div className="flex gap-2 overflow-x-auto no-scrollbar">
            {loading
              ? [1,2,3,4].map(i => <div key={i} className="flex h-8 w-20 shrink-0 animate-pulse bg-slate-200 dark:bg-slate-700 rounded-full" />)
              : categories.slice(0, 8).map(cat => (
                <button
                  key={cat.name}
                  onClick={() => navigate(`/search?category=${encodeURIComponent(CATEGORY_SEARCH_OVERRIDES[cat.name] ?? cat.name)}${selectedStore ? `&store=${selectedStore}` : ''}`)}
                  className="flex h-8 shrink-0 items-center gap-1.5 rounded-full px-3 border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 active:bg-primary/10 transition-colors"
                >
                  <span className="material-symbols-outlined text-[14px] text-slate-400">{getCategoryIcon(cat.name)}</span>
                  <span className="text-xs font-semibold text-slate-700 dark:text-slate-300 whitespace-nowrap">{cat.name}</span>
                </button>
              ))
            }
            {!loading && categories.length > 8 && (
              <button
                onClick={() => navigate('/categories')}
                className="flex h-8 shrink-0 items-center gap-1 rounded-full px-3 border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-500 dark:text-slate-400"
              >
                <span className="text-xs font-bold">Ver más</span>
                <span className="material-symbols-outlined text-[14px]">chevron_right</span>
              </button>
            )}
          </div>
        </div>

        {/* ── CANASTA DEL DÍA ─────────────────────────────────────────────── */}
        {(loadingBasket || basket.length > 0) && (
          <section className="px-4">
            <div className="flex items-center justify-between mb-3">
              <div>
                <h3 className="text-slate-900 dark:text-white text-base font-bold tracking-tight">Canasta del día</h3>
                <p className="text-[11px] text-slate-500 dark:text-slate-400">
                  {storeName ? `Precios en ${storeName}` : 'Mejores precios disponibles'}
                </p>
              </div>
              {!loadingBasket && (
                <div className="flex flex-col items-end">
                  <span className="text-[10px] text-slate-400 font-bold uppercase tracking-wider">Total</span>
                  <span className="text-lg font-black text-primary">{formatCurrency(totalBasket)}</span>
                </div>
              )}
            </div>

            <div className="bg-white dark:bg-slate-800/60 rounded-2xl border border-slate-100 dark:border-slate-700 overflow-hidden">
              {loadingBasket
                ? [1,2,3,4].map(i => (
                    <div key={i} className="flex items-center gap-3 px-4 py-3 border-b border-slate-100 dark:border-slate-700/50 last:border-0 animate-pulse">
                      <div className="size-10 rounded-xl bg-slate-200 dark:bg-slate-700 shrink-0" />
                      <div className="flex-1 space-y-1.5">
                        <div className="h-3 w-20 bg-slate-200 dark:bg-slate-700 rounded" />
                        <div className="h-2.5 w-32 bg-slate-100 dark:bg-slate-700/50 rounded" />
                      </div>
                      <div className="h-4 w-14 bg-slate-200 dark:bg-slate-700 rounded" />
                    </div>
                  ))
                : basket.map((item, idx) => (
                    <div
                      key={item.productId}
                      onClick={() => navigate(`/product/${item.productId}`)}
                      className={`flex items-center gap-3 px-4 py-3 cursor-pointer active:bg-slate-50 dark:active:bg-slate-700/50 transition-colors ${idx < basket.length - 1 ? 'border-b border-slate-100 dark:border-slate-700/50' : ''}`}
                    >
                      <div className="size-10 rounded-xl bg-slate-50 dark:bg-slate-900 flex items-center justify-center shrink-0 overflow-hidden">
                        {item.imageUrl
                          ? <img src={item.imageUrl} alt={item.name} className="size-9 object-contain" loading="lazy" />
                          : <span className="material-symbols-outlined text-primary text-[20px]">{item.icon}</span>
                        }
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">{item.label}</p>
                        <p className="text-sm font-semibold text-slate-800 dark:text-slate-200 truncate">{item.name}</p>
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                        <span className="text-base font-black text-primary">{formatCurrency(item.price)}</span>
                        <button
                          onClick={e => {
                            e.stopPropagation();
                            if (!isInCart(item.productId)) {
                              addItem({ product_id: item.productId, name: item.name, brand: '', image_url: item.imageUrl, price: item.price, store_slug: selectedStore ?? '', store_name: storeName ?? '' });
                            }
                          }}
                          className={`size-7 rounded-full flex items-center justify-center transition-all active:scale-90 ${isInCart(item.productId) ? 'bg-primary text-background-dark' : 'bg-slate-100 dark:bg-slate-700 text-slate-400'}`}
                        >
                          <span className="material-symbols-outlined text-[16px]">{isInCart(item.productId) ? 'check' : 'add'}</span>
                        </button>
                      </div>
                    </div>
                  ))
              }
            </div>

            {!loadingBasket && basket.length > 0 && (
              <button
                onClick={() => {
                  basket.forEach(item => {
                    if (!isInCart(item.productId)) {
                      addItem({ product_id: item.productId, name: item.name, brand: '', image_url: item.imageUrl, price: item.price, store_slug: selectedStore ?? '', store_name: storeName ?? '' });
                    }
                  });
                  navigate('/cart');
                }}
                className="w-full mt-3 py-3.5 rounded-xl bg-primary text-background-dark text-sm font-bold flex items-center justify-center gap-2 active:scale-[0.98] transition-transform shadow-lg shadow-primary/20"
              >
                <span className="material-symbols-outlined text-[18px]">shopping_cart</span>
                Agregar toda la canasta · {formatCurrency(totalBasket)}
              </button>
            )}
          </section>
        )}

        {/* ── ALERTAS (bajadas + mínimos) ──────────────────────────────────── */}
        {allAlerts.length > 0 && (
          <section className="px-4">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-slate-900 dark:text-white text-base font-bold tracking-tight">Alertas de precio</h3>
              <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">{allAlerts.length} producto{allAlerts.length !== 1 ? 's' : ''}</span>
            </div>
            <div className="space-y-2">
              {allAlerts.slice(0, 5).map(alert => (
                <div
                  key={`alert-${alert.type}-${alert.id}`}
                  onClick={() => navigate(`/product/${alert.id}`)}
                  className="flex items-center gap-3 bg-white dark:bg-slate-800/60 rounded-xl px-3 py-2.5 border border-slate-100 dark:border-slate-700 cursor-pointer active:scale-[0.98] transition-transform"
                >
                  <div className={`size-8 rounded-lg flex items-center justify-center shrink-0 ${alert.type === 'drop' ? 'bg-red-100 dark:bg-red-900/30' : 'bg-emerald-100 dark:bg-emerald-900/30'}`}>
                    <span className={`material-symbols-outlined text-[16px] ${alert.type === 'drop' ? 'text-red-500' : 'text-emerald-500'}`}>
                      {alert.type === 'drop' ? 'arrow_downward' : 'trending_down'}
                    </span>
                  </div>
                  <div className="size-10 shrink-0 bg-slate-50 dark:bg-slate-900 rounded-lg overflow-hidden flex items-center justify-center">
                    <img src={alert.imageUrl} alt={alert.name} className="size-9 object-contain" loading="lazy" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-semibold text-slate-800 dark:text-slate-200 truncate leading-tight">{alert.name}</p>
                    <p className="text-[10px] text-slate-400 flex items-center gap-0.5">
                      <span className="material-symbols-outlined text-[10px]">storefront</span>{alert.storeName}
                    </p>
                  </div>
                  <div className="flex flex-col items-end shrink-0">
                    <span className={`text-base font-black ${alert.type === 'drop' ? 'text-red-500' : 'text-emerald-500'}`}>
                      {formatCurrency(alert.price)}
                    </span>
                    {alert.pct && (
                      <span className="text-[10px] font-bold text-red-400">-{Math.round(alert.pct)}%</span>
                    )}
                    {alert.type === 'low' && (
                      <span className="text-[9px] font-bold text-emerald-400 uppercase">Mínimo</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* ── OFERTAS FLASH ────────────────────────────────────────────────── */}
        <section>
          <div className="flex items-center justify-between px-4 mb-3">
            <div className="flex items-center gap-2">
              <h3 className="text-slate-900 dark:text-white text-base font-bold tracking-tight">
                {storeName ? `Ofertas en ${storeName}` : 'Ofertas flash'}
              </h3>
              <span className="flex size-5 items-center justify-center">
                <span className="animate-ping absolute inline-flex h-2.5 w-2.5 rounded-full bg-primary opacity-60" />
                <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-primary" />
              </span>
            </div>
            <button
              onClick={handleRefreshDeals}
              disabled={refreshingDeals || searchingDeals}
              className="flex items-center justify-center size-8 rounded-full bg-slate-100 dark:bg-slate-800 text-slate-500 border border-slate-200 dark:border-slate-700 active:scale-90 transition-all disabled:opacity-40"
            >
              <span className={`material-symbols-outlined text-[18px] ${refreshingDeals ? 'animate-spin' : ''}`}>refresh</span>
            </button>
          </div>
          <div className="flex gap-3 px-4 overflow-x-auto no-scrollbar pb-2">
            {searchingDeals
              ? [1,2,3].map(i => <div key={i} className="flex-none w-40 h-52 animate-pulse bg-slate-200 dark:bg-slate-800 rounded-2xl" />)
              : (deals.length > 0 ? deals : essentialProducts.map(p => ({
                  product_id: p.id, product_name: p.name, image_url: p.image_url,
                  price: p.best_price ?? 0, list_price: null, store_slug: p.prices?.[0]?.store_slug ?? '',
                  store_name: p.prices?.[0]?.store_name ?? '', brand: p.brand ?? '', discount_percent: null,
                }))).map(deal => (
                <div
                  key={`deal-${deal.product_id}-${deal.store_slug}`}
                  onClick={() => navigate(`/product/${deal.product_id}`)}
                  className="flex-none w-40 bg-white dark:bg-slate-800 rounded-2xl overflow-hidden border border-slate-100 dark:border-slate-700 shadow-sm cursor-pointer active:scale-95 transition-transform"
                >
                  <div className="relative h-28 bg-slate-50 dark:bg-slate-900 flex items-center justify-center">
                    {deal.discount_percent && (
                      <span className="absolute top-2 left-2 bg-red-500 text-white text-[9px] font-bold px-1.5 py-0.5 rounded-full">
                        -{Math.round(deal.discount_percent)}%
                      </span>
                    )}
                    <div className="absolute top-2 right-2 size-5 overflow-hidden rounded">
                      <StoreLogo slug={deal.store_slug} name={deal.store_name} className="size-full" />
                    </div>
                    <img src={deal.image_url} alt={deal.product_name} className="size-full object-contain p-3" loading="lazy" />
                  </div>
                  <div className="p-3">
                    <p className="text-xs font-bold text-slate-900 dark:text-white line-clamp-2 leading-tight mb-1">{deal.product_name}</p>
                    <p className="text-primary text-base font-black">{formatCurrency(deal.price)}</p>
                    {deal.list_price && (
                      <p className="text-slate-400 text-[10px] line-through">{formatCurrency(deal.list_price)}</p>
                    )}
                  </div>
                </div>
              ))
            }
            {!searchingDeals && deals.length === 0 && essentialProducts.length === 0 && (
              <div className="text-center py-8 w-full">
                <span className="material-symbols-outlined text-slate-300 text-[40px]">local_offer</span>
                <p className="text-slate-500 text-sm mt-2">Sin ofertas registradas hoy.</p>
              </div>
            )}
          </div>
        </section>

      </main>
    </div>
  );
};

export default Home;

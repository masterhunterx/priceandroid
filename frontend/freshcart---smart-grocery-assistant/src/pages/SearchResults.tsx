import React, { useEffect, useState, useRef, useCallback } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  searchProducts,
  toggleFavorite,
  formatCurrency,
  getSearchSuggestions,
  getTrendingSearches,
  getRecentSearches,
  saveRecentSearch,
  clearRecentSearches,
} from '../lib/api';
import { Product, SearchSuggestion } from '../types';
import StoreLogo from '../components/StoreLogo';
import { useLocation } from '../context/LocationContext';
import { useCart } from '../context/CartContext';

const STORES = ['jumbo', 'lider', 'unimarc', 'santa_isabel'] as const;
const STORE_LABELS: Record<string, string> = {
  jumbo: 'Jumbo',
  lider: 'Lider',
  unimarc: 'Unimarc',
  santa_isabel: 'Santa Isabel',
};

const OFFER_BADGE: Record<string, { cls: string; icon: string; label: string }> = {
  card:     { cls: 'bg-amber-100 text-amber-700 dark:bg-amber-500/20 dark:text-amber-400', icon: 'credit_card', label: 'Club' },
  internet: { cls: 'bg-indigo-100 text-indigo-700 dark:bg-indigo-500/20 dark:text-indigo-400', icon: 'public', label: 'Web' },
  app:      { cls: 'bg-purple-100 text-purple-700 dark:bg-purple-500/20 dark:text-purple-400', icon: 'smartphone', label: 'App' },
};

const SearchResults: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { getBranchContext, selectedStore } = useLocation();

  const query        = searchParams.get('q') || '';
  const categoryParam = searchParams.get('category') || '';
  const storeParam   = searchParams.get('store') || '';

  // Si la URL no trae store, inicializar desde la tienda activa del contexto
  const [results, setResults]       = useState<Product[]>([]);
  const [total, setTotal]           = useState(0);
  const [page, setPage]             = useState(1);
  const [loading, setLoading]       = useState(false);
  const [searchError, setSearchError] = useState(false);
  const [sort, setSort]             = useState('price_asc');
  const [store, setStore]           = useState(storeParam || selectedStore || '');
  const { addItem, removeItem, isInCart } = useCart();
  const sentinelRef = useRef<HTMLDivElement>(null);

  // Autocomplete
  const [searchQuery, setSearchQuery]       = useState(query);
  const [suggestions, setSuggestions]       = useState<SearchSuggestion[]>([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [trending, setTrending]             = useState<{ term: string; icon: string }[]>([]);
  const [recent, setRecent]                 = useState<string[]>([]);

  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    getTrendingSearches().then(setTrending).catch(() => {});
    setRecent(getRecentSearches());
  }, []);

  // Sync URL → input when navigating back
  useEffect(() => {
    setSearchQuery(query);
  }, [query]);

  const handleStoreToggle = (slug: string) => {
    const next = store === slug ? '' : slug;
    setStore(next);
    setPage(1);
    const p = new URLSearchParams(searchParams);
    if (next) p.set('store', next); else p.delete('store');
    setSearchParams(p, { replace: true });
  };

  const handleSort = () => {
    setSort(s => {
      setPage(1);
      return s === 'price_asc' ? 'price_desc' : 'price_asc';
    });
  };

  const handleToggleCart = (e: React.MouseEvent, product: Product) => {
    e.stopPropagation();
    if (isInCart(product.id)) {
      removeItem(product.id);
    } else {
      addItem({
        product_id: product.id,
        name: product.name,
        brand: product.brand || '',
        image_url: product.image_url || '',
        price: product.best_price || 0,
        store_slug: product.best_store_slug || '',
        store_name: product.best_store || '',
      });
    }
    toggleFavorite(product.id).catch(() => {});
  };

  // Resetear página cuando cambian los filtros
  useEffect(() => {
    setPage(1);
    setResults([]);
  }, [query, categoryParam, sort, store]);

  // ── Execute search whenever query/sort/store/page changes ─────────────────────
  useEffect(() => {
    if (!query && !categoryParam) { setResults([]); setTotal(0); setSearchError(false); return; }
    let cancelled = false;
    setSearchError(false);
    setLoading(true);
    (async () => {
      try {
        const branchContext = getBranchContext();
        const data = await searchProducts(query, categoryParam, page, 20, sort, store, branchContext);
        if (cancelled) return;
        setResults(prev => page === 1 ? data.results : [...prev, ...data.results]);
        setTotal(data.total);
        if (page === 1 && query) saveRecentSearch(query);
      } catch {
        if (cancelled) return;
        setSearchError(true);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [query, categoryParam, sort, store, page, getBranchContext]);

  // ── Scroll infinito ───────────────────────────────────────────────────────────
  const hasMore = results.length < total;
  useEffect(() => {
    const el = sentinelRef.current;
    if (!el) return;
    const observer = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting && hasMore && !loading) {
        setPage(p => p + 1);
      }
    }, { rootMargin: '300px' });
    observer.observe(el);
    return () => observer.disconnect();
  }, [hasMore, loading]);

  // ── Real-time suggestions + live search debounce ──────────────────────────────
  const liveSearchTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const suggestTimer    = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Limpiar timers pendientes al desmontar el componente
  useEffect(() => {
    return () => {
      if (suggestTimer.current) clearTimeout(suggestTimer.current);
      if (liveSearchTimer.current) clearTimeout(liveSearchTimer.current);
    };
  }, []);

  const handleInputChange = (value: string) => {
    setSearchQuery(value);

    // Suggestions — 200 ms debounce
    if (suggestTimer.current) clearTimeout(suggestTimer.current);
    if (value.length >= 2) {
      suggestTimer.current = setTimeout(async () => {
        try {
          const data = await getSearchSuggestions(value);
          setSuggestions(data);
          setShowSuggestions(data.length > 0);
        } catch {
          setSuggestions([]);
          setShowSuggestions(false);
        }
      }, 200);
    } else {
      setSuggestions([]);
      setShowSuggestions(false);
    }

    // Live search — 400 ms debounce (updates URL → triggers result fetch)
    if (liveSearchTimer.current) clearTimeout(liveSearchTimer.current);
    if (value.trim().length >= 2) {
      liveSearchTimer.current = setTimeout(() => {
        const p = new URLSearchParams(searchParams);
        p.set('q', value.trim());
        setSearchParams(p, { replace: true });
      }, 400);
    } else if (value.trim() === '') {
      // Clear results when input is emptied
      const p = new URLSearchParams(searchParams);
      p.delete('q');
      setSearchParams(p, { replace: true });
    }
  };

  const doSearch = (term: string) => {
    setShowSuggestions(false);
    setSearchQuery(term);
    if (term.trim()) {
      saveRecentSearch(term);
      setRecent(getRecentSearches());
      navigate(`/search?q=${encodeURIComponent(term)}`, { replace: true });
    }
  };

  // Navigate directly to product when suggestion has product_id
  const handleSuggestionClick = (s: SearchSuggestion) => {
    setShowSuggestions(false);
    if (s.type === 'product' && s.product_id) {
      navigate(`/product/${s.product_id}`);
    } else {
      doSearch(s.term);
    }
  };

  const handleClearRecent = () => {
    clearRecentSearches();
    setRecent([]);
  };

  // Close suggestions on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (inputRef.current && !inputRef.current.closest('.search-wrapper')?.contains(e.target as Node)) {
        setShowSuggestions(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const showDiscoveryPanel = !query && !categoryParam;

  return (
    <div className="flex flex-col min-h-screen">
      {/* ── Header ── */}
      <header className="sticky top-0 z-50 bg-background-light/95 dark:bg-background-dark/95 backdrop-blur-md border-b border-slate-200 dark:border-white/10">
        <div className="flex items-center p-4 pb-2 justify-between gap-3">
          <span
            onClick={() => navigate(-1)}
            className="material-symbols-outlined cursor-pointer text-slate-900 dark:text-white shrink-0"
          >
            arrow_back_ios
          </span>

          {/* Search input + dropdown wrapper */}
          <div className="search-wrapper flex-1 relative">
            <input
              ref={inputRef}
              autoFocus
              className="w-full bg-transparent border-none text-lg font-bold p-0 focus:ring-0 text-slate-900 dark:text-white placeholder:text-slate-400"
              placeholder="Buscar productos..."
              value={searchQuery}
              onChange={e => handleInputChange(e.target.value)}
              onFocus={() => suggestions.length > 0 && setShowSuggestions(true)}
              onKeyDown={e => {
                if (e.key === 'Enter') {
                  e.preventDefault();
                  doSearch(searchQuery);
                }
                if (e.key === 'Escape') setShowSuggestions(false);
              }}
            />

            {/* Live suggestions dropdown */}
            {showSuggestions && suggestions.length > 0 && (
              <div className="absolute top-full left-0 right-0 mt-2 bg-white dark:bg-[#1c2720] border border-slate-200 dark:border-white/10 rounded-2xl shadow-2xl z-[100] overflow-hidden">
                <div className="max-h-[320px] overflow-y-auto">
                  {suggestions.map((s, i) => (
                    <button
                      key={i}
                      onMouseDown={e => { e.preventDefault(); handleSuggestionClick(s); }}
                      className="w-full flex items-center justify-between px-4 py-3 border-b border-slate-100 dark:border-white/5 last:border-0 hover:bg-primary/5 dark:hover:bg-primary/10 active:bg-primary/10 transition-colors text-left"
                    >
                      <div className="flex items-center gap-3 min-w-0">
                        <span className="material-symbols-outlined text-[18px] text-slate-400 shrink-0">
                          {s.type === 'product' ? 'shopping_bag' : s.type === 'brand' ? 'label' : 'category'}
                        </span>
                        <span className="text-sm font-bold text-slate-900 dark:text-white truncate">{s.term}</span>
                      </div>
                      <div className="flex items-center gap-2 shrink-0 ml-2">
                        {s.store && (
                          <span className="text-[10px] text-slate-400 font-medium">{s.store}</span>
                        )}
                        {s.product_id ? (
                          <span className="material-symbols-outlined text-[14px] text-primary">arrow_forward</span>
                        ) : (
                          <span className="material-symbols-outlined text-[14px] text-slate-300">search</span>
                        )}
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Clear / Search button */}
          {searchQuery ? (
            <button onClick={() => { setSearchQuery(''); setSuggestions([]); setShowSuggestions(false); doSearch(''); }} className="shrink-0">
              <span className="material-symbols-outlined text-slate-400">close</span>
            </button>
          ) : (
            <span className="material-symbols-outlined text-primary shrink-0">search</span>
          )}
        </div>

        {/* Loading bar */}
        {loading && (
          <div className="h-0.5 bg-slate-100 dark:bg-white/5">
            <div className="h-full bg-primary animate-[loading_1s_ease-in-out_infinite]" style={{ width: '60%', marginLeft: '20%' }} />
          </div>
        )}

        {/* Trending chips */}
        {trending.length > 0 && (
          <div className="px-4 pb-2 overflow-x-auto no-scrollbar flex gap-2">
            {trending.map((t, i) => (
              <button
                key={i}
                onClick={() => doSearch(t.term)}
                className="flex items-center gap-1 px-2.5 py-1 rounded-full bg-slate-100 dark:bg-white/5 border border-slate-200 dark:border-white/10 hover:border-primary transition-colors shrink-0 active:scale-95"
              >
                <span className="text-[11px]">{t.icon}</span>
                <span className="text-[11px] font-semibold text-slate-700 dark:text-slate-300">{t.term}</span>
              </button>
            ))}
          </div>
        )}

        {/* Store filters */}
        <div className="flex gap-2 px-4 pb-3 overflow-x-auto no-scrollbar">
          {STORES.map(slug => (
            <button
              key={slug}
              onClick={() => handleStoreToggle(slug)}
              className={`flex h-8 shrink-0 items-center justify-center gap-x-1.5 rounded-full border px-3.5 shadow-sm transition-all text-xs font-bold active:scale-95 ${
                store === slug
                  ? 'bg-primary border-primary text-background-dark'
                  : 'bg-white dark:bg-[#1c2720] border-slate-200 dark:border-white/10 text-slate-700 dark:text-slate-300'
              }`}
            >
              {STORE_LABELS[slug]}
            </button>
          ))}
        </div>
      </header>

      {/* ── Discovery panel (empty query) ── */}
      {showDiscoveryPanel ? (
        <main className="flex-1 px-4 pt-4 pb-20">
          {recent.length > 0 && (
            <section className="mb-6">
              <div className="flex items-center justify-between mb-3">
                <p className="text-[11px] font-black uppercase tracking-widest text-slate-400">Buscado recientemente</p>
                <button onClick={handleClearRecent} className="text-[11px] text-primary font-semibold">Borrar</button>
              </div>
              <div className="flex flex-col gap-1">
                {recent.map((term, i) => (
                  <button
                    key={i}
                    onClick={() => doSearch(term)}
                    className="flex items-center gap-3 p-3 rounded-xl hover:bg-slate-50 dark:hover:bg-white/5 text-left transition-colors active:scale-95"
                  >
                    <span className="material-symbols-outlined text-[18px] text-slate-400">history</span>
                    <span className="text-sm font-semibold text-slate-800 dark:text-white">{term}</span>
                  </button>
                ))}
              </div>
            </section>
          )}

          {recent.length === 0 && (
            <div className="flex flex-col items-center justify-center mt-24 text-center px-10">
              <span className="material-symbols-outlined text-6xl text-slate-300 dark:text-slate-600 mb-4">search</span>
              <h3 className="text-lg font-bold text-slate-900 dark:text-white">¿Qué buscas hoy?</h3>
              <p className="text-slate-500 mt-2 text-sm">
                Escribe al menos 2 letras para ver sugerencias en tiempo real.
              </p>
            </div>
          )}
        </main>
      ) : (
        /* ── Results ── */
        <main className="flex-1">
          <div className="flex items-center gap-4 px-4 py-3 justify-between">
            <p className="text-slate-500 dark:text-[#9db9a8] text-sm">
              {loading ? 'Buscando...' : `${total} resultado${total !== 1 ? 's' : ''}${query ? ` para "${query}"` : ''}`}
            </p>
            <button
              onClick={handleSort}
              className="flex items-center gap-1.5 text-primary transition-all active:scale-95"
            >
              <span className="material-symbols-outlined text-[20px]">swap_vert</span>
              <p className="text-slate-900 dark:text-white text-sm font-bold">
                {sort === 'price_asc' ? 'Menor Precio' : 'Mayor Precio'}
              </p>
            </button>
          </div>

          <div className="flex flex-col gap-4 px-4 pb-20">
            {results.map(product => (
              <div
                key={product.id}
                onClick={() => navigate(`/product/${product.id}`)}
                className="flex flex-col gap-3 rounded-xl p-4 shadow-sm border bg-white dark:bg-[#1c2720] border-slate-100 dark:border-white/5 cursor-pointer hover:border-primary/50 active:scale-[0.98] transition-all"
              >
                <div className={`flex items-stretch justify-between gap-4 ${!product.best_price ? 'opacity-50 grayscale' : ''}`}>
                  <div className="flex flex-[3_3_0px] flex-col gap-2">
                    <div className="flex flex-col gap-1">
                      <p className="text-base font-bold leading-tight text-slate-900 dark:text-white">{product.name}</p>
                      <p className="text-slate-500 dark:text-[#9db9a8] text-xs">
                        {product.weight_value} {product.weight_unit} · {product.brand}
                      </p>
                    </div>
                    <div className="mt-1">
                      {product.best_price ? (
                        <>
                          <p className="text-2xl font-black leading-tight text-primary">
                            {formatCurrency(product.best_price)}
                          </p>
                          {(() => {
                            const best = product.prices.find(p => p.price === product.best_price);
                            if (!best) return null;
                            const ot = best.offer_type;
                            return (
                              <div className="flex flex-col gap-1 mt-1">
                                <div className="flex items-center gap-1.5 flex-wrap">
                                  {ot && OFFER_BADGE[ot] && (
                                    <span className={`flex items-center gap-0.5 text-[9px] font-bold px-1.5 py-0.5 rounded ${OFFER_BADGE[ot].cls}`}>
                                      <span className="material-symbols-outlined" style={{ fontSize: '10px' }}>{OFFER_BADGE[ot].icon}</span>
                                      {OFFER_BADGE[ot].label}
                                    </span>
                                  )}
                                </div>
                                <div className="flex items-center gap-1.5 flex-wrap">
                                  <StoreLogo slug={product.best_store_slug || ''} name={product.best_store || ''} className="size-4" />
                                  <p className="text-slate-500 text-[10px]">
                                    Mejor precio en <span className="font-bold text-primary">{product.best_store}</span>
                                  </p>
                                  {best.price_per_unit != null && best.unit_label && (
                                    <span className="text-[9px] text-sky-400 font-bold bg-sky-500/10 px-1.5 py-0.5 rounded">
                                      ~{formatCurrency(best.price_per_unit)}/{best.unit_label.replace('$/', '')}
                                    </span>
                                  )}
                                  {best.is_stale && (
                                    <span className="text-[9px] text-amber-500 font-bold flex items-center gap-0.5">
                                      <span className="material-symbols-outlined text-[10px]">warning</span>
                                      {best.store_slug === 'lider' ? 'Posible bloqueo PerimeterX' : '+6h sin actualizar'}
                                    </span>
                                  )}
                                </div>
                              </div>
                            );
                          })()}
                        </>
                      ) : (
                        <div className="py-1 px-3 bg-slate-100 dark:bg-white/5 rounded-lg inline-block border border-slate-200 dark:border-white/10">
                          <p className="text-sm font-black text-slate-400 dark:text-slate-500 uppercase tracking-tighter">Sin Stock</p>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Product image */}
                  <div className="w-24 h-24 shrink-0 rounded-lg border border-slate-100 dark:border-white/10 bg-white p-2 flex items-center justify-center">
                    <img
                      src={product.image_url}
                      alt={product.name}
                      className="size-full object-contain"
                      onError={e => { (e.target as HTMLImageElement).style.opacity = '0.3'; }}
                    />
                  </div>
                </div>

                <div className="flex gap-2">
                  <button
                    onClick={e => { e.stopPropagation(); navigate(`/product/${product.id}`); }}
                    className="flex-1 flex items-center justify-center rounded-lg h-10 bg-primary text-background-dark gap-2 text-sm font-bold shadow-md shadow-primary/10 active:scale-95 transition-all"
                  >
                    <span className="material-symbols-outlined text-[20px]">equalizer</span>
                    <span className="truncate">Ver precios</span>
                  </button>
                  <button
                    onClick={e => handleToggleCart(e, product)}
                    className={`flex w-10 items-center justify-center rounded-lg h-10 active:scale-95 transition-all ${
                      isInCart(product.id)
                        ? 'bg-red-100 dark:bg-red-900/30 text-red-500'
                        : 'bg-slate-100 dark:bg-[#28392f] text-slate-400 dark:text-slate-500'
                    }`}
                  >
                    <span className="material-symbols-outlined text-[20px]" style={{ fontVariationSettings: isInCart(product.id) ? "'FILL' 1" : "'FILL' 0" }}>
                      favorite
                    </span>
                  </button>
                </div>
              </div>
            ))}

            {/* Skeleton loaders */}
            {loading && [1, 2, 3].map(i => (
              <div key={i} className="h-40 w-full animate-pulse bg-slate-200 dark:bg-slate-800 rounded-xl" />
            ))}

            {/* Sentinel para scroll infinito */}
            <div ref={sentinelRef} className="h-1" />

            {!loading && !hasMore && results.length > 0 && (
              <p className="text-center text-xs text-slate-400 py-4">— {total} productos mostrados —</p>
            )}

            {!loading && searchError && (
              <div className="flex flex-col items-center justify-center mt-20 text-center px-10">
                <span className="material-symbols-outlined text-6xl text-red-300 mb-4">wifi_off</span>
                <h3 className="text-lg font-bold text-slate-900 dark:text-white">Error de conexión</h3>
                <p className="text-slate-500 mt-2">No se pudo conectar al servidor. Verifica tu conexión e intenta de nuevo.</p>
              </div>
            )}
            {!loading && !searchError && results.length === 0 && query && (
              <div className="flex flex-col items-center justify-center mt-20 text-center px-10">
                <span className="material-symbols-outlined text-6xl text-slate-300 mb-4">search_off</span>
                <h3 className="text-lg font-bold text-slate-900 dark:text-white">Sin resultados para "{query}"</h3>
                <p className="text-slate-500 mt-2">Prueba términos más cortos: "leche", "arroz", "aceite".</p>
              </div>
            )}
          </div>
        </main>
      )}
    </div>
  );
};

export default SearchResults;

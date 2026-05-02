import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { getCategories } from '../lib/api';
import { useLocation } from '../context/LocationContext';

interface Category {
  name: string;
  emoji: string;
  color: string;
  product_count: number;
}

// Algunas categorías canónicas no coinciden exactamente con el top_category raw
// del scraper (ej. "Limpieza del Hogar" vs "Limpieza"). Mapeamos al término
// que el backend actual sí indexa correctamente.
// Cada supermercado guarda top_category con nombres distintos al canónico.
// Usamos el primer término significativo que funciona en todos los stores.
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

const Categories: React.FC = () => {
  const navigate = useNavigate();
  const { selectedStore, setSelectedStore } = useLocation();
  const [categories, setCategories] = useState<Category[]>([]);
  const [loading, setLoading] = useState(true);

  const navToCategory = (name: string) => {
    const searchTerm = CATEGORY_SEARCH_OVERRIDES[name] ?? name;
    navigate(`/search?category=${encodeURIComponent(searchTerm)}${selectedStore ? `&store=${selectedStore}` : ''}`);
  };

  useEffect(() => {
    setLoading(true);
    getCategories(selectedStore ?? undefined)
      .then(data => setCategories(data as unknown as Category[]))
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [selectedStore]);

  const featuredCategories = categories.slice(0, 4);
  const restCategories = categories.slice(4);

  return (
    <div className="flex flex-col min-h-screen bg-white dark:bg-black">
      {/* Header */}
      <header className="sticky top-0 z-50 bg-white dark:bg-black border-b border-gray-100 dark:border-zinc-900">
        <div className="flex items-center gap-3 p-4">
          <button
            onClick={() => navigate(-1)}
            className="size-9 flex items-center justify-center rounded-full bg-gray-100 dark:bg-zinc-900"
          >
            <span className="material-symbols-outlined text-black dark:text-white text-[20px]">arrow_back_ios</span>
          </button>
          <div>
            <h1 className="text-lg font-black text-black dark:text-white">Categorías</h1>
            <p className="text-xs text-gray-400 dark:text-zinc-500">{categories.length} departamentos disponibles</p>
          </div>
        </div>
        {/* Filtro de tienda */}
        <div className="px-4 pb-3 flex gap-2 overflow-x-auto no-scrollbar">
          {[
            { label: 'Todas',    value: null,       color: '#00f076' },
            { label: 'Jumbo',    value: 'jumbo',    color: '#00a650' },
            { label: 'Líder',    value: 'lider',    color: '#0071ce' },
            { label: 'Unimarc', value: 'unimarc',  color: '#da291c' },
            { label: 'S. Isabel', value: 'santaisabel', color: '#e30613' },
          ].map(({ label, value, color }) => {
            const active = (selectedStore ?? null) === value;
            return (
              <button
                key={label}
                onClick={() => setSelectedStore(value)}
                className={`h-8 px-3 rounded-full text-xs font-bold shrink-0 transition-colors ${
                  active
                    ? ''
                    : 'bg-gray-100 dark:bg-zinc-900 text-black dark:text-white'
                }`}
                style={
                  active
                    ? {
                        border: `2px solid ${color}`,
                        background: `${color}20`,
                        color,
                      }
                    : undefined
                }
              >
                {label}
              </button>
            );
          })}
        </div>
      </header>

      <main className="flex-1">
        {loading ? (
          <div className="p-4">
            {[...Array(8)].map((_, i) => (
              <div key={i} className={`flex items-center gap-4 px-5 py-4 animate-pulse ${i < 7 ? 'border-b border-gray-100 dark:border-zinc-900' : ''}`}>
                <div className="size-10 rounded-xl bg-gray-100 dark:bg-zinc-900 shrink-0" />
                <div className="flex-1 space-y-1.5">
                  <div className="h-3 w-32 bg-gray-100 dark:bg-zinc-900 rounded" />
                  <div className="h-2.5 w-20 bg-gray-100 dark:bg-zinc-900 rounded" />
                </div>
              </div>
            ))}
          </div>
        ) : (
          <>
            {/* Featured — top 4 */}
            {featuredCategories.length > 0 && (
              <section className="py-5">
                <p className="text-[11px] font-bold text-gray-400 dark:text-zinc-500 uppercase tracking-widest px-5 mb-3">Más populares</p>
                <div>
                  {featuredCategories.map((cat, idx) => (
                    <button
                      key={cat.name}
                      onClick={() => navToCategory(cat.name)}
                      className={`w-full flex items-center gap-4 px-5 py-4 active:bg-gray-50 dark:active:bg-zinc-900 transition-colors text-left ${
                        idx < featuredCategories.length - 1 ? 'border-b border-gray-100 dark:border-zinc-900' : ''
                      }`}
                    >
                      <div className="size-10 rounded-xl bg-gray-100 dark:bg-zinc-900 flex items-center justify-center text-xl flex-shrink-0">
                        {cat.emoji}
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-[15px] font-bold text-black dark:text-white truncate">{cat.name}</p>
                        <p className="text-[12px] text-gray-400 dark:text-zinc-500">{cat.product_count.toLocaleString()} productos</p>
                      </div>
                      <span className="material-symbols-outlined text-gray-300 dark:text-zinc-700 text-[18px]">chevron_right</span>
                    </button>
                  ))}
                </div>
              </section>
            )}

            {/* Rest — lista compacta */}
            {restCategories.length > 0 && (
              <section className="pb-5">
                <div className="h-px bg-gray-100 dark:bg-zinc-900" />
                <p className="text-[11px] font-bold text-gray-400 dark:text-zinc-500 uppercase tracking-widest px-5 py-4">Todos los departamentos</p>
                <div>
                  {restCategories.map((cat, idx) => (
                    <button
                      key={cat.name}
                      onClick={() => navToCategory(cat.name)}
                      className={`w-full flex items-center gap-4 px-5 py-3.5 active:bg-gray-50 dark:active:bg-zinc-900 transition-colors text-left ${
                        idx < restCategories.length - 1 ? 'border-b border-gray-100 dark:border-zinc-900' : ''
                      }`}
                    >
                      <div className="size-10 rounded-xl bg-gray-100 dark:bg-zinc-900 flex items-center justify-center text-xl flex-shrink-0">
                        {cat.emoji}
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-[14px] font-semibold text-black dark:text-white truncate">{cat.name}</p>
                        <p className="text-[12px] text-gray-400 dark:text-zinc-500">{cat.product_count.toLocaleString()} productos</p>
                      </div>
                      <span className="material-symbols-outlined text-gray-300 dark:text-zinc-700 text-[18px]">chevron_right</span>
                    </button>
                  ))}
                </div>
              </section>
            )}
          </>
        )}
      </main>
    </div>
  );
};

export default Categories;

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

const Categories: React.FC = () => {
  const navigate = useNavigate();
  const { selectedStore } = useLocation();
  const [categories, setCategories] = useState<Category[]>([]);
  const [loading, setLoading] = useState(true);

  const navToCategory = (name: string) =>
    navigate(`/search?category=${encodeURIComponent(name)}${selectedStore ? `&store=${selectedStore}` : ''}`);

  useEffect(() => {
    getCategories()
      .then(data => setCategories(data as unknown as Category[]))
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  const featuredCategories = categories.slice(0, 4);
  const restCategories = categories.slice(4);

  return (
    <div className="flex flex-col min-h-screen bg-slate-50 dark:bg-background-dark">
      {/* Header */}
      <header className="sticky top-0 z-50 bg-white/95 dark:bg-background-dark/95 backdrop-blur-md border-b border-slate-100 dark:border-white/10">
        <div className="flex items-center gap-3 p-4">
          <button
            onClick={() => navigate(-1)}
            className="size-9 flex items-center justify-center rounded-full bg-slate-100 dark:bg-slate-800"
          >
            <span className="material-symbols-outlined text-slate-700 dark:text-white text-[20px]">arrow_back_ios</span>
          </button>
          <div>
            <h1 className="text-lg font-bold text-slate-900 dark:text-white">Categorías</h1>
            <p className="text-xs text-slate-400">{categories.length} departamentos disponibles</p>
          </div>
        </div>
      </header>

      <main className="p-4 flex-1 space-y-6">
        {loading ? (
          <div className="grid grid-cols-2 gap-3">
            {[...Array(8)].map((_, i) => (
              <div key={i} className="h-32 rounded-2xl bg-slate-200 dark:bg-slate-800 animate-pulse" />
            ))}
          </div>
        ) : (
          <>
            {/* Featured — top 4 en grid 2x2 grande */}
            {featuredCategories.length > 0 && (
              <section>
                <p className="text-xs font-bold text-slate-400 uppercase tracking-widest mb-3">Más populares</p>
                <div className="grid grid-cols-2 gap-3">
                  {featuredCategories.map(cat => (
                    <button
                      key={cat.name}
                      onClick={() => navToCategory(cat.name)}
                      className="relative overflow-hidden rounded-2xl p-4 text-left active:scale-95 transition-transform"
                      style={{ background: `${cat.color}18`, border: `1.5px solid ${cat.color}30` }}
                    >
                      <span className="text-4xl block mb-2">{cat.emoji}</span>
                      <p className="text-sm font-bold text-slate-900 dark:text-white leading-tight">{cat.name}</p>
                      <p className="text-xs mt-1 font-medium" style={{ color: cat.color }}>
                        {cat.product_count.toLocaleString()} productos
                      </p>
                      {/* Decorative circle */}
                      <div
                        className="absolute -right-4 -bottom-4 w-16 h-16 rounded-full opacity-20"
                        style={{ background: cat.color }}
                      />
                    </button>
                  ))}
                </div>
              </section>
            )}

            {/* Rest — lista compacta */}
            {restCategories.length > 0 && (
              <section>
                <p className="text-xs font-bold text-slate-400 uppercase tracking-widest mb-3">Todos los departamentos</p>
                <div className="bg-white dark:bg-[#161f1a] rounded-2xl border border-slate-100 dark:border-white/5 overflow-hidden">
                  {restCategories.map((cat, idx) => (
                    <button
                      key={cat.name}
                      onClick={() => navToCategory(cat.name)}
                      className={`w-full flex items-center gap-4 px-4 py-3.5 active:bg-slate-50 dark:active:bg-white/5 transition-colors text-left ${
                        idx < restCategories.length - 1 ? 'border-b border-slate-100 dark:border-white/5' : ''
                      }`}
                    >
                      {/* Color dot + emoji */}
                      <div
                        className="size-10 rounded-xl flex items-center justify-center text-xl flex-shrink-0"
                        style={{ background: `${cat.color}18` }}
                      >
                        {cat.emoji}
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-semibold text-slate-900 dark:text-white truncate">{cat.name}</p>
                        <p className="text-xs text-slate-400">{cat.product_count.toLocaleString()} productos</p>
                      </div>
                      <span className="material-symbols-outlined text-slate-300 text-[18px]">chevron_right</span>
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

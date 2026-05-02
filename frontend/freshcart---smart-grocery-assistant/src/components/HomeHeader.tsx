import React, { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Notification } from '../types';
import { useAuth } from '../context/AuthContext';

const STORE_META: Record<string, { name: string; color: string }> = {
  jumbo:        { name: 'Jumbo',        color: '#00a650' },
  santa_isabel: { name: 'Santa Isabel', color: '#e30613' },
  lider:        { name: 'Líder',        color: '#0071ce' },
  unimarc:      { name: 'Unimarc',      color: '#da291c' },
};

interface HomeHeaderProps {
  username: string;
  selectedStore: string | null;
  theme: 'light' | 'dark';
  notifications: Notification[];
  toggleTheme: () => void;
  onOpenLocation: () => void;
  onOpenStorePicker: () => void;
}

const HomeHeader: React.FC<HomeHeaderProps> = ({
  username,
  selectedStore,
  theme,
  notifications,
  toggleTheme,
  onOpenLocation,
  onOpenStorePicker,
}) => {
  const navigate = useNavigate();
  const { logout } = useAuth();
  const [showUserMenu, setShowUserMenu] = useState(false);
  const userMenuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!showUserMenu) return;
    const handler = (e: MouseEvent) => {
      if (userMenuRef.current && !userMenuRef.current.contains(e.target as Node)) {
        setShowUserMenu(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [showUserMenu]);

  const storeColor = selectedStore && STORE_META[selectedStore] ? STORE_META[selectedStore].color : '#00f076';
  const storeName = selectedStore && STORE_META[selectedStore] ? STORE_META[selectedStore].name : null;

  return (
    <header className="sticky top-0 z-50 bg-white dark:bg-black border-b border-gray-100 dark:border-zinc-900">
      <div className="flex items-center px-5 py-3 gap-3">
        {/* User menu */}
        <div className="relative" ref={userMenuRef}>
          <button
            onClick={() => setShowUserMenu(v => !v)}
            className="size-9 rounded-full bg-gray-100 dark:bg-zinc-900 flex items-center justify-center active:scale-90 transition-transform"
          >
            <span className="material-symbols-outlined text-[20px] text-gray-500 dark:text-zinc-400">person</span>
          </button>
          {showUserMenu && (
            <div className="absolute left-0 top-11 z-50 min-w-[180px] rounded-2xl bg-white dark:bg-zinc-900 shadow-xl border border-gray-100 dark:border-zinc-800 overflow-hidden">
              <div className="px-4 py-3 border-b border-gray-100 dark:border-zinc-800">
                <p className="text-[11px] text-gray-400 dark:text-zinc-500">Sesión iniciada como</p>
                <p className="text-sm font-bold text-black dark:text-white truncate">{username}</p>
              </div>
              <button
                onClick={() => { setShowUserMenu(false); logout(); navigate('/login'); }}
                className="flex w-full items-center gap-2 px-4 py-3 text-sm text-red-500 hover:bg-gray-50 dark:hover:bg-zinc-800 transition-colors"
              >
                <span className="material-symbols-outlined text-[18px]">logout</span>
                Cerrar sesión
              </button>
            </div>
          )}
        </div>

        {/* Store picker + title */}
        <div className="flex-1 min-w-0">
          <button
            onClick={onOpenStorePicker}
            className="flex items-center gap-1.5 mb-0.5 active:opacity-60 transition-opacity"
          >
            <div className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: storeColor }} />
            <span className="text-[11px] font-bold uppercase tracking-widest text-gray-400 dark:text-zinc-500">
              {storeName || 'Todas las tiendas'}
            </span>
            <span className="material-symbols-outlined text-gray-400 dark:text-zinc-500 text-[14px]">expand_more</span>
          </button>
          <h1 className="text-[18px] font-black text-black dark:text-white tracking-tight leading-tight">
            {storeName ? `Ofertas en ${storeName}` : 'Mejores Ofertas'}
          </h1>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-1">
          <button onClick={toggleTheme} className="size-10 flex items-center justify-center active:scale-90 transition-transform">
            <span className="material-symbols-outlined text-[22px] text-gray-400 dark:text-zinc-500">
              {theme === 'dark' ? 'light_mode' : 'dark_mode'}
            </span>
          </button>
          <button onClick={() => navigate('/notifications')} className="relative size-10 flex items-center justify-center">
            <span className="material-symbols-outlined text-[22px] text-gray-400 dark:text-zinc-500">notifications</span>
            {notifications.length > 0 && (
              <span className="absolute top-2 right-2 w-2 h-2 rounded-full bg-red-500" />
            )}
          </button>
        </div>
      </div>

      {/* Search bar */}
      <div className="px-5 pb-3">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            const q = (e.currentTarget.elements.namedItem('search') as HTMLInputElement).value;
            if (q) navigate(`/search?q=${q}${selectedStore ? `&store=${selectedStore}` : ''}`);
          }}
          data-tour="search"
          className="flex items-center bg-gray-100 dark:bg-zinc-900 rounded-xl h-11 px-4 gap-2"
        >
          <span className="material-symbols-outlined text-[20px] text-gray-400 dark:text-zinc-500 shrink-0">search</span>
          <input
            name="search"
            className="flex-1 bg-transparent text-black dark:text-white placeholder:text-gray-400 dark:placeholder:text-zinc-500 text-[15px] font-medium border-none focus:ring-0 focus:outline-none"
            placeholder="Buscar productos o marcas..."
          />
          <button type="submit" className="shrink-0">
            <span className="material-symbols-outlined text-[20px] text-gray-400 dark:text-zinc-500">arrow_forward</span>
          </button>
        </form>
      </div>
    </header>
  );
};

export default HomeHeader;

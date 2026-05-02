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

  return (
    <header
      className="sticky top-0 z-50 backdrop-blur-md"
      style={{ backgroundColor: theme === 'dark' ? 'var(--store-header-bg-dark)' : 'var(--store-header-bg-light)' }}
    >
      <div className="flex items-center p-4 pb-0 justify-between">
        {/* User menu */}
        <div className="relative" ref={userMenuRef}>
          <button
            onClick={() => setShowUserMenu(v => !v)}
            className="flex size-10 shrink-0 items-center justify-center overflow-hidden rounded-full border-2 border-slate-200 dark:border-slate-700 bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400 active:scale-90 transition-transform"
          >
            <span className="material-symbols-outlined text-[24px]">person</span>
          </button>
          {showUserMenu && (
            <div className="absolute left-0 top-12 z-50 min-w-[160px] rounded-2xl bg-white dark:bg-slate-800 shadow-xl border border-slate-100 dark:border-slate-700 overflow-hidden">
              <div className="px-4 py-3 border-b border-slate-100 dark:border-slate-700">
                <p className="text-xs text-slate-400 dark:text-slate-500">Sesión iniciada como</p>
                <p className="text-sm font-bold text-slate-800 dark:text-slate-100 truncate">{username}</p>
              </div>
              <button
                onClick={() => { setShowUserMenu(false); logout(); navigate('/login'); }}
                className="flex w-full items-center gap-2 px-4 py-3 text-sm text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
              >
                <span className="material-symbols-outlined text-[18px]">logout</span>
                Cerrar sesión
              </button>
            </div>
          )}
        </div>

        {/* Store picker chip */}
        <div className="flex-1 px-3">
          <button
            onClick={onOpenStorePicker}
            className="flex items-center gap-2 mb-0.5 active:opacity-70 transition-opacity"
          >
            <div
              className="w-2.5 h-2.5 rounded-full shrink-0"
              style={{ backgroundColor: selectedStore && STORE_META[selectedStore] ? STORE_META[selectedStore].color : '#00f076' }}
            />
            <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
              {selectedStore && STORE_META[selectedStore] ? STORE_META[selectedStore].name : 'Todas las tiendas'}
            </span>
            <span className="material-symbols-outlined text-slate-400 dark:text-slate-500 text-[14px]">expand_more</span>
          </button>
          <h2 className="text-slate-900 dark:text-white text-lg font-bold leading-tight tracking-tight">
            {selectedStore && STORE_META[selectedStore]
              ? `Ofertas en ${STORE_META[selectedStore].name}`
              : 'Mejores Ofertas'}
          </h2>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-2">
          <button
            onClick={toggleTheme}
            className="flex size-10 items-center justify-center rounded-full bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 transition-all active:scale-90"
          >
            <span className="material-symbols-outlined">
              {theme === 'dark' ? 'light_mode' : 'dark_mode'}
            </span>
          </button>
          <button
            onClick={() => navigate('/notifications')}
            className="relative flex size-10 items-center justify-center rounded-full bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300"
          >
            <span className="material-symbols-outlined">notifications</span>
            {notifications.length > 0 && (
              <span className="absolute top-2 right-2 flex h-2 w-2 rounded-full bg-primary animate-pulse" />
            )}
          </button>
        </div>
      </div>

      {/* Search bar */}
      <div className="px-4 py-3">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            const q = (e.currentTarget.elements.namedItem('search') as HTMLInputElement).value;
            if (q) navigate(`/search?q=${q}${selectedStore ? `&store=${selectedStore}` : ''}`);
          }}
          data-tour="search"
          className="flex w-full items-stretch rounded-xl h-12 shadow-sm bg-white"
          style={theme === 'dark' ? { backgroundColor: 'var(--store-surface-dark)' } : undefined}
        >
          <div className="text-primary flex items-center justify-center pl-4">
            <span className="material-symbols-outlined">search</span>
          </div>
          <input
            name="search"
            className="flex-1 flex items-center px-4 pl-2 text-slate-900 dark:text-white bg-transparent border-none focus:ring-0 placeholder:text-slate-400 dark:placeholder:text-[#9db9a8] text-base font-normal"
            placeholder="Buscar productos o marcas..."
          />
          <button type="submit" className="flex items-center pr-3">
            <span className="material-symbols-outlined text-primary">arrow_forward</span>
          </button>
        </form>
      </div>
    </header>
  );
};

export default HomeHeader;

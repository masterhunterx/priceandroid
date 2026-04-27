import React from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useCart } from '../context/CartContext';
import { useTheme } from '../context/ThemeContext';

const BottomNav: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { itemCount } = useCart();
  const { theme } = useTheme();

  const navItems = [
    { name: 'Inicio',    path: '/',          icon: 'home' },
    { name: 'Buscar',    path: '/search',     icon: 'search' },
    { name: 'Categorías', path: '/categories', icon: 'grid_view', isCentral: true },
    { name: 'Favoritos', path: '/favorites',  icon: 'favorite' },
    { name: 'Carro',     path: '/cart',       icon: 'shopping_cart', badge: itemCount },
  ];

  const isActive = (path: string) => location.pathname === path;

  return (
    <nav
      className="fixed bottom-0 left-0 right-0 z-40 backdrop-blur-3xl glass-premium border-t border-slate-200 dark:border-white/5 pb-safe shadow-2xl"
      style={{ backgroundColor: theme === 'dark' ? 'var(--store-nav-bg-dark)' : 'rgba(255,255,255,0.72)' }}
    >
      <div className="max-w-md mx-auto flex items-center justify-between h-20 px-2 lg:px-6 relative">
        {navItems.map((item) => (
          <button
            key={item.path}
            onClick={() => navigate(item.path)}
            className={`flex flex-col items-center justify-center gap-1 transition-all flex-1 h-full active:scale-90 ${
              item.isCentral ? 'relative -top-4 shrink-0' : ''
            } ${isActive(item.path) ? '' : 'text-slate-400 dark:text-slate-500'}`}
            style={isActive(item.path) && !item.isCentral ? { color: 'var(--store-primary)' } : undefined}
          >
            {item.isCentral ? (
              <div
                data-tour="categories"
                className="size-14 rounded-full flex items-center justify-center border-4 border-white"
                style={{
                  backgroundColor: isActive(item.path) ? '#ffffff' : 'var(--store-primary)',
                  color: isActive(item.path) ? 'var(--store-primary)' : 'var(--store-primary-text)',
                  borderColor: theme === 'dark' ? 'var(--store-bg-dark)' : '#ffffff',
                  boxShadow: '0 4px 20px var(--store-gradient)',
                  transform: isActive(item.path) ? 'scale(1.10)' : undefined,
                }}
              >
                <span className="material-symbols-outlined text-3xl font-black">{item.icon}</span>
              </div>
            ) : (
              <>
                <div className="relative">
                  <span className={`material-symbols-outlined ${isActive(item.path) ? 'fill-1' : ''}`}>{item.icon}</span>
                  {item.badge != null && item.badge > 0 && (
                    <span
                    className="absolute -top-1.5 -right-2 text-[9px] font-black min-w-[16px] h-4 rounded-full flex items-center justify-center px-1"
                    style={{ backgroundColor: 'var(--store-primary)', color: 'var(--store-primary-text)' }}
                  >
                      {item.badge}
                    </span>
                  )}
                </div>
                <span className="text-[10px] font-bold">{item.name}</span>
              </>
            )}
          </button>
        ))}
      </div>
    </nav>
  );
};

export default BottomNav;

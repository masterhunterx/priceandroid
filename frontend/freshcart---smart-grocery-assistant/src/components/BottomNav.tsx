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
      className="fixed bottom-0 left-0 right-0 z-40 bg-white dark:bg-black border-t border-gray-100 dark:border-zinc-900 pb-safe"
    >
      <div className="max-w-md mx-auto flex items-center justify-between h-16 px-2 relative">
        {navItems.map((item) => (
          <button
            key={item.path}
            onClick={() => navigate(item.path)}
            className={`flex flex-col items-center justify-center gap-0.5 flex-1 h-full active:scale-90 transition-all ${
              item.isCentral ? 'relative -top-5 shrink-0' : ''
            }`}
          >
            {item.isCentral ? (
              <div
                data-tour="categories"
                className="size-14 rounded-full flex items-center justify-center border-4"
                style={{
                  backgroundColor: isActive(item.path) ? (theme === 'dark' ? '#ffffff' : '#000000') : 'var(--store-primary)',
                  color: isActive(item.path) ? (theme === 'dark' ? '#000000' : '#ffffff') : 'var(--store-primary-text)',
                  borderColor: theme === 'dark' ? '#000000' : '#ffffff',
                  boxShadow: isActive(item.path) ? 'none' : '0 4px 16px rgba(0,0,0,0.12)',
                }}
              >
                <span className="material-symbols-outlined text-3xl">{item.icon}</span>
              </div>
            ) : (
              <>
                <div className="relative">
                  <span
                    className={`material-symbols-outlined ${isActive(item.path) ? 'fill-1' : ''}`}
                    style={{ color: isActive(item.path) ? (theme === 'dark' ? '#ffffff' : '#000000') : (theme === 'dark' ? '#52525b' : '#9ca3af') }}
                  >
                    {item.icon}
                  </span>
                  {item.badge != null && item.badge > 0 && (
                    <span className="absolute -top-1.5 -right-2 text-[9px] font-black min-w-[16px] h-4 rounded-full flex items-center justify-center px-1 bg-black dark:bg-white text-white dark:text-black">
                      {item.badge}
                    </span>
                  )}
                </div>
                <span
                  className="text-[10px] font-bold"
                  style={{ color: isActive(item.path) ? (theme === 'dark' ? '#ffffff' : '#000000') : (theme === 'dark' ? '#52525b' : '#9ca3af') }}
                >
                  {item.name}
                </span>
              </>
            )}
          </button>
        ))}
      </div>
    </nav>
  );
};

export default BottomNav;

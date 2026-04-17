import React, { createContext, useContext, useState, useEffect } from 'react';

export interface CartItem {
  sp_id: number;
  name: string;
  brand: string;
  price: number;
  store: string;
  store_slug: string;
  image_url: string;
  qty: number;
  total: number;
  status: 'found' | 'not_found';
  query?: string;
}

export interface SavedCart {
  store: string;
  store_slug: string;
  emoji: string;
  items: CartItem[];
  total_cost: number;
  added_at: string;
}

interface CartContextType {
  cart: SavedCart | null;
  itemCount: number;
  addToCart: (plan: any) => void;
  clearCart: () => void;
}

const CartContext = createContext<CartContextType>({
  cart: null,
  itemCount: 0,
  addToCart: () => {},
  clearCart: () => {},
});

export const useCart = () => useContext(CartContext);

const CART_KEY = 'freshcart_kairos_cart';

export const CartProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [cart, setCart] = useState<SavedCart | null>(() => {
    try {
      const saved = localStorage.getItem(CART_KEY);
      return saved ? JSON.parse(saved) : null;
    } catch {
      return null;
    }
  });

  useEffect(() => {
    if (cart) {
      localStorage.setItem(CART_KEY, JSON.stringify(cart));
    } else {
      localStorage.removeItem(CART_KEY);
    }
  }, [cart]);

  const itemCount = cart ? cart.items.filter(i => i.status === 'found').length : 0;

  const addToCart = (plan: any) => {
    const newCart: SavedCart = {
      store:      plan.store,
      store_slug: plan.store_slug,
      emoji:      plan.emoji,
      items:      plan.items as CartItem[],
      total_cost: plan.total_cost,
      added_at:   new Date().toISOString(),
    };
    setCart(newCart);
  };

  const clearCart = () => setCart(null);

  return (
    <CartContext.Provider value={{ cart, itemCount, addToCart, clearCart }}>
      {children}
    </CartContext.Provider>
  );
};

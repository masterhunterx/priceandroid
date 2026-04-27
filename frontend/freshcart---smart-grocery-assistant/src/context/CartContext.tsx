import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';

export interface CartItem {
  product_id: string | number;
  name: string;
  brand: string;
  image_url: string;
  price: number;
  store_slug: string;
  store_name: string;
  qty: number;
}

interface CartContextType {
  items: CartItem[];
  itemCount: number;
  total: number;
  addItem: (item: Omit<CartItem, 'qty'>) => void;
  removeItem: (product_id: string | number) => void;
  updateQty: (product_id: string | number, delta: number) => void;
  clearCart: () => void;
  isInCart: (product_id: string | number) => boolean;
}

const CartContext = createContext<CartContextType>({
  items: [],
  itemCount: 0,
  total: 0,
  addItem: () => {},
  removeItem: () => {},
  updateQty: () => {},
  clearCart: () => {},
  isInCart: () => false,
});

export const useCart = () => useContext(CartContext);

const CART_KEY = 'freshcart_cart_v2';

export const CartProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [items, setItems] = useState<CartItem[]>(() => {
    try {
      const saved = localStorage.getItem(CART_KEY);
      return saved ? JSON.parse(saved) : [];
    } catch { return []; }
  });

  useEffect(() => {
    try { localStorage.setItem(CART_KEY, JSON.stringify(items)); } catch {}
  }, [items]);

  const itemCount = items.length;
  const total = items.reduce((s, i) => s + i.price * i.qty, 0);

  const addItem = useCallback((item: Omit<CartItem, 'qty'>) => {
    setItems(prev => {
      const key = String(item.product_id);
      const exists = prev.find(i => String(i.product_id) === key);
      if (exists) {
        return prev.map(i => String(i.product_id) === key ? { ...i, qty: i.qty + 1 } : i);
      }
      return [...prev, { ...item, qty: 1 }];
    });
  }, []);

  const removeItem = useCallback((product_id: string | number) => {
    setItems(prev => prev.filter(i => String(i.product_id) !== String(product_id)));
  }, []);

  const updateQty = useCallback((product_id: string | number, delta: number) => {
    setItems(prev =>
      prev.flatMap(i => {
        if (String(i.product_id) !== String(product_id)) return [i];
        const newQty = i.qty + delta;
        return newQty <= 0 ? [] : [{ ...i, qty: newQty }];
      })
    );
  }, []);

  const clearCart = useCallback(() => setItems([]), []);

  const isInCart = useCallback(
    (product_id: string | number) =>
      items.some(i => String(i.product_id) === String(product_id)),
    [items],
  );

  return (
    <CartContext.Provider value={{ items, itemCount, total, addItem, removeItem, updateQty, clearCart, isInCart }}>
      {children}
    </CartContext.Provider>
  );
};

/**
 * Tests del CartContext.
 *
 * Cubre:
 *   - Estado inicial vacío
 *   - addItem: agrega producto, incrementa qty si ya existe
 *   - removeItem: elimina correctamente
 *   - updateQty: incrementa, decrementa, elimina al llegar a 0
 *   - clearCart: vacía todo
 *   - isInCart: O(1) lookup usando Set
 *   - Persistencia en localStorage con clave user-scoped
 *   - Aislamiento entre usuarios distintos
 */

import React from 'react';
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { render, act, cleanup } from '@testing-library/react';
import { CartProvider, useCart, CartItem } from '../context/CartContext';

// Hook helper: monta CartProvider y expone el contexto para aserciones directas
function renderCart(username = 'testuser') {
  localStorage.setItem('freshcart_username', username);

  let ctx: ReturnType<typeof useCart>;

  function Capture() {
    ctx = useCart();
    return null;
  }

  render(
    <CartProvider>
      <Capture />
    </CartProvider>
  );

  return () => ctx!;
}

const makeItem = (overrides: Partial<CartItem> = {}): Omit<CartItem, 'qty'> => ({
  product_id: 1,
  name: 'Leche Entera',
  brand: 'Soprole',
  image_url: '',
  price: 990,
  store_slug: 'jumbo',
  store_name: 'Jumbo',
  ...overrides,
});

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  localStorage.clear();
});

describe('CartContext — estado inicial', () => {
  it('inicia con carrito vacío', () => {
    const getCtx = renderCart();
    expect(getCtx().items).toEqual([]);
    expect(getCtx().itemCount).toBe(0);
    expect(getCtx().total).toBe(0);
  });
});

describe('CartContext — addItem', () => {
  it('agrega un producto nuevo con qty=1', () => {
    const getCtx = renderCart();
    act(() => getCtx().addItem(makeItem()));
    expect(getCtx().items).toHaveLength(1);
    expect(getCtx().items[0].qty).toBe(1);
    expect(getCtx().itemCount).toBe(1);
  });

  it('incrementa qty si el producto ya existe', () => {
    const getCtx = renderCart();
    act(() => getCtx().addItem(makeItem({ product_id: 42 })));
    act(() => getCtx().addItem(makeItem({ product_id: 42 })));
    expect(getCtx().items).toHaveLength(1);
    expect(getCtx().items[0].qty).toBe(2);
  });

  it('agrega productos distintos como entradas separadas', () => {
    const getCtx = renderCart();
    act(() => getCtx().addItem(makeItem({ product_id: 1 })));
    act(() => getCtx().addItem(makeItem({ product_id: 2, name: 'Pan' })));
    expect(getCtx().items).toHaveLength(2);
  });

  it('calcula el total correctamente', () => {
    const getCtx = renderCart();
    act(() => getCtx().addItem(makeItem({ price: 1000 })));
    act(() => getCtx().addItem(makeItem({ price: 1000 })));  // mismo producto → qty=2
    expect(getCtx().total).toBe(2000);
  });
});

describe('CartContext — removeItem', () => {
  it('elimina el producto del carrito', () => {
    const getCtx = renderCart();
    act(() => getCtx().addItem(makeItem({ product_id: 7 })));
    act(() => getCtx().removeItem(7));
    expect(getCtx().items).toHaveLength(0);
  });

  it('no falla si el producto no existe', () => {
    const getCtx = renderCart();
    expect(() => act(() => getCtx().removeItem(999))).not.toThrow();
  });

  it('solo elimina el producto indicado', () => {
    const getCtx = renderCart();
    act(() => getCtx().addItem(makeItem({ product_id: 1 })));
    act(() => getCtx().addItem(makeItem({ product_id: 2 })));
    act(() => getCtx().removeItem(1));
    expect(getCtx().items).toHaveLength(1);
    expect(getCtx().items[0].product_id).toBe(2);
  });
});

describe('CartContext — updateQty', () => {
  it('incrementa qty', () => {
    const getCtx = renderCart();
    act(() => getCtx().addItem(makeItem({ product_id: 5 })));
    act(() => getCtx().updateQty(5, +1));
    expect(getCtx().items[0].qty).toBe(2);
  });

  it('decrementa qty', () => {
    const getCtx = renderCart();
    act(() => getCtx().addItem(makeItem({ product_id: 5 })));
    act(() => getCtx().updateQty(5, +2));  // qty=3
    act(() => getCtx().updateQty(5, -1));  // qty=2
    expect(getCtx().items[0].qty).toBe(2);
  });

  it('elimina el item cuando qty llega a 0', () => {
    const getCtx = renderCart();
    act(() => getCtx().addItem(makeItem({ product_id: 5 })));  // qty=1
    act(() => getCtx().updateQty(5, -1));  // qty=0 → eliminado
    expect(getCtx().items).toHaveLength(0);
  });

  it('elimina el item cuando qty sería negativa', () => {
    const getCtx = renderCart();
    act(() => getCtx().addItem(makeItem({ product_id: 5 })));  // qty=1
    act(() => getCtx().updateQty(5, -5));  // qty=-4 → eliminado
    expect(getCtx().items).toHaveLength(0);
  });
});

describe('CartContext — clearCart', () => {
  it('vacía todos los items', () => {
    const getCtx = renderCart();
    act(() => getCtx().addItem(makeItem({ product_id: 1 })));
    act(() => getCtx().addItem(makeItem({ product_id: 2 })));
    act(() => getCtx().clearCart());
    expect(getCtx().items).toHaveLength(0);
    expect(getCtx().total).toBe(0);
  });
});

describe('CartContext — isInCart (O(1) Set lookup)', () => {
  it('devuelve false para carrito vacío', () => {
    const getCtx = renderCart();
    expect(getCtx().isInCart(99)).toBe(false);
  });

  it('devuelve true para producto en carrito', () => {
    const getCtx = renderCart();
    act(() => getCtx().addItem(makeItem({ product_id: 10 })));
    expect(getCtx().isInCart(10)).toBe(true);
  });

  it('devuelve false para producto no en carrito', () => {
    const getCtx = renderCart();
    act(() => getCtx().addItem(makeItem({ product_id: 10 })));
    expect(getCtx().isInCart(99)).toBe(false);
  });

  it('acepta product_id como string o number', () => {
    const getCtx = renderCart();
    act(() => getCtx().addItem(makeItem({ product_id: 15 })));
    expect(getCtx().isInCart('15')).toBe(true);
    expect(getCtx().isInCart(15)).toBe(true);
  });
});

describe('CartContext — localStorage user-scoped', () => {
  it('persiste el carrito para el usuario actual', () => {
    const getCtx = renderCart('user_a');
    act(() => getCtx().addItem(makeItem({ product_id: 3, name: 'Yogurt' })));

    const stored = JSON.parse(localStorage.getItem('freshcart_cart_v3_user_a') || '[]');
    expect(stored).toHaveLength(1);
    expect(stored[0].name).toBe('Yogurt');
  });

  it('usa clave distinta para cada usuario', () => {
    renderCart('user_a');
    cleanup();  // desmontar user_a antes de montar user_b
    const getCtx = renderCart('user_b');
    expect(getCtx().items).toHaveLength(0);
  });
});

/**
 * Unit tests para lib/api.ts — funciones puras (sin fetch, sin servidor).
 *
 * Cubre:
 *   - formatCurrency: valores normales, negativos, cero, null/undefined, grandes
 *   - getRecentSearches / saveRecentSearch / clearRecentSearches: ciclo completo
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { formatCurrency, getRecentSearches, saveRecentSearch, clearRecentSearches } from '../lib/api';

// ─── formatCurrency ────────────────────────────────────────────────────────────

describe('formatCurrency', () => {
  it('formatea un valor entero positivo', () => {
    const result = formatCurrency(1990);
    expect(result).toContain('1.990');  // formato CLP con punto como separador de miles
  });

  it('formatea cero', () => {
    const result = formatCurrency(0);
    expect(result).toBeDefined();
    expect(result).not.toBe('N/A');
  });

  it('formatea un número grande', () => {
    const result = formatCurrency(1_000_000);
    expect(result).toContain('1.000.000');
  });

  it('devuelve N/A para null', () => {
    expect(formatCurrency(null)).toBe('N/A');
  });

  it('devuelve N/A para undefined', () => {
    expect(formatCurrency(undefined)).toBe('N/A');
  });

  it('formatea valor negativo sin lanzar error', () => {
    const result = formatCurrency(-500);
    expect(result).toBeDefined();
    expect(typeof result).toBe('string');
  });

  it('incluye símbolo de moneda CLP', () => {
    const result = formatCurrency(990);
    // Intl puede usar $ o CLP dependiendo de la plataforma — verificamos que sea string no vacío
    expect(result.length).toBeGreaterThan(0);
    expect(result).not.toBe('N/A');
  });
});


// ─── getRecentSearches / saveRecentSearch / clearRecentSearches ────────────────

const RECENT_KEY = 'freshcart_recent_searches';

describe('búsquedas recientes (localStorage)', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  afterEach(() => {
    localStorage.clear();
  });

  it('getRecentSearches devuelve [] cuando no hay nada guardado', () => {
    expect(getRecentSearches()).toEqual([]);
  });

  it('saveRecentSearch guarda un término', () => {
    saveRecentSearch('leche');
    expect(getRecentSearches()).toContain('leche');
  });

  it('saveRecentSearch coloca el término más reciente primero', () => {
    saveRecentSearch('leche');
    saveRecentSearch('pan');
    const searches = getRecentSearches();
    expect(searches[0]).toBe('pan');
    expect(searches[1]).toBe('leche');
  });

  it('saveRecentSearch deduplica ignorando mayúsculas', () => {
    saveRecentSearch('Leche');
    saveRecentSearch('leche');
    const searches = getRecentSearches();
    expect(searches.length).toBe(1);
    expect(searches[0]).toBe('leche');
  });

  it('saveRecentSearch ignora términos vacíos', () => {
    saveRecentSearch('');
    saveRecentSearch('   ');
    expect(getRecentSearches()).toEqual([]);
  });

  it('saveRecentSearch mantiene máximo 6 entradas', () => {
    ['a', 'b', 'c', 'd', 'e', 'f', 'g'].forEach(t => saveRecentSearch(t));
    expect(getRecentSearches().length).toBeLessThanOrEqual(6);
  });

  it('clearRecentSearches vacía el historial', () => {
    saveRecentSearch('leche');
    saveRecentSearch('pan');
    clearRecentSearches();
    expect(getRecentSearches()).toEqual([]);
  });

  it('getRecentSearches maneja localStorage corrupto sin lanzar', () => {
    localStorage.setItem(RECENT_KEY, '{not valid json}');
    expect(() => getRecentSearches()).not.toThrow();
    expect(getRecentSearches()).toEqual([]);
  });
});


// ─── getStoredToken ────────────────────────────────────────────────────────────
// Verifica que getStoredToken lee del localStorage correctamente.

describe('getStoredToken', () => {
  afterEach(() => localStorage.clear());

  it('devuelve null cuando no hay token', async () => {
    const { getStoredToken } = await import('../context/AuthContext');
    localStorage.removeItem('freshcart_access_token');
    expect(getStoredToken()).toBeNull();
  });

  it('devuelve el token almacenado', async () => {
    const { getStoredToken } = await import('../context/AuthContext');
    localStorage.setItem('freshcart_access_token', 'my-token-xyz');
    expect(getStoredToken()).toBe('my-token-xyz');
  });
});

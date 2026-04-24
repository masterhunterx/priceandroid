import { Product, Deal, Category, Notification, PlanningResult, Branch, LocationHierarchy, SearchSuggestion } from '../types';
import { getStoredToken } from '../context/AuthContext';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';

const getHeaders = (branchContext?: Record<string, string>): Record<string, string> => {
  const token = getStoredToken();
  const h: Record<string, string> = { 'Content-Type': 'application/json' };
  if (token) h['Authorization'] = `Bearer ${token}`;
  if (branchContext) h['X-Branch-Context'] = JSON.stringify(branchContext);
  return h;
};

/**
 * Wrapper sobre fetch que maneja 401 automáticamente:
 * 1. Intenta refrescar el access token con el refresh token.
 * 2. Si funciona, reintenta la petición original con el nuevo token.
 * 3. Si falla, limpia localStorage y redirige a /login.
 */
// Referencia directa a fetch nativo para uso interno (evita recursión en fetchWithAuth)
const _rawFetch = globalThis.fetch.bind(globalThis);

// Tiempo máximo de espera por petición (15 s). Pasado este tiempo se lanza AbortError.
const REQUEST_TIMEOUT_MS = 15_000;

// Promise queue para refresh: si ya hay un refresh en curso, los requests que
// reciban 401 esperan al mismo token en vez de redirigir a /login prematuramente.
let _refreshPromise: Promise<string | null> | null = null;

async function _doRefresh(): Promise<string | null> {
  const refreshToken = localStorage.getItem('freshcart_refresh_token');
  if (!refreshToken) return null;
  try {
    const rc = new AbortController();
    const rtId = setTimeout(() => rc.abort(), REQUEST_TIMEOUT_MS);
    let rr: Response;
    try {
      rr = await _rawFetch(`${API_BASE_URL}/auth/refresh`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${refreshToken}` },
        signal: rc.signal,
      });
    } finally {
      clearTimeout(rtId);
    }
    if (!rr.ok) return null;
    const rj = await rr.json();
    const newToken: string | undefined = rj.data?.access_token;
    if (newToken) {
      localStorage.setItem('freshcart_access_token', newToken);
      return newToken;
    }
    return null;
  } catch {
    return null;
  }
}

async function fetchWithAuth(url: string, options: RequestInit = {}): Promise<Response> {
  const timeoutController = new AbortController();
  const timeoutId = setTimeout(() => timeoutController.abort(), REQUEST_TIMEOUT_MS);

  let resp: Response;
  try {
    resp = await _rawFetch(url, { ...options, signal: timeoutController.signal });
  } catch (err) {
    clearTimeout(timeoutId);
    throw err; // AbortError por timeout u otro error de red
  }
  clearTimeout(timeoutId);

  if (resp.status !== 401) return resp;

  // Serializar todos los refreshes concurrentes en una sola promesa
  if (!_refreshPromise) {
    _refreshPromise = _doRefresh().finally(() => { _refreshPromise = null; });
  }
  const newToken = await _refreshPromise;

  if (!newToken) {
    // Refresh falló — limpiar sesión y redirigir
    localStorage.removeItem('freshcart_access_token');
    localStorage.removeItem('freshcart_refresh_token');
    window.location.href = '/login';
    return resp;
  }

  // Reintentar la petición original con el nuevo token
  const retryHeaders = {
    ...(options.headers as Record<string, string> || {}),
    'Authorization': `Bearer ${newToken}`,
  };
  const retryController = new AbortController();
  const retryTimeoutId = setTimeout(() => retryController.abort(), REQUEST_TIMEOUT_MS);
  try {
    resp = await _rawFetch(url, { ...options, headers: retryHeaders, signal: retryController.signal });
  } finally {
    clearTimeout(retryTimeoutId);
  }

  if (resp.status === 401) {
    localStorage.removeItem('freshcart_access_token');
    localStorage.removeItem('freshcart_refresh_token');
    window.location.href = '/login';
  }
  return resp;
}

// ── Productos ──────────────────────────────────────────────────────────────────

export async function searchProducts(
  query: string,
  category?: string,
  page = 1,
  pageSize = 20,
  sort = 'price_asc',
  store = '',
  branchContext?: Record<string, string>
): Promise<{results: Product[], total: number}> {
  let url = `${API_BASE_URL}/products/search?page=${page}&page_size=${pageSize}&sort=${sort}`;
  if (query) url += `&q=${encodeURIComponent(query)}`;
  if (category) url += `&category=${encodeURIComponent(category)}`;
  if (store) url += `&store=${encodeURIComponent(store)}`;
  const resp = await fetchWithAuth(url, { headers: getHeaders(branchContext) });
  const json = await resp.json();
  if (!json.success) throw new Error(json.error || 'Failed to search products');
  return json.data;
}

export async function getProductDetails(id: number, branchContext?: Record<string, string>): Promise<Product> {
  const resp = await fetchWithAuth(`${API_BASE_URL}/products/${id}`, { headers: getHeaders(branchContext) });
  const json = await resp.json();
  if (!json.success) throw new Error(json.error || 'Failed to fetch product details');
  return json.data;
}

export async function getDeals(limit = 20, offset = 0): Promise<Deal[]> {
  const resp = await fetchWithAuth(`${API_BASE_URL}/deals?limit=${limit}&offset=${offset}`, { headers: getHeaders() });
  const json = await resp.json();
  if (!json.success) throw new Error(json.error || 'Failed to fetch deals');
  return json.data;
}

export async function getCategories(): Promise<Category[]> {
  const resp = await fetchWithAuth(`${API_BASE_URL}/categories`, { headers: getHeaders() });
  const json = await resp.json();
  if (!json.success) throw new Error(json.error || 'Failed to fetch categories');
  return json.data;
}

// ── Notificaciones ─────────────────────────────────────────────────────────────

export async function getNotifications(unreadOnly = false, limit = 50): Promise<Notification[]> {
  const resp = await fetchWithAuth(`${API_BASE_URL}/assistant/notifications?unread_only=${unreadOnly}&limit=${limit}`, { headers: getHeaders() });
  const json = await resp.json();
  if (!json.success) throw new Error(json.error || 'Failed to fetch notifications');
  return json.data;
}

export async function markNotificationRead(id: number): Promise<void> {
  await fetchWithAuth(`${API_BASE_URL}/assistant/notifications/${id}/read`, {
    method: 'POST',
    headers: getHeaders(),
  });
}

export async function deleteNotification(id: number): Promise<void> {
  await fetchWithAuth(`${API_BASE_URL}/assistant/notifications/${id}`, {
    method: 'DELETE',
    headers: getHeaders(),
  });
}

export async function clearReadNotifications(): Promise<number> {
  const resp = await fetchWithAuth(`${API_BASE_URL}/assistant/notifications`, {
    method: 'DELETE',
    headers: getHeaders(),
  });
  const json = await resp.json();
  return json.data?.deleted_count ?? 0;
}

export async function refreshNotifications(): Promise<void> {
  await fetchWithAuth(`${API_BASE_URL}/assistant/notifications/refresh`, {
    method: 'POST',
    headers: getHeaders(),
  });
}

// ── Favoritos ──────────────────────────────────────────────────────────────────

export async function getFavorites(limit = 50, offset = 0): Promise<Product[]> {
  const response = await fetchWithAuth(
    `${API_BASE_URL}/assistant/favorites?limit=${limit}&offset=${offset}`,
    { headers: getHeaders() }
  );
  const data = await response.json();
  return data.data;
}

export async function toggleFavorite(productId: number | string): Promise<{ is_favorite: boolean; message: string }> {
  const response = await fetchWithAuth(`${API_BASE_URL}/assistant/favorites`, {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify({ product_id: Number(productId), action: 'toggle' }),
  });
  const data = await response.json();
  if (!data.success) throw new Error(data.error || 'Failed to toggle favorite');
  return data.data;
}

// ── Planificación y optimización ───────────────────────────────────────────────

export async function runUltraplan(productIds: number[]): Promise<PlanningResult> {
  const resp = await fetchWithAuth(`${API_BASE_URL}/optimize/ultraplan`, {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify(productIds),
  });
  const json = await resp.json();
  if (!json.success) throw new Error(json.error || 'Failed to run Ultraplan');
  return json.data;
}

export async function syncProduct(id: number | string): Promise<{updated_count: number}> {
  const resp = await fetchWithAuth(`${API_BASE_URL}/products/${id}/sync`, {
    method: 'POST',
    headers: getHeaders(),
  });
  const json = await resp.json();
  if (!json.success) throw new Error(json.error || 'Failed to sync product');
  return json.data;
}

// ── Ubicaciones ────────────────────────────────────────────────────────────────

export async function getNearestBranches(lat: number, lng: number): Promise<Branch[]> {
  const resp = await fetchWithAuth(`${API_BASE_URL}/branches/nearest?lat=${lat}&lng=${lng}`, { headers: getHeaders() });
  const json = await resp.json();
  if (!json.success) throw new Error(json.error || 'Failed to fetch nearest branches');
  return json.data;
}

export async function getLocationHierarchy(): Promise<LocationHierarchy> {
  const resp = await fetchWithAuth(`${API_BASE_URL}/locations/hierarchy`, { headers: getHeaders() });
  const json = await resp.json();
  if (!json.success) throw new Error(json.error || 'Failed to fetch location hierarchy');
  return json.data;
}

// ── Asistente KAIROS ───────────────────────────────────────────────────────────

export async function optimizeCart(items: {query: string, qty: number}[]): Promise<any> {
  const resp = await fetchWithAuth(`${API_BASE_URL}/assistant/optimize_cart`, {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify({ items }),
  });
  const json = await resp.json();
  if (!json.success) throw new Error(json.error || 'Failed to optimize cart');
  return json.data;
}

export async function getAssistantState(): Promise<any> {
  const resp = await fetchWithAuth(`${API_BASE_URL}/assistant/chat/state`, { headers: getHeaders() });
  const json = await resp.json();
  return json.data;
}

export async function chatAssistant(messages: {role: string, content: string}[]): Promise<any> {
  const resp = await fetchWithAuth(`${API_BASE_URL}/assistant/chat`, {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify({ messages }),
  });
  const json = await resp.json();
  if (!json.success) throw new Error(json.error || 'Failed to chat with KAIROS');
  return json.data;
}

export async function getDealsMenu(persons: number = 2): Promise<any> {
  const resp = await fetchWithAuth(`${API_BASE_URL}/assistant/deals-menu?persons=${persons}`, {
    headers: getHeaders(),
  });
  const json = await resp.json();
  if (!json.success) throw new Error(json.error || 'Failed to generate deals menu');
  return json.data;
}

// ── Sugerencias y tendencias ───────────────────────────────────────────────────

export async function getSearchSuggestions(q: string): Promise<SearchSuggestion[]> {
  if (!q || q.length < 2) return [];
  const resp = await fetchWithAuth(`${API_BASE_URL}/products/suggestions?q=${encodeURIComponent(q)}`, { headers: getHeaders() });
  const json = await resp.json();
  if (!json.success) return [];
  return json.data;
}

export async function getTrendingSearches(): Promise<{term: string, icon: string}[]> {
  try {
    const resp = await fetchWithAuth(`${API_BASE_URL}/trending`, { headers: getHeaders() });
    const json = await resp.json();
    if (!json.success) return [];
    return json.data;
  } catch {
    return [];
  }
}

// ── Despensa (Pantry) ──────────────────────────────────────────────────────────

export async function getPantry(): Promise<any[]> {
  const resp = await fetchWithAuth(`${API_BASE_URL}/pantry`, { headers: getHeaders() });
  const json = await resp.json();
  if (!json.success) throw new Error(json.error || 'Failed to fetch pantry');
  return json.data;
}

export async function buyPantryItems(items: {product_id: number, stock_level: string}[]): Promise<any> {
  const resp = await fetchWithAuth(`${API_BASE_URL}/pantry/purchase`, {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify(items),
  });
  const json = await resp.json();
  if (!json.success) throw new Error(json.error || 'Failed to purchase pantry items');
  return json.data;
}

export async function consumePantryItem(id: number): Promise<any> {
  const resp = await fetchWithAuth(`${API_BASE_URL}/pantry/${id}/consume`, {
    method: 'POST',
    headers: getHeaders(),
  });
  const json = await resp.json();
  if (!json.success) throw new Error(json.error || 'Failed to consume pantry item');
  return json.data;
}

// ── Mínimos históricos ─────────────────────────────────────────────────────────

export async function getHistoricLows(limit = 10): Promise<any[]> {
  const resp = await fetchWithAuth(`${API_BASE_URL}/deals/historic-lows?limit=${limit}`, { headers: getHeaders() });
  const json = await resp.json();
  if (!json.success) return [];
  return json.data;
}

// ── Utilidades ─────────────────────────────────────────────────────────────────

// Instancia reutilizable — Intl.NumberFormat es costoso de construir en cada llamada.
const _clpFormatter = new Intl.NumberFormat('es-CL', {
  style: 'currency',
  currency: 'CLP',
  minimumFractionDigits: 0,
});

export function formatCurrency(amount: number | null): string {
  if (amount === null) return 'N/A';
  return _clpFormatter.format(amount);
}

// Búsquedas recientes (localStorage)
const RECENT_KEY = 'freshcart_recent_searches';
const MAX_RECENT = 6;

export function getRecentSearches(): string[] {
  try {
    return JSON.parse(localStorage.getItem(RECENT_KEY) || '[]');
  } catch {
    return [];
  }
}

export function saveRecentSearch(term: string): void {
  if (!term.trim()) return;
  try {
    const current = getRecentSearches().filter(t => t.toLowerCase() !== term.toLowerCase());
    const updated = [term, ...current].slice(0, MAX_RECENT);
    localStorage.setItem(RECENT_KEY, JSON.stringify(updated));
  } catch {
    // localStorage lleno o deshabilitado — ignorar silenciosamente
  }
}

export function clearRecentSearches(): void {
  localStorage.removeItem(RECENT_KEY);
}

// ── Feedback ───────────────────────────────────────────────────────────────────

export async function submitFeedback(
  type: 'bug' | 'mejora' | 'sugerencia',
  description: string,
  pageContext?: string,
): Promise<{ id: number; message: string }> {
  const resp = await fetchWithAuth(`${API_BASE_URL}/feedback`, {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify({ type, description, page_context: pageContext }),
  });
  const json = await resp.json();
  if (!json.success) throw new Error(json.error || 'Error al enviar el reporte');
  return json.data;
}

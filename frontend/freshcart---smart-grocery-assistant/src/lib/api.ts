import { Product, Deal, Category, Notification, PlanningResult, Branch, LocationHierarchy, SearchSuggestion, HistoricLow } from '../types';
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
  } catch (err: any) {
    clearTimeout(timeoutId);
    if (err?.name === 'AbortError') {
      throw new Error('La conexión tardó demasiado. Verifica tu internet e intenta de nuevo.');
    }
    throw err;
  }
  clearTimeout(timeoutId);

  if (resp.status !== 401) return resp;

  // Serializar todos los refreshes concurrentes en una sola promesa
  if (!_refreshPromise) {
    _refreshPromise = _doRefresh().finally(() => { _refreshPromise = null; });
  }
  const newToken = await _refreshPromise;

  if (!newToken) {
    // Refresh falló — limpiar sesión y notificar a la app
    localStorage.removeItem('freshcart_access_token');
    localStorage.removeItem('freshcart_refresh_token');
    window.dispatchEvent(new CustomEvent('freshcart:logout'));
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
    window.dispatchEvent(new CustomEvent('freshcart:logout'));
  }
  return resp;
}

// ── Auth ───────────────────────────────────────────────────────────────────────

export async function loginUser(username: string, password: string): Promise<{
  access_token: string; refresh_token: string; token_type: string;
  expires_in: number; role?: string; selected_store?: string; selected_branch?: string;
}> {
  const resp = await _rawFetch(`${API_BASE_URL}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  });
  const json = await resp.json();
  if (!json.success) throw new Error(json.error || json.detail || 'Login fallido');
  return json.data;
}

export async function registerUser(username: string, password: string, email?: string): Promise<{ message: string }> {
  const resp = await _rawFetch(`${API_BASE_URL}/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password, email }),
  });
  const json = await resp.json();
  if (!json.success) throw new Error(json.error || json.detail || 'Registro fallido');
  return json.data;
}

export async function getMe(): Promise<{
  username: string; role: string; email?: string;
  selected_store?: string; selected_branch?: string;
  created_at?: string; last_login_at?: string;
}> {
  const resp = await fetchWithAuth(`${API_BASE_URL}/auth/me`, { headers: getHeaders() });
  const json = await resp.json();
  if (!json.success) throw new Error(json.error || 'Error obteniendo perfil');
  return json.data;
}

export async function updateProfile(data: {
  selected_store?: string; selected_branch?: string; email?: string;
}): Promise<void> {
  const resp = await fetchWithAuth(`${API_BASE_URL}/auth/profile`, {
    method: 'PATCH',
    headers: { ...getHeaders(), 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  const json = await resp.json();
  if (!json.success) throw new Error(json.error || 'Error actualizando perfil');
}

export async function changePassword(currentPassword: string, newPassword: string): Promise<void> {
  const resp = await fetchWithAuth(`${API_BASE_URL}/auth/change-password`, {
    method: 'POST',
    headers: { ...getHeaders(), 'Content-Type': 'application/json' },
    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
  });
  const json = await resp.json();
  if (!json.success) throw new Error(json.error || 'Error cambiando contraseña');
}

export async function listUsers(): Promise<{ users: any[]; total: number }> {
  const resp = await fetchWithAuth(`${API_BASE_URL}/auth/users`, { headers: getHeaders() });
  const json = await resp.json();
  if (!json.success) throw new Error(json.error || 'Error listando usuarios');
  return json.data;
}

export async function googleLogin(credential: string): Promise<{
  access_token: string; refresh_token: string; token_type: string;
  expires_in: number; role?: string; selected_store?: string; selected_branch?: string; username: string;
}> {
  const resp = await _rawFetch(`${API_BASE_URL}/auth/google`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ credential }),
  });
  const json = await resp.json();
  if (!json.success) throw new Error(json.error || json.detail || 'Google login fallido');
  return json.data;
}

export async function forgotPassword(email: string): Promise<{ message: string }> {
  const resp = await _rawFetch(`${API_BASE_URL}/auth/forgot-password`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email }),
  });
  const json = await resp.json();
  if (!json.success) throw new Error(json.error || json.detail || 'Error al solicitar recuperación');
  return json.data;
}

export async function resetPassword(token: string, newPassword: string): Promise<{ message: string }> {
  const resp = await _rawFetch(`${API_BASE_URL}/auth/reset-password`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token, new_password: newPassword }),
  });
  const json = await resp.json();
  if (!json.success) throw new Error(json.error || json.detail || 'Error al restablecer contraseña');
  return json.data;
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

export async function getDeals(limit = 20, offset = 0, store?: string): Promise<Deal[]> {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  if (store) params.set('store', store);
  const resp = await fetchWithAuth(`${API_BASE_URL}/deals?${params}`, { headers: getHeaders() });
  const json = await resp.json();
  if (!json.success) throw new Error(json.error || 'Failed to fetch deals');
  return json.data;
}

export async function getCategories(store?: string): Promise<Category[]> {
  const params = store ? `?store=${encodeURIComponent(store)}` : '';
  const resp = await fetchWithAuth(`${API_BASE_URL}/categories${params}`, { headers: getHeaders() });
  const json = await resp.json();
  if (!json.success) throw new Error(json.error || 'Failed to fetch categories');
  return json.data;
}

// ── Notificaciones (deshabilitado — backend assistant eliminado) ───────────────

export async function getNotifications(_unreadOnly = false, _limit = 50): Promise<Notification[]> {
  return [];
}

export async function markNotificationRead(_id: number): Promise<void> {}

export async function deleteNotification(_id: number): Promise<void> {}

export async function clearReadNotifications(): Promise<number> {
  return 0;
}

export async function refreshNotifications(): Promise<void> {}

// ── Favoritos ──────────────────────────────────────────────────────────────────

export async function getFavorites(limit = 50, offset = 0): Promise<Product[]> {
  const response = await fetchWithAuth(
    `${API_BASE_URL}/assistant/favorites?limit=${limit}&offset=${offset}`,
    { headers: getHeaders() }
  );
  const data = await response.json();
  if (!data.success) return [];
  return data.data ?? [];
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
  // C3: el backend usa Body(..., embed=True) → espera {"product_ids": [...]}
  // El formato anterior (array bare) causaba 422 Unprocessable Entity.
  const resp = await fetchWithAuth(`${API_BASE_URL}/optimize/ultraplan`, {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify({ product_ids: productIds }),
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

export async function optimizeCart(items: {query: string, qty: number}[]): Promise<PlanningResult> {
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

export async function getHistoricLows(limit = 10): Promise<HistoricLow[]> {
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

export function formatCurrency(amount: number | null | undefined): string {
  if (amount == null) return 'N/A';
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

// ── Snapshots de precios ───────────────────────────────────────────────────────

const PRICE_SNAPSHOT_KEY = 'freshcart_price_snapshots';
const MAX_SNAPSHOT_ENTRIES = 50;

export interface PriceSnapshotEntry {
  price: number;
  storeSlug: string;
  storeName: string;
  name: string;
  imageUrl: string;
  savedAt: number;
}

export type PriceSnapshotMap = Record<string, PriceSnapshotEntry>;

export function readPriceSnapshots(): PriceSnapshotMap {
  try {
    return JSON.parse(localStorage.getItem(PRICE_SNAPSHOT_KEY) || '{}');
  } catch {
    return {};
  }
}

export function writePriceSnapshots(map: PriceSnapshotMap): void {
  try {
    const entries = Object.entries(map);
    if (entries.length > MAX_SNAPSHOT_ENTRIES) {
      entries.sort((a, b) => b[1].savedAt - a[1].savedAt);
      localStorage.setItem(PRICE_SNAPSHOT_KEY, JSON.stringify(Object.fromEntries(entries.slice(0, MAX_SNAPSHOT_ENTRIES))));
    } else {
      localStorage.setItem(PRICE_SNAPSHOT_KEY, JSON.stringify(map));
    }
  } catch {
    // localStorage lleno — ignorar silenciosamente
  }
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

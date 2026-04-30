import React, { createContext, useContext, useState, useCallback, useEffect } from 'react';

const ACCESS_KEY   = 'freshcart_access_token';
const REFRESH_KEY  = 'freshcart_refresh_token';
const USERNAME_KEY = 'freshcart_username';

function _decodeUsername(token: string): string | null {
  try {
    return JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/'))).sub || null;
  } catch { return null; }
}

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';

interface AuthContextType {
  token: string | null;
  username: string | null;
  isAuthenticated: boolean;
  login: (username: string, password: string) => Promise<'ok' | 'pending'>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType>(null!);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [token, setToken] = useState<string | null>(() => localStorage.getItem(ACCESS_KEY));
  const [username, setUsername] = useState<string | null>(() => {
    const stored = localStorage.getItem(USERNAME_KEY);
    if (stored) return stored;
    const t = localStorage.getItem(ACCESS_KEY);
    return t ? _decodeUsername(t) : null;
  });

  // Intenta renovar el access token usando el refresh token guardado
  const tryRefresh = useCallback(async (): Promise<string | null> => {
    const refreshToken = localStorage.getItem(REFRESH_KEY);
    if (!refreshToken) return null;

    try {
      const resp = await fetch(`${API_BASE_URL}/auth/refresh`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${refreshToken}` },
      });
      if (!resp.ok) return null;
      const json = await resp.json();
      const newToken: string = json.data?.access_token;
      if (newToken) {
        localStorage.setItem(ACCESS_KEY, newToken);
        setToken(newToken);
        return newToken;
      }
    } catch {
      // refresh falló
    }
    return null;
  }, []);

  // Al montar, verifica silenciosamente si el token sigue vigente; refresca si es necesario.
  // Usa AbortController para cancelar el fetch si el componente se desmonta antes de responder.
  useEffect(() => {
    if (!token) return;
    const controller = new AbortController();
    let cancelled = false;
    const timeoutId = setTimeout(() => controller.abort(), 10000);

    fetch(`${API_BASE_URL}/auth/me`, {
      headers: { Authorization: `Bearer ${token}` },
      signal: controller.signal,
    }).then(async (r) => {
      if (cancelled) return;
      if (r.status === 401) {
        const renewed = await tryRefresh();
        if (cancelled) return;
        if (!renewed) {
          setToken(null);
          localStorage.removeItem(ACCESS_KEY);
          localStorage.removeItem(REFRESH_KEY);
        }
      }
    }).catch((err) => {
      if (err.name !== 'AbortError') { /* sin conexión — seguir con el token guardado */ }
    }).finally(() => {
      clearTimeout(timeoutId);
    });

    return () => {
      cancelled = true;
      clearTimeout(timeoutId);
      controller.abort();
    };
  }, []); // solo al montar

  const login = useCallback(async (username: string, password: string): Promise<'ok' | 'pending'> => {
    const resp = await fetch(`${API_BASE_URL}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    });

    const json = await resp.json();

    if (resp.status === 202 && json.status === 'pending_approval') {
      return 'pending';
    }

    if (!resp.ok || !json.success) {
      throw new Error(json.detail || json.error || 'Credenciales incorrectas');
    }

    const { access_token, refresh_token, selected_store, selected_branch } = json.data;
    localStorage.setItem(ACCESS_KEY, access_token);
    localStorage.setItem(REFRESH_KEY, refresh_token);
    setToken(access_token);
    const uname = json.data.username || _decodeUsername(access_token);
    setUsername(uname);
    if (uname) localStorage.setItem(USERNAME_KEY, uname);

    // Restaurar tienda y sucursal guardadas en el servidor
    if (selected_store) {
      localStorage.setItem('selected_store', selected_store);
      window.dispatchEvent(new CustomEvent('freshcart:store_restored', { detail: { store: selected_store, branch: selected_branch } }));
    }
    if (selected_branch) {
      try { localStorage.setItem('selected_branches', selected_branch); } catch {}
    }

    return 'ok';
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem(ACCESS_KEY);
    localStorage.removeItem(REFRESH_KEY);
    localStorage.removeItem(USERNAME_KEY);
    setToken(null);
    setUsername(null);
  }, []);

  return (
    <AuthContext.Provider value={{ token, username, isAuthenticated: !!token, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => useContext(AuthContext);

/** Retorna el access token guardado (para usarlo en api.ts fuera de React) */
export const getStoredToken = (): string | null => localStorage.getItem(ACCESS_KEY);

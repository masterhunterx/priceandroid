import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { googleLogin, firebaseLogin } from '../lib/api';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';

declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize: (cfg: object) => void;
          renderButton: (el: HTMLElement, opts: object) => void;
        };
      };
    };
    onGoogleLibraryLoad?: () => void;
  }
}

const GoogleLogo = ({ size = 18 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 48 48" xmlns="http://www.w3.org/2000/svg" style={{ flexShrink: 0 }}>
    <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/>
    <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/>
    <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"/>
    <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/>
    <path fill="none" d="M0 0h48v48H0z"/>
  </svg>
);

const Login: React.FC = () => {
  const { login, setSession, enterGuestMode } = useAuth();
  const navigate = useNavigate();

  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPwd, setShowPwd] = useState(false);
  const [loginLoading, setLoginLoading] = useState(false);
  const [loginError, setLoginError] = useState('');
  const [pendingUser, setPendingUser] = useState('');
  const [pendingPwd, setPendingPwd] = useState('');
  const [googleLoading, setGoogleLoading] = useState(false);
  const [guestLoading, setGuestLoading] = useState(false);
  const [showAdmin, setShowAdmin] = useState(false);
  const [showGuestInfo, setShowGuestInfo] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const googleBtnRef = useRef<HTMLDivElement>(null);

  const isNative = !!(window as any).Capacitor?.isNativePlatform?.();
  const hasWebGoogle = !!import.meta.env.VITE_GOOGLE_CLIENT_ID && !isNative;

  const handleGoogleCredential = async (response: { credential: string }) => {
    try {
      const data = await googleLogin(response.credential);
      setSession(data.access_token, data.refresh_token, data.username);
      if (data.selected_store) {
        localStorage.setItem('selected_store', data.selected_store);
        window.dispatchEvent(new CustomEvent('freshcart:store_restored', {
          detail: { store: data.selected_store, branch: data.selected_branch }
        }));
      }
      navigate('/store-select', { replace: true });
    } catch (err: any) {
      setLoginError(err.message || 'Error al iniciar sesión con Google');
    }
  };

  useEffect(() => {
    if (!hasWebGoogle) return;
    const init = () => {
      if (!window.google?.accounts?.id || !googleBtnRef.current) return;
      window.google.accounts.id.initialize({ client_id: import.meta.env.VITE_GOOGLE_CLIENT_ID, callback: handleGoogleCredential });
      window.google.accounts.id.renderButton(googleBtnRef.current, {
        theme: 'outline', size: 'large', width: 320, locale: 'es', text: 'continue_with'
      });
    };
    if (window.google?.accounts?.id) init();
    else window.onGoogleLibraryLoad = init;
  }, []);

  const handleNativeGoogleSignIn = async () => {
    setGoogleLoading(true);
    setLoginError('');
    try {
      const { FirebaseAuthentication } = await import('@capacitor-firebase/authentication');
      await FirebaseAuthentication.signInWithGoogle();
      const { token } = await FirebaseAuthentication.getIdToken();
      if (!token) throw new Error('No se obtuvo token de Firebase');
      const data = await firebaseLogin(token);
      setSession(data.access_token, data.refresh_token, data.username);
      if (data.selected_store) {
        localStorage.setItem('selected_store', data.selected_store);
        window.dispatchEvent(new CustomEvent('freshcart:store_restored', {
          detail: { store: data.selected_store, branch: data.selected_branch }
        }));
      }
      navigate('/store-select', { replace: true });
    } catch (err: any) {
      const msg: string = err.message || '';
      if (!/cancel|dismiss|closed|no credentials/i.test(msg))
        setLoginError(msg || 'Error al iniciar sesión con Google');
    } finally {
      setGoogleLoading(false);
    }
  };

  const handleEnterGuest = async () => {
    setGuestLoading(true);
    await enterGuestMode();
    setGuestLoading(false);
    navigate('/store-select', { replace: true });
  };

  useEffect(() => {
    if (!pendingUser) return;
    let attempts = 0;
    pollRef.current = setInterval(async () => {
      try {
        const resp = await fetch(`${API_BASE_URL}/auth/approval-status/${pendingUser}`);
        const json = await resp.json();
        if (json.approved) {
          clearInterval(pollRef.current!);
          const result = await login(pendingUser, pendingPwd);
          if (result === 'ok') navigate('/store-select', { replace: true });
        }
        attempts = 0;
      } catch {
        if (++attempts >= 3) {
          clearInterval(pollRef.current!);
          setLoginError('No se pudo conectar. Intenta de nuevo.');
          setPendingUser(''); setPendingPwd('');
        }
      }
    }, 5000);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [pendingUser, pendingPwd, login, navigate]);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!username || !password) return;
    setLoginLoading(true);
    setLoginError('');
    try {
      const result = await login(username, password);
      if (result === 'ok') navigate('/store-select', { replace: true });
      else if (result === 'pending') { setPendingUser(username.trim().toLowerCase()); setPendingPwd(password); }
    } catch (err: any) {
      setLoginError(err.message || 'Error al iniciar sesión');
    } finally {
      setLoginLoading(false);
    }
  };

  // ── Espera admin ───────────────────────────────────────────────────────────
  if (pendingUser) {
    return (
      <div className="min-h-screen bg-white dark:bg-zinc-950 flex items-center justify-center px-6">
        <div className="flex flex-col items-center gap-4 text-center">
          <div className="w-12 h-12 rounded-full border-2 border-slate-200 dark:border-zinc-700 flex items-center justify-center">
            <span className="material-symbols-outlined text-slate-400 text-[20px] animate-spin">progress_activity</span>
          </div>
          <p className="text-slate-500 dark:text-zinc-400 text-sm">Verificando acceso…</p>
          <button onClick={() => { setPendingUser(''); setPendingPwd(''); }}
            className="text-xs text-slate-400 hover:text-slate-600 transition-colors">Cancelar</button>
        </div>
      </div>
    );
  }

  // ── Sheet: info invitado ───────────────────────────────────────────────────
  if (showGuestInfo) {
    const features = [
      { label: 'Buscar y comparar precios',                    ok: true },
      { label: 'Ver productos de todos los supermercados',     ok: true },
      { label: 'Carrito guardado en este dispositivo',         ok: true },
      { label: 'Favoritos y alertas de precio',                ok: false },
      { label: 'Historial y sincronización entre dispositivos',ok: false },
    ];
    return (
      <div className="min-h-screen bg-black/40 flex items-end justify-center" onClick={() => setShowGuestInfo(false)}>
        <div
          className="w-full max-w-md bg-white dark:bg-zinc-900 rounded-t-2xl px-6 pt-5 pb-10"
          onClick={e => e.stopPropagation()}
        >
          <div className="w-8 h-1 bg-slate-200 dark:bg-zinc-700 rounded-full mx-auto mb-6" />
          <h2 className="text-xl font-bold text-slate-900 dark:text-white mb-1">Modo explorador</h2>
          <p className="text-sm text-slate-500 dark:text-zinc-400 mb-6">
            Puedes buscar y comparar sin crear cuenta.
          </p>
          <div className="flex flex-col gap-3 mb-8">
            {features.map(({ label, ok }) => (
              <div key={label} className="flex items-center gap-3">
                <span className={`material-symbols-outlined text-[18px] ${ok ? 'text-green-500' : 'text-slate-300 dark:text-zinc-600'}`}>
                  {ok ? 'check_circle' : 'lock'}
                </span>
                <span className={`text-sm ${ok ? 'text-slate-800 dark:text-zinc-100' : 'text-slate-400 dark:text-zinc-500'}`}>
                  {label}
                </span>
              </div>
            ))}
          </div>
          <button
            onClick={handleEnterGuest}
            disabled={guestLoading}
            className="w-full h-12 bg-slate-100 dark:bg-zinc-800 text-slate-700 dark:text-zinc-200 font-semibold rounded-xl flex items-center justify-center gap-2 mb-3 active:scale-[0.98] transition-all disabled:opacity-50 text-sm"
          >
            {guestLoading
              ? <span className="material-symbols-outlined text-[18px] animate-spin">progress_activity</span>
              : <span className="material-symbols-outlined text-[18px]">explore</span>}
            {guestLoading ? 'Cargando...' : 'Continuar sin cuenta'}
          </button>
          <button
            onClick={() => setShowGuestInfo(false)}
            className="w-full h-12 bg-slate-900 dark:bg-white text-white dark:text-slate-900 font-semibold rounded-xl flex items-center justify-center gap-2 active:scale-[0.98] transition-all text-sm"
          >
            <GoogleLogo size={16} />
            Conectar con Google
          </button>
        </div>
      </div>
    );
  }

  // ── Sheet: admin ───────────────────────────────────────────────────────────
  if (showAdmin) {
    return (
      <div className="min-h-screen bg-black/40 flex items-end justify-center" onClick={() => setShowAdmin(false)}>
        <div
          className="w-full max-w-md bg-white dark:bg-zinc-900 rounded-t-2xl px-6 pt-5 pb-10"
          onClick={e => e.stopPropagation()}
        >
          <div className="w-8 h-1 bg-slate-200 dark:bg-zinc-700 rounded-full mx-auto mb-6" />
          <div className="flex items-center justify-between mb-6">
            <h2 className="text-lg font-bold text-slate-900 dark:text-white">Administrador</h2>
            <button onClick={() => setShowAdmin(false)} className="text-slate-400 hover:text-slate-600 transition-colors">
              <span className="material-symbols-outlined text-[20px]">close</span>
            </button>
          </div>
          <form onSubmit={handleLogin} className="flex flex-col gap-3">
            <input
              type="text" value={username} onChange={e => setUsername(e.target.value)}
              placeholder="Usuario" autoComplete="username"
              className="w-full h-12 px-4 bg-slate-50 dark:bg-zinc-800 border border-slate-200 dark:border-zinc-700 rounded-xl text-sm text-slate-900 dark:text-white placeholder:text-slate-400 dark:placeholder:text-zinc-500 focus:outline-none focus:border-slate-400 dark:focus:border-zinc-500 transition-colors"
            />
            <div className="relative">
              <input
                type={showPwd ? 'text' : 'password'} value={password} onChange={e => setPassword(e.target.value)}
                placeholder="Contraseña" autoComplete="current-password"
                className="w-full h-12 px-4 pr-12 bg-slate-50 dark:bg-zinc-800 border border-slate-200 dark:border-zinc-700 rounded-xl text-sm text-slate-900 dark:text-white placeholder:text-slate-400 dark:placeholder:text-zinc-500 focus:outline-none focus:border-slate-400 dark:focus:border-zinc-500 transition-colors"
              />
              <button type="button" onClick={() => setShowPwd(v => !v)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 transition-colors">
                <span className="material-symbols-outlined text-[18px]">{showPwd ? 'visibility_off' : 'visibility'}</span>
              </button>
            </div>
            {loginError && <p className="text-red-500 text-xs px-1">{loginError}</p>}
            <button type="submit" disabled={loginLoading || !username || !password}
              className="h-12 w-full bg-slate-900 dark:bg-white text-white dark:text-slate-900 font-semibold rounded-xl flex items-center justify-center gap-2 transition-all active:scale-[0.98] disabled:opacity-40 text-sm mt-1">
              {loginLoading
                ? <span className="material-symbols-outlined text-[18px] animate-spin">progress_activity</span>
                : 'Entrar'}
            </button>
          </form>
        </div>
      </div>
    );
  }

  // ── Vista principal ────────────────────────────────────────────────────────
  return (
    <div className="min-h-screen bg-white dark:bg-zinc-950 flex flex-col px-6 relative">

      {/* Gear admin — bottom left */}
      <button
        onClick={() => setShowAdmin(true)}
        className="absolute bottom-8 left-6 text-slate-200 dark:text-zinc-800 hover:text-slate-400 dark:hover:text-zinc-600 transition-colors"
        aria-label="Administrador"
      >
        <span className="material-symbols-outlined text-[22px]">settings</span>
      </button>

      {/* Content — centered */}
      <div className="flex-1 flex flex-col justify-center">

        {/* Wordmark */}
        <div className="mb-12">
          <p className="text-xs font-semibold text-slate-300 dark:text-zinc-700 uppercase tracking-widest mb-3">FreshCart</p>
          <h1 className="text-4xl font-black text-slate-900 dark:text-white leading-none mb-2">
            Compra<br />más inteligente.
          </h1>
          <p className="text-slate-400 dark:text-zinc-500 text-sm">
            Compara precios en tiempo real entre supermercados.
          </p>
        </div>

        {/* Actions */}
        <div className="flex flex-col gap-3">
          {isNative && (
            <button
              onClick={handleNativeGoogleSignIn}
              disabled={googleLoading}
              className="w-full h-14 flex items-center justify-center gap-3 bg-slate-900 dark:bg-white text-white dark:text-slate-900 font-semibold rounded-xl active:scale-[0.98] transition-all disabled:opacity-60 text-[15px]"
            >
              {googleLoading
                ? <span className="material-symbols-outlined text-[20px] animate-spin">progress_activity</span>
                : <GoogleLogo size={20} />}
              {googleLoading ? 'Conectando...' : 'Continuar con Google'}
            </button>
          )}

          {hasWebGoogle && <div ref={googleBtnRef} className="flex justify-center" style={{ minHeight: 44 }} />}

          {loginError && <p className="text-red-500 text-sm text-center">{loginError}</p>}

          <button
            onClick={() => setShowGuestInfo(true)}
            className="w-full h-12 flex items-center justify-center text-slate-400 dark:text-zinc-500 text-sm hover:text-slate-600 dark:hover:text-zinc-300 transition-colors"
          >
            Explorar sin cuenta
          </button>
        </div>

      </div>

    </div>
  );
};

export default Login;

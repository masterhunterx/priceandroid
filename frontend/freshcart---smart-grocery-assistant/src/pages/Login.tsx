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
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const googleBtnRef = useRef<HTMLDivElement>(null);

  const isNative = !!(window as any).Capacitor?.isNativePlatform?.();
  const hasWebGoogle = !!import.meta.env.VITE_GOOGLE_CLIENT_ID && !isNative;

  // ── Google GSI (web) ───────────────────────────────────────────────────────
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

  // ── Google Firebase (nativo Android) ──────────────────────────────────────
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

  // ── Polling aprobación admin ───────────────────────────────────────────────
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
          setPendingUser('');
          setPendingPwd('');
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

  // ── Pantalla espera aprobación ─────────────────────────────────────────────
  if (pendingUser) {
    return (
      <div className="min-h-screen bg-background-light dark:bg-background-dark flex flex-col items-center justify-center px-6">
        <div className="w-full max-w-sm bg-white dark:bg-slate-800 rounded-3xl shadow-xl border border-slate-100 dark:border-slate-700 p-8 flex flex-col items-center gap-5 text-center">
          <div className="flex items-center justify-center w-16 h-16 rounded-2xl bg-amber-100 dark:bg-amber-900/30">
            <span className="material-symbols-outlined text-amber-500 text-[36px]">hourglass_top</span>
          </div>
          <div>
            <h2 className="text-slate-900 dark:text-white text-xl font-bold mb-1">Acceso pendiente</h2>
            <p className="text-slate-500 dark:text-slate-400 text-sm">
              Verificando permisos de administrador…
            </p>
          </div>
          <div className="flex items-center gap-2 text-slate-400 text-xs">
            <span className="material-symbols-outlined text-[16px] animate-spin">progress_activity</span>
            Comprobando…
          </div>
          <button onClick={() => { setPendingUser(''); setPendingPwd(''); }}
            className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 text-sm transition-colors">
            Cancelar
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background-light dark:bg-background-dark flex flex-col items-center justify-center px-6">

      {/* Logo */}
      <div className="mb-10 flex flex-col items-center gap-3">
        <div className="relative flex items-center justify-center w-24 h-24 rounded-3xl bg-primary/10 border-2 border-primary/20">
          <span className="material-symbols-outlined text-primary text-[52px]">shopping_cart</span>
          <span className="absolute -top-2 -right-2 flex h-6 w-6 items-center justify-center rounded-full bg-primary shadow-lg">
            <span className="material-symbols-outlined text-background-dark text-[14px]">bolt</span>
          </span>
        </div>
        <div className="text-center">
          <h1 className="text-3xl font-black text-slate-900 dark:text-white tracking-tight">FreshCart</h1>
          <div className="flex items-center justify-center gap-1.5 mt-1">
            <span className="bg-primary text-background-dark text-[9px] font-black px-2 py-0.5 rounded uppercase tracking-widest">KAIROS AI</span>
            <span className="text-slate-400 text-[11px]">Asistente de Compras</span>
          </div>
        </div>
      </div>

      <div className="w-full max-w-sm flex flex-col gap-3">

        {/* Google Sign-In — nativo Android */}
        {isNative && (
          <button
            onClick={handleNativeGoogleSignIn}
            disabled={googleLoading}
            className="w-full h-14 flex items-center justify-center gap-3 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-600 rounded-2xl font-semibold text-slate-700 dark:text-slate-200 text-base shadow-sm hover:bg-slate-50 dark:hover:bg-slate-700 active:scale-95 transition-all disabled:opacity-60"
          >
            {googleLoading ? (
              <span className="material-symbols-outlined text-[22px] animate-spin text-primary">progress_activity</span>
            ) : (
              <svg width="22" height="22" viewBox="0 0 48 48" xmlns="http://www.w3.org/2000/svg">
                <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/>
                <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/>
                <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"/>
                <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/>
                <path fill="none" d="M0 0h48v48H0z"/>
              </svg>
            )}
            {googleLoading ? 'Conectando...' : 'Continuar con Google'}
          </button>
        )}

        {/* Google Sign-In — web (GSI) */}
        {hasWebGoogle && (
          <div ref={googleBtnRef} className="flex justify-center" style={{ minHeight: 44 }} />
        )}

        {loginError && <ErrorBox msg={loginError} />}

        {/* Explorar sin cuenta */}
        <button
          onClick={() => { enterGuestMode(); navigate('/store-select', { replace: true }); }}
          className="w-full h-12 flex items-center justify-center gap-2 text-slate-500 dark:text-slate-400 text-sm font-medium hover:text-slate-700 dark:hover:text-slate-200 transition-colors"
        >
          <span className="material-symbols-outlined text-[18px]">explore</span>
          Explorar sin cuenta
        </button>

        {/* Acceso administrador */}
        <div className="mt-4">
          <div className="flex items-center gap-3 mb-4">
            <div className="flex-1 h-px bg-slate-200 dark:bg-slate-700" />
            <span className="flex items-center gap-1 text-[11px] text-slate-400 uppercase tracking-widest font-semibold">
              <span className="material-symbols-outlined text-[14px]">admin_panel_settings</span>
              Administrador
            </span>
            <div className="flex-1 h-px bg-slate-200 dark:bg-slate-700" />
          </div>

          <form onSubmit={handleLogin} className="flex flex-col gap-3">
            <div className="flex items-center gap-3 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-600 rounded-xl px-4 h-12 focus-within:border-primary transition-colors shadow-sm">
              <span className="material-symbols-outlined text-slate-400 text-[20px]">person</span>
              <input
                type="text" value={username} onChange={e => setUsername(e.target.value)}
                placeholder="Usuario" autoComplete="username"
                className="flex-1 bg-transparent text-slate-900 dark:text-white text-sm focus:outline-none placeholder:text-slate-400"
              />
            </div>
            <div className="flex items-center gap-3 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-600 rounded-xl px-4 h-12 focus-within:border-primary transition-colors shadow-sm">
              <span className="material-symbols-outlined text-slate-400 text-[20px]">lock</span>
              <input
                type={showPwd ? 'text' : 'password'} value={password} onChange={e => setPassword(e.target.value)}
                placeholder="Contraseña" autoComplete="current-password"
                className="flex-1 bg-transparent text-slate-900 dark:text-white text-sm focus:outline-none placeholder:text-slate-400"
              />
              <button type="button" onClick={() => setShowPwd(v => !v)} className="text-slate-400 hover:text-primary transition-colors">
                <span className="material-symbols-outlined text-[20px]">{showPwd ? 'visibility_off' : 'visibility'}</span>
              </button>
            </div>
            <button type="submit" disabled={loginLoading || !username || !password}
              className="h-11 w-full bg-slate-700 hover:bg-slate-600 dark:bg-slate-700 dark:hover:bg-slate-600 disabled:opacity-40 disabled:cursor-not-allowed text-white font-semibold rounded-xl flex items-center justify-center gap-2 transition-all active:scale-95 text-sm">
              {loginLoading
                ? <><span className="material-symbols-outlined text-[18px] animate-spin">progress_activity</span>Verificando...</>
                : <><span className="material-symbols-outlined text-[18px]">login</span>Entrar</>}
            </button>
          </form>
        </div>

      </div>

      <p className="mt-8 text-center text-slate-400 text-[11px]">
        Protegido por <span className="text-primary font-bold">KAIROS Shield</span> · JWT Auth
      </p>
    </div>
  );
};

const ErrorBox: React.FC<{ msg: string }> = ({ msg }) => (
  <div className="flex items-center gap-2 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800/30 rounded-xl px-4 py-3">
    <span className="material-symbols-outlined text-red-500 text-[18px]">error</span>
    <p className="text-red-600 dark:text-red-400 text-sm">{msg}</p>
  </div>
);

export default Login;

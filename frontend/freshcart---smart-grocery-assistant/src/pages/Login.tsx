import React, { useState, useEffect, useRef } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { registerUser, googleLogin, forgotPassword, resetPassword } from '../lib/api';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';

declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize: (cfg: object) => void;
          renderButton: (el: HTMLElement, opts: object) => void;
          prompt: () => void;
        };
      };
    };
    onGoogleLibraryLoad?: () => void;
  }
}

type View = 'login' | 'register' | 'forgot' | 'reset';

const Login: React.FC = () => {
  const { login, setSession } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  const resetToken = searchParams.get('reset_token');
  const [view, setView] = useState<View>(resetToken ? 'reset' : 'login');

  // ── Login ──────────────────────────────────────────────────────────────────
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPwd, setShowPwd] = useState(false);
  const [loginLoading, setLoginLoading] = useState(false);
  const [loginError, setLoginError] = useState('');
  const [pendingUser, setPendingUser] = useState('');
  const [pendingPwd, setPendingPwd] = useState('');
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // ── Register ───────────────────────────────────────────────────────────────
  const [regUsername, setRegUsername] = useState('');
  const [regEmail, setRegEmail] = useState('');
  const [regPassword, setRegPassword] = useState('');
  const [showRegPwd, setShowRegPwd] = useState(false);
  const [regLoading, setRegLoading] = useState(false);
  const [regError, setRegError] = useState('');
  const [regSuccess, setRegSuccess] = useState(false);

  // ── Forgot password ────────────────────────────────────────────────────────
  const [forgotEmail, setForgotEmail] = useState('');
  const [forgotLoading, setForgotLoading] = useState(false);
  const [forgotSent, setForgotSent] = useState(false);
  const [forgotError, setForgotError] = useState('');

  // ── Reset password ─────────────────────────────────────────────────────────
  const [newPwd, setNewPwd] = useState('');
  const [newPwd2, setNewPwd2] = useState('');
  const [showNewPwd, setShowNewPwd] = useState(false);
  const [resetLoading, setResetLoading] = useState(false);
  const [resetError, setResetError] = useState('');
  const [resetDone, setResetDone] = useState(false);

  // ── Google Firebase (nativo Android) ──────────────────────────────────────
  const [googleLoading, setGoogleLoading] = useState(false);

  const handleNativeGoogleSignIn = async () => {
    setGoogleLoading(true);
    setLoginError('');
    try {
      const { GoogleAuth } = await import('@codetrix-studio/capacitor-google-auth');
      const result = await GoogleAuth.signIn();
      const idToken = result?.authentication?.idToken;
      if (!idToken) throw new Error('No se obtuvo token de Google');
      const data = await googleLogin(idToken);
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
    } finally {
      setGoogleLoading(false);
    }
  };

  // ── Google GSI ─────────────────────────────────────────────────────────────
  const googleBtnRef = useRef<HTMLDivElement>(null);

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
    if (view !== 'login' && view !== 'register') return;
    const clientId = import.meta.env.VITE_GOOGLE_CLIENT_ID;
    const native = !!(window as any).Capacitor?.isNativePlatform?.();
    if (!clientId || native) return;

    const init = () => {
      if (!window.google?.accounts?.id || !googleBtnRef.current) return;
      window.google.accounts.id.initialize({ client_id: clientId, callback: handleGoogleCredential });
      window.google.accounts.id.renderButton(googleBtnRef.current, {
        theme: 'outline', size: 'large', width: 320, locale: 'es', text: 'continue_with'
      });
    };

    if (window.google?.accounts?.id) {
      init();
    } else {
      window.onGoogleLibraryLoad = init;
    }
  }, [view]);

  // ── Polling aprobación ─────────────────────────────────────────────────────
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

  // ── Handlers ───────────────────────────────────────────────────────────────
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

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!regUsername || !regPassword) return;
    setRegLoading(true);
    setRegError('');
    try {
      await registerUser(regUsername, regPassword, regEmail || undefined);
      setRegSuccess(true);
    } catch (err: any) {
      setRegError(err.message || 'Error al registrarse');
    } finally {
      setRegLoading(false);
    }
  };

  const handleForgot = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!forgotEmail) return;
    setForgotLoading(true);
    setForgotError('');
    try {
      await forgotPassword(forgotEmail);
      setForgotSent(true);
    } catch (err: any) {
      setForgotError(err.message || 'Error al enviar solicitud');
    } finally {
      setForgotLoading(false);
    }
  };

  const handleReset = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newPwd || newPwd !== newPwd2) { setResetError('Las contraseñas no coinciden.'); return; }
    if (!resetToken) { setResetError('Token inválido.'); return; }
    setResetLoading(true);
    setResetError('');
    try {
      await resetPassword(resetToken, newPwd);
      setResetDone(true);
    } catch (err: any) {
      setResetError(err.message || 'Error al actualizar contraseña');
    } finally {
      setResetLoading(false);
    }
  };

  // ── Pantalla espera aprobación ──────────────────────────────────────────────
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
              Se envió una solicitud al administrador. Te avisaremos automáticamente cuando tengas acceso.
            </p>
          </div>
          <div className="w-full bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-700/30 rounded-2xl px-4 py-3">
            <p className="text-amber-700 dark:text-amber-400 text-sm font-medium">
              Sesión solicitada como <span className="font-bold">{pendingUser}</span>
            </p>
          </div>
          <div className="flex items-center gap-2 text-slate-400 text-xs">
            <span className="material-symbols-outlined text-[16px] animate-spin">progress_activity</span>
            Verificando aprobación…
          </div>
          <button onClick={() => { setPendingUser(''); setPendingPwd(''); }}
            className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 text-sm transition-colors">
            Cancelar y volver
          </button>
        </div>
      </div>
    );
  }

  // ── Cabecera compartida ─────────────────────────────────────────────────────
  const Header = () => (
    <div className="mb-8 flex flex-col items-center gap-3">
      <div className="relative flex items-center justify-center w-20 h-20 rounded-3xl bg-primary/10 border-2 border-primary/30">
        <span className="material-symbols-outlined text-primary text-[42px]">shopping_cart</span>
        <span className="absolute -top-1.5 -right-1.5 flex h-5 w-5 items-center justify-center rounded-full bg-primary">
          <span className="material-symbols-outlined text-background-dark text-[12px]">bolt</span>
        </span>
      </div>
      <div className="text-center">
        <h1 className="text-2xl font-black text-slate-900 dark:text-white tracking-tight">FreshCart</h1>
        <div className="flex items-center justify-center gap-1 mt-0.5">
          <span className="bg-primary text-background-dark text-[9px] font-black px-1.5 py-0.5 rounded uppercase tracking-widest">KAIROS AI</span>
          <span className="text-slate-400 text-[10px]">Asistente de Compras</span>
        </div>
      </div>
    </div>
  );

  // ── Vista: reset password ───────────────────────────────────────────────────
  if (view === 'reset') {
    return (
      <div className="min-h-screen bg-background-light dark:bg-background-dark flex flex-col items-center justify-center px-6">
        <Header />
        <div className="w-full max-w-sm bg-white dark:bg-slate-800 rounded-3xl shadow-xl border border-slate-100 dark:border-slate-700 p-7">
          {resetDone ? (
            <div className="flex flex-col items-center gap-4 text-center py-2">
              <div className="w-14 h-14 rounded-2xl bg-green-100 dark:bg-green-900/30 flex items-center justify-center">
                <span className="material-symbols-outlined text-green-500 text-[32px]">check_circle</span>
              </div>
              <div>
                <h2 className="text-slate-900 dark:text-white text-lg font-bold mb-1">¡Contraseña actualizada!</h2>
                <p className="text-slate-500 dark:text-slate-400 text-sm">Ya puedes iniciar sesión con tu nueva contraseña.</p>
              </div>
              <button onClick={() => setView('login')}
                className="mt-2 h-11 w-full bg-primary hover:bg-primary/90 text-background-dark font-bold rounded-xl transition-all active:scale-95">
                Ir a iniciar sesión
              </button>
            </div>
          ) : (
            <>
              <h2 className="text-slate-900 dark:text-white text-xl font-bold mb-1">Nueva contraseña</h2>
              <p className="text-slate-500 dark:text-slate-400 text-sm mb-6">Elige una contraseña segura de al menos 8 caracteres.</p>
              <form onSubmit={handleReset} className="flex flex-col gap-4">
                <PasswordField label="Nueva contraseña" value={newPwd} onChange={setNewPwd}
                  show={showNewPwd} onToggle={() => setShowNewPwd(v => !v)} placeholder="••••••••" />
                <PasswordField label="Confirmar contraseña" value={newPwd2} onChange={setNewPwd2}
                  show={showNewPwd} onToggle={() => setShowNewPwd(v => !v)} placeholder="••••••••" />
                {resetError && <ErrorBox msg={resetError} />}
                <button type="submit" disabled={resetLoading || !newPwd || !newPwd2}
                  className="h-12 w-full bg-primary hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed text-background-dark font-bold rounded-xl flex items-center justify-center gap-2 transition-all active:scale-95 mt-1">
                  {resetLoading
                    ? <><span className="material-symbols-outlined text-[20px] animate-spin">progress_activity</span>Actualizando...</>
                    : <><span className="material-symbols-outlined text-[20px]">lock_reset</span>Actualizar contraseña</>}
                </button>
              </form>
            </>
          )}
        </div>
      </div>
    );
  }

  // ── Vista: forgot password ──────────────────────────────────────────────────
  if (view === 'forgot') {
    return (
      <div className="min-h-screen bg-background-light dark:bg-background-dark flex flex-col items-center justify-center px-6">
        <Header />
        <div className="w-full max-w-sm bg-white dark:bg-slate-800 rounded-3xl shadow-xl border border-slate-100 dark:border-slate-700 p-7">
          <button onClick={() => setView('login')}
            className="flex items-center gap-1 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 text-sm mb-5 transition-colors">
            <span className="material-symbols-outlined text-[18px]">arrow_back</span> Volver
          </button>
          {forgotSent ? (
            <div className="flex flex-col items-center gap-4 text-center py-2">
              <div className="w-14 h-14 rounded-2xl bg-blue-100 dark:bg-blue-900/30 flex items-center justify-center">
                <span className="material-symbols-outlined text-blue-500 text-[32px]">mark_email_read</span>
              </div>
              <div>
                <h2 className="text-slate-900 dark:text-white text-lg font-bold mb-1">Revisa tu correo</h2>
                <p className="text-slate-500 dark:text-slate-400 text-sm">
                  Si el correo está registrado, recibirás un enlace de recuperación en los próximos minutos.
                </p>
              </div>
              <button onClick={() => setView('login')}
                className="mt-2 text-primary hover:text-primary/80 text-sm font-semibold transition-colors">
                Volver al inicio de sesión
              </button>
            </div>
          ) : (
            <>
              <h2 className="text-slate-900 dark:text-white text-xl font-bold mb-1">Recuperar contraseña</h2>
              <p className="text-slate-500 dark:text-slate-400 text-sm mb-6">Ingresa tu correo y te enviaremos un enlace para restablecer tu contraseña.</p>
              <form onSubmit={handleForgot} className="flex flex-col gap-4">
                <div className="flex flex-col gap-1.5">
                  <label className="text-xs font-semibold text-slate-600 dark:text-slate-300 uppercase tracking-wide">Email</label>
                  <div className="flex items-center gap-3 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-600 rounded-xl px-4 h-12 focus-within:border-primary transition-colors">
                    <span className="material-symbols-outlined text-slate-400 text-[20px]">mail</span>
                    <input type="email" value={forgotEmail} onChange={e => setForgotEmail(e.target.value)}
                      placeholder="tu@email.com" autoComplete="email"
                      className="flex-1 bg-transparent text-slate-900 dark:text-white text-sm focus:outline-none placeholder:text-slate-400" />
                  </div>
                </div>
                {forgotError && <ErrorBox msg={forgotError} />}
                <button type="submit" disabled={forgotLoading || !forgotEmail}
                  className="h-12 w-full bg-primary hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed text-background-dark font-bold rounded-xl flex items-center justify-center gap-2 transition-all active:scale-95 mt-1">
                  {forgotLoading
                    ? <><span className="material-symbols-outlined text-[20px] animate-spin">progress_activity</span>Enviando...</>
                    : <><span className="material-symbols-outlined text-[20px]">send</span>Enviar enlace</>}
                </button>
              </form>
            </>
          )}
        </div>
      </div>
    );
  }

  // ── Vista principal: login / register ──────────────────────────────────────
  const isNative = !!(window as any).Capacitor?.isNativePlatform?.();
  // En web: botón GSI. En nativo Android: botón Firebase (google-services.json lo configura).
  const hasWebGoogle = !!import.meta.env.VITE_GOOGLE_CLIENT_ID && !isNative;
  const hasNativeGoogle = isNative;

  return (
    <div className="min-h-screen bg-background-light dark:bg-background-dark flex flex-col items-center justify-center px-6">
      <Header />

      <div className="w-full max-w-sm bg-white dark:bg-slate-800 rounded-3xl shadow-xl border border-slate-100 dark:border-slate-700 p-7">
        {/* Tabs */}
        <div className="flex mb-6 bg-slate-100 dark:bg-slate-900 rounded-2xl p-1">
          {(['login', 'register'] as const).map(tab => (
            <button key={tab} onClick={() => setView(tab)}
              className={`flex-1 h-9 rounded-xl text-sm font-semibold transition-all ${
                view === tab
                  ? 'bg-white dark:bg-slate-700 text-slate-900 dark:text-white shadow-sm'
                  : 'text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200'
              }`}>
              {tab === 'login' ? 'Iniciar sesión' : 'Registrarse'}
            </button>
          ))}
        </div>

        {/* Google Sign-In — web (GSI) */}
        {hasWebGoogle && (
          <>
            <div ref={googleBtnRef} className="flex justify-center mb-4" style={{ minHeight: 44 }} />
            <div className="flex items-center gap-3 mb-4">
              <div className="flex-1 h-px bg-slate-200 dark:bg-slate-700" />
              <span className="text-xs text-slate-400">o con usuario</span>
              <div className="flex-1 h-px bg-slate-200 dark:bg-slate-700" />
            </div>
          </>
        )}

        {/* Google Sign-In — nativo Android (Firebase) */}
        {hasNativeGoogle && (
          <>
            <button
              onClick={handleNativeGoogleSignIn}
              disabled={googleLoading}
              className="w-full h-12 flex items-center justify-center gap-3 bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-600 rounded-xl mb-4 font-semibold text-slate-700 dark:text-slate-200 text-sm hover:bg-slate-50 dark:hover:bg-slate-800 active:scale-95 transition-all disabled:opacity-60"
            >
              {googleLoading ? (
                <span className="material-symbols-outlined text-[20px] animate-spin text-primary">progress_activity</span>
              ) : (
                <svg width="20" height="20" viewBox="0 0 48 48" xmlns="http://www.w3.org/2000/svg">
                  <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/>
                  <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/>
                  <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"/>
                  <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/>
                  <path fill="none" d="M0 0h48v48H0z"/>
                </svg>
              )}
              {googleLoading ? 'Conectando...' : 'Continuar con Google'}
            </button>
            <div className="flex items-center gap-3 mb-4">
              <div className="flex-1 h-px bg-slate-200 dark:bg-slate-700" />
              <span className="text-xs text-slate-400">o con usuario</span>
              <div className="flex-1 h-px bg-slate-200 dark:bg-slate-700" />
            </div>
          </>
        )}

        {/* ── LOGIN FORM ── */}
        {view === 'login' && (
          <form onSubmit={handleLogin} className="flex flex-col gap-4">
            <TextField icon="person" label="Usuario" value={username} onChange={setUsername}
              placeholder="admin" autoComplete="username" />
            <PasswordField label="Contraseña" value={password} onChange={setPassword}
              show={showPwd} onToggle={() => setShowPwd(v => !v)} placeholder="••••••••" />
            <button type="button" onClick={() => setView('forgot')}
              className="text-xs text-primary hover:text-primary/80 text-right -mt-2 transition-colors self-end">
              ¿Olvidaste tu contraseña?
            </button>
            {loginError && <ErrorBox msg={loginError} />}
            <button type="submit" disabled={loginLoading || !username || !password}
              className="h-12 w-full bg-primary hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed text-background-dark font-bold rounded-xl flex items-center justify-center gap-2 transition-all active:scale-95 shadow-lg shadow-primary/20 mt-1">
              {loginLoading
                ? <><span className="material-symbols-outlined text-[20px] animate-spin">progress_activity</span>Verificando...</>
                : <><span className="material-symbols-outlined text-[20px]">login</span>Entrar</>}
            </button>
          </form>
        )}

        {/* ── REGISTER FORM ── */}
        {view === 'register' && (
          <>
            {regSuccess ? (
              <div className="flex flex-col items-center gap-4 text-center py-2">
                <div className="w-14 h-14 rounded-2xl bg-amber-100 dark:bg-amber-900/30 flex items-center justify-center">
                  <span className="material-symbols-outlined text-amber-500 text-[32px]">hourglass_top</span>
                </div>
                <div>
                  <h3 className="text-slate-900 dark:text-white font-bold mb-1">¡Cuenta creada!</h3>
                  <p className="text-slate-500 dark:text-slate-400 text-sm">
                    Tu cuenta está pendiente de aprobación del administrador. Te avisaremos pronto.
                  </p>
                </div>
                <button onClick={() => setView('login')}
                  className="text-primary hover:text-primary/80 text-sm font-semibold transition-colors">
                  Volver al inicio de sesión
                </button>
              </div>
            ) : (
              <form onSubmit={handleRegister} className="flex flex-col gap-4">
                <TextField icon="person" label="Usuario" value={regUsername} onChange={setRegUsername}
                  placeholder="mi_usuario" autoComplete="username" />
                <TextField icon="mail" label="Email (opcional)" value={regEmail} onChange={setRegEmail}
                  placeholder="tu@email.com" autoComplete="email" type="email" />
                <PasswordField label="Contraseña" value={regPassword} onChange={setRegPassword}
                  show={showRegPwd} onToggle={() => setShowRegPwd(v => !v)} placeholder="Mín. 8 caracteres" />
                {regError && <ErrorBox msg={regError} />}
                <button type="submit" disabled={regLoading || !regUsername || !regPassword}
                  className="h-12 w-full bg-primary hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed text-background-dark font-bold rounded-xl flex items-center justify-center gap-2 transition-all active:scale-95 shadow-lg shadow-primary/20 mt-1">
                  {regLoading
                    ? <><span className="material-symbols-outlined text-[20px] animate-spin">progress_activity</span>Creando cuenta...</>
                    : <><span className="material-symbols-outlined text-[20px]">person_add</span>Crear cuenta</>}
                </button>
                <p className="text-xs text-slate-400 text-center">
                  La cuenta requiere aprobación del administrador antes de poder ingresar.
                </p>
              </form>
            )}
          </>
        )}
      </div>

      <p className="mt-6 text-center text-slate-400 text-[11px]">
        Protegido por <span className="text-primary font-bold">KAIROS Shield</span> · JWT Auth
      </p>
    </div>
  );
};

// ── Sub-componentes reutilizables ──────────────────────────────────────────────

interface TextFieldProps {
  icon: string; label: string; value: string;
  onChange: (v: string) => void; placeholder: string;
  autoComplete?: string; type?: string;
}
const TextField: React.FC<TextFieldProps> = ({ icon, label, value, onChange, placeholder, autoComplete, type = 'text' }) => (
  <div className="flex flex-col gap-1.5">
    <label className="text-xs font-semibold text-slate-600 dark:text-slate-300 uppercase tracking-wide">{label}</label>
    <div className="flex items-center gap-3 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-600 rounded-xl px-4 h-12 focus-within:border-primary transition-colors">
      <span className="material-symbols-outlined text-slate-400 text-[20px]">{icon}</span>
      <input type={type} value={value} onChange={e => onChange(e.target.value)}
        placeholder={placeholder} autoComplete={autoComplete}
        className="flex-1 bg-transparent text-slate-900 dark:text-white text-sm focus:outline-none placeholder:text-slate-400" />
    </div>
  </div>
);

interface PasswordFieldProps {
  label: string; value: string; onChange: (v: string) => void;
  show: boolean; onToggle: () => void; placeholder: string;
}
const PasswordField: React.FC<PasswordFieldProps> = ({ label, value, onChange, show, onToggle, placeholder }) => (
  <div className="flex flex-col gap-1.5">
    <label className="text-xs font-semibold text-slate-600 dark:text-slate-300 uppercase tracking-wide">{label}</label>
    <div className="flex items-center gap-3 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-600 rounded-xl px-4 h-12 focus-within:border-primary transition-colors">
      <span className="material-symbols-outlined text-slate-400 text-[20px]">lock</span>
      <input type={show ? 'text' : 'password'} value={value} onChange={e => onChange(e.target.value)}
        placeholder={placeholder} autoComplete="current-password"
        className="flex-1 bg-transparent text-slate-900 dark:text-white text-sm focus:outline-none placeholder:text-slate-400" />
      <button type="button" onClick={onToggle} className="text-slate-400 hover:text-primary transition-colors">
        <span className="material-symbols-outlined text-[20px]">{show ? 'visibility_off' : 'visibility'}</span>
      </button>
    </div>
  </div>
);

const ErrorBox: React.FC<{ msg: string }> = ({ msg }) => (
  <div className="flex items-center gap-2 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800/30 rounded-xl px-4 py-3">
    <span className="material-symbols-outlined text-red-500 text-[18px]">error</span>
    <p className="text-red-600 dark:text-red-400 text-sm">{msg}</p>
  </div>
);

export default Login;

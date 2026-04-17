import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

const Login: React.FC = () => {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!username || !password) return;

    setLoading(true);
    setError('');

    try {
      await login(username, password);
      navigate('/', { replace: true });
    } catch (err: any) {
      setError(err.message || 'Error al iniciar sesión');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-background-light dark:bg-background-dark flex flex-col items-center justify-center px-6">
      {/* Logo / Marca */}
      <div className="mb-10 flex flex-col items-center gap-3">
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

      {/* Card de Login */}
      <div className="w-full max-w-sm bg-white dark:bg-slate-800 rounded-3xl shadow-xl border border-slate-100 dark:border-slate-700 p-7">
        <h2 className="text-slate-900 dark:text-white text-xl font-bold mb-1">Iniciar sesión</h2>
        <p className="text-slate-500 dark:text-slate-400 text-sm mb-6">Accede a tu asistente de precios inteligente</p>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          {/* Usuario */}
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-semibold text-slate-600 dark:text-slate-300 uppercase tracking-wide">
              Usuario
            </label>
            <div className="flex items-center gap-3 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-600 rounded-xl px-4 h-12 focus-within:border-primary transition-colors">
              <span className="material-symbols-outlined text-slate-400 text-[20px]">person</span>
              <input
                type="text"
                autoComplete="username"
                value={username}
                onChange={e => setUsername(e.target.value)}
                placeholder="admin"
                className="flex-1 bg-transparent text-slate-900 dark:text-white text-sm focus:outline-none placeholder:text-slate-400"
              />
            </div>
          </div>

          {/* Contraseña */}
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-semibold text-slate-600 dark:text-slate-300 uppercase tracking-wide">
              Contraseña
            </label>
            <div className="flex items-center gap-3 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-600 rounded-xl px-4 h-12 focus-within:border-primary transition-colors">
              <span className="material-symbols-outlined text-slate-400 text-[20px]">lock</span>
              <input
                type={showPassword ? 'text' : 'password'}
                autoComplete="current-password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder="••••••••"
                className="flex-1 bg-transparent text-slate-900 dark:text-white text-sm focus:outline-none placeholder:text-slate-400"
              />
              <button
                type="button"
                onClick={() => setShowPassword(v => !v)}
                className="text-slate-400 hover:text-primary transition-colors"
              >
                <span className="material-symbols-outlined text-[20px]">
                  {showPassword ? 'visibility_off' : 'visibility'}
                </span>
              </button>
            </div>
          </div>

          {/* Error */}
          {error && (
            <div className="flex items-center gap-2 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800/30 rounded-xl px-4 py-3">
              <span className="material-symbols-outlined text-red-500 text-[18px]">error</span>
              <p className="text-red-600 dark:text-red-400 text-sm">{error}</p>
            </div>
          )}

          {/* Botón */}
          <button
            type="submit"
            disabled={loading || !username || !password}
            className="mt-2 h-12 w-full bg-primary hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed text-background-dark font-bold rounded-xl flex items-center justify-center gap-2 transition-all active:scale-95 shadow-lg shadow-primary/20"
          >
            {loading ? (
              <>
                <span className="material-symbols-outlined text-[20px] animate-spin">progress_activity</span>
                Verificando...
              </>
            ) : (
              <>
                <span className="material-symbols-outlined text-[20px]">login</span>
                Entrar
              </>
            )}
          </button>
        </form>
      </div>

      {/* Footer */}
      <p className="mt-8 text-center text-slate-400 text-[11px]">
        Protegido por <span className="text-primary font-bold">KAIROS Shield</span> · JWT Auth
      </p>
    </div>
  );
};

export default Login;

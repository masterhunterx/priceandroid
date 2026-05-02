
import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { getNotifications, markNotificationRead, syncProduct, deleteNotification, clearReadNotifications, refreshNotifications } from '../lib/api';
import { Notification } from '../types';
import toast from 'react-hot-toast';
import { useAuth } from '../context/AuthContext';

const Notifications: React.FC = () => {
  const navigate = useNavigate();
  const { isGuest } = useAuth();

  if (isGuest) return <GuestCTA title="Alertas de precio" description="Activa alertas cuando el precio de tus productos baje." navigate={navigate} />;

  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [loading, setLoading] = useState(true);
  const [syncingId, setSyncingId] = useState<number | null>(null);
  const [dismissingId, setDismissingId] = useState<number | null>(null);
  const [clearing, setClearing] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => {
    let mounted = true;
    let timeoutId: ReturnType<typeof setTimeout>;
    let retryDelay = 30_000; // Empieza en 30 s

    // Carga en background (sin tocar loading UI) con backoff exponencial en errores
    async function scheduledPoll() {
      if (!mounted) return;
      try {
        const data = await getNotifications();
        if (mounted) {
          // Solo actualizar estado si los datos cambiaron (evita re-renders innecesarios)
          setNotifications(prev => {
            if (prev.length === data.length && prev.every((n, i) => n.id === data[i].id && n.is_read === data[i].is_read)) return prev;
            return data;
          });
          retryDelay = 30_000;
        }
      } catch {
        // Doubling hasta máx 5 min para no saturar el servidor caído
        retryDelay = Math.min(retryDelay * 2, 5 * 60_000);
      } finally {
        if (mounted) timeoutId = setTimeout(scheduledPoll, retryDelay);
      }
    }

    loadNotifications();
    timeoutId = setTimeout(scheduledPoll, 30_000);
    return () => {
      mounted = false;
      clearTimeout(timeoutId);
    };
  }, []);

  async function loadNotifications() {
    try {
      const data = await getNotifications();
      setNotifications(data);
    } catch (error) {
      console.error('Error loading notifications:', error);
    } finally {
      setLoading(false);
    }
  }

  const handleDismiss = async (e: React.MouseEvent, id: number) => {
    e.stopPropagation();
    setDismissingId(id);
    // Pequeño delay para la animación antes de borrar del estado
    await new Promise(r => setTimeout(r, 250));
    try {
      await deleteNotification(id);
      setNotifications(prev => prev.filter(n => n.id !== id));
    } catch {
      toast.error('No se pudo eliminar la alerta');
    } finally {
      setDismissingId(null);
    }
  };

  const handleRefresh = async () => {
    if (refreshing) return;
    setRefreshing(true);
    try {
      await refreshNotifications();
      await loadNotifications();
      toast.success('Alertas actualizadas');
    } catch {
      toast.error('Error al actualizar alertas');
    } finally {
      setRefreshing(false);
    }
  };

  const handleClearRead = async () => {
    if (clearing) return;
    setClearing(true);
    try {
      const count = await clearReadNotifications();
      setNotifications(prev => prev.filter(n => !n.is_read));
      if (count > 0) toast.success(`${count} alerta${count > 1 ? 's' : ''} eliminada${count > 1 ? 's' : ''}`);
    } catch {
      toast.error('Error al limpiar notificaciones');
    } finally {
      setClearing(false);
    }
  };

  const handleNotificationClick = async (notif: Notification) => {
    if (syncingId || dismissingId) return;

    // 1. Marcar como leída y remover de la lista con animación
    if (!notif.is_read) {
      markNotificationRead(notif.id).catch(() => {});
      // Remover inmediatamente de la UI para sensación de limpieza
      setDismissingId(notif.id);
      await new Promise(r => setTimeout(r, 250));
      setNotifications(prev => prev.filter(n => n.id !== notif.id));
      setDismissingId(null);
    }

    // 2. Sync de precio en vivo si tiene producto
    if (notif.product_id) {
      setSyncingId(notif.id);
      const toastId = toast.loading('Verificando precio en vivo...');
      try {
        await syncProduct(notif.product_id);
        toast.success('Precio verificado', { id: toastId });
      } catch {
        toast.dismiss(toastId);
      } finally {
        setSyncingId(null);
      }
    }

    // 3. Navegar
    if (notif.link_url) navigate(notif.link_url);
  };

  const getRelativeTime = (dateStr: string) => {
    const date = new Date(dateStr);
    const diffMin = Math.floor((Date.now() - date.getTime()) / 60000);
    if (diffMin < 1) return 'Ahora mismo';
    if (diffMin < 60) return `Hace ${diffMin} min`;
    const diffHr = Math.floor(diffMin / 60);
    if (diffHr < 24) return `Hace ${diffHr}h`;
    return date.toLocaleDateString('es-CL');
  };

  const unreadCount = notifications.filter(n => !n.is_read).length;
  const readCount = notifications.filter(n => n.is_read).length;

  const groups: Record<string, Notification[]> = useMemo(() => {
    const today = new Date().toDateString();
    const yesterday = new Date(Date.now() - 86400000).toDateString();
    const result: Record<string, Notification[]> = { 'Hoy': [], 'Ayer': [], 'Anteriores': [] };
    notifications.forEach(n => {
      const d = new Date(n.created_at).toDateString();
      if (d === today) result['Hoy'].push(n);
      else if (d === yesterday) result['Ayer'].push(n);
      else result['Anteriores'].push(n);
    });
    return result;
  }, [notifications]);

  return (
    <div className="flex flex-col min-h-screen bg-slate-50 dark:bg-[#0d1a12]">
      <header className="p-6 bg-white dark:bg-[#1a2e22]/50 backdrop-blur-md sticky top-0 z-10 border-b border-slate-100 dark:border-white/5">
        <div className="flex items-center justify-between mb-1">
          <div className="flex items-center gap-4">
            <button onClick={() => navigate('/')} className="size-10 flex items-center justify-center rounded-full bg-slate-100 dark:bg-white/10 active:scale-95 transition-all text-slate-900 dark:text-white">
              <span className="material-symbols-outlined">arrow_back</span>
            </button>
            <h1 className="text-2xl font-black text-slate-900 dark:text-white tracking-tight">Alertas de Ahorro</h1>
          </div>

          <div className="flex items-center gap-3">
            {/* Botón actualizar */}
            <button
              onClick={handleRefresh}
              disabled={refreshing}
              className="flex items-center gap-1 text-[10px] font-black uppercase tracking-widest text-primary hover:text-primary/80 active:scale-95 transition-all disabled:opacity-50"
            >
              <span className={`material-symbols-outlined text-sm ${refreshing ? 'animate-spin' : ''}`}>
                refresh
              </span>
              {refreshing ? 'Buscando...' : 'Actualizar'}
            </button>

            {/* Botón limpiar revisadas */}
            {readCount > 0 && (
              <button
                onClick={handleClearRead}
                disabled={clearing}
                className="flex items-center gap-1 text-[10px] font-black uppercase tracking-widest text-red-400 hover:text-red-500 active:scale-95 transition-all disabled:opacity-50"
              >
                <span className={`material-symbols-outlined text-sm ${clearing ? 'animate-spin' : ''}`}>
                  {clearing ? 'sync' : 'delete_sweep'}
                </span>
                Limpiar ({readCount})
              </button>
            )}
          </div>
        </div>

        <div className="flex items-center gap-2 mt-2">
          <p className="text-slate-500 dark:text-[#9db9a8] text-sm">
            {unreadCount > 0
              ? `${unreadCount} alerta${unreadCount > 1 ? 's' : ''} sin revisar`
              : 'Todo revisado · Toca para navegar'}
          </p>
          {unreadCount > 0 && (
            <span className="size-1.5 rounded-full bg-primary animate-pulse" />
          )}
        </div>
      </header>

      <main className="flex-1 p-4 pb-24">
        {loading ? (
          <div className="flex flex-col gap-4">
            {[1, 2, 3].map(i => (
              <div key={i} className="h-24 w-full animate-pulse bg-slate-200 dark:bg-white/5 rounded-2xl" />
            ))}
          </div>
        ) : notifications.length > 0 ? (
          <div className="flex flex-col gap-8">
            {Object.entries(groups).map(([title, items]) => items.length > 0 && (
              <div key={title} className="flex flex-col gap-3">
                <h2 className="px-2 text-[10px] font-black uppercase tracking-[0.2em] text-primary/70">{title}</h2>
                {items.map((notif) => (
                  <div
                    key={notif.id}
                    onClick={() => handleNotificationClick(notif)}
                    className={`relative overflow-hidden p-5 rounded-2xl border transition-all cursor-pointer active:scale-95 ${
                      dismissingId === notif.id ? 'opacity-0 scale-95 -translate-x-4' : 'opacity-100 scale-100'
                    } ${
                      notif.is_read
                        ? 'bg-white/60 dark:bg-white/5 border-slate-100 dark:border-white/5 opacity-70'
                        : 'bg-white dark:bg-[#1c2720] border-primary/20 shadow-md shadow-primary/5'
                    } ${syncingId === notif.id ? 'animate-pulse ring-2 ring-primary ring-offset-2 dark:ring-offset-[#0d1a12]' : ''}`}
                    style={{ transition: 'opacity 0.25s ease, transform 0.25s ease' }}
                  >
                    {/* Indicador no leído */}
                    {!notif.is_read && (
                      <div className="absolute top-0 right-10 p-3">
                        <div className="size-2 bg-primary rounded-full animate-pulse" />
                      </div>
                    )}

                    {/* Botón X para descartar */}
                    <button
                      onClick={(e) => handleDismiss(e, notif.id)}
                      className="absolute top-3 right-3 size-6 flex items-center justify-center rounded-full bg-slate-100 dark:bg-white/10 text-slate-400 hover:text-red-400 hover:bg-red-50 dark:hover:bg-red-500/10 transition-all active:scale-90 z-10"
                    >
                      <span className="material-symbols-outlined text-[14px]">close</span>
                    </button>

                    <div className="flex gap-4 pr-4">
                      <div className={`size-12 rounded-xl flex items-center justify-center shrink-0 ${
                        notif.type?.startsWith('price') ? 'bg-primary/10 text-primary' : 'bg-blue-500/10 text-blue-500'
                      }`}>
                        <span className="material-symbols-outlined">
                          {notif.type === 'price_luca' ? 'monetization_on' :
                           notif.type?.startsWith('price') ? 'trending_down' : 'notifications_active'}
                        </span>
                      </div>

                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <h3 className={`font-bold leading-tight text-sm ${notif.is_read ? 'text-slate-500 dark:text-slate-400' : 'text-slate-900 dark:text-white'}`}>
                            {notif.title}
                          </h3>
                          {notif.type === 'price_luca' && (
                            <span className="bg-primary text-background-dark text-[10px] font-black px-1.5 py-0.5 rounded shrink-0">A LUCA</span>
                          )}
                          {notif.type === 'price_under_2k' && (
                            <span className="bg-yellow-500 text-white text-[10px] font-black px-1.5 py-0.5 rounded shrink-0">&lt;2K</span>
                          )}
                        </div>
                        <p className="text-xs text-slate-500 dark:text-[#8ea89a] line-clamp-2">{notif.message}</p>
                        <div className="flex items-center justify-between mt-3">
                          <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest flex items-center gap-1">
                            <span className="material-symbols-outlined text-xs">schedule</span>
                            {getRelativeTime(notif.created_at)}
                          </span>
                          <span className="text-[10px] font-bold text-primary uppercase flex items-center gap-1">
                            {syncingId === notif.id ? 'Verificando...' : 'Ver Oferta'}
                            <span className="material-symbols-outlined text-xs">arrow_forward</span>
                          </span>
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            ))}
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center py-24 text-center px-10">
            <div className="size-24 rounded-full bg-slate-100 dark:bg-white/5 flex items-center justify-center mb-8 border-2 border-dashed border-slate-200 dark:border-white/10">
              <span className="material-symbols-outlined text-5xl text-slate-300">notifications_off</span>
            </div>
            <h2 className="text-xl font-bold text-slate-900 dark:text-white">Tu bandeja está al día</h2>
            <p className="text-slate-500 dark:text-[#9db9a8] text-sm mt-2 max-w-[240px]">KAIROS te avisará cuando detecte oportunidades reales de ahorro.</p>
          </div>
        )}
      </main>
    </div>
  );
};

const GuestCTA: React.FC<{ title: string; description: string; navigate: (path: string) => void }> = ({ title, description, navigate }) => (
  <div className="min-h-screen bg-background-light dark:bg-background-dark flex flex-col items-center justify-center px-6 text-center">
    <div className="w-16 h-16 rounded-2xl bg-primary/10 flex items-center justify-center mb-4">
      <span className="material-symbols-outlined text-primary text-[32px]">notifications</span>
    </div>
    <h2 className="text-xl font-bold text-slate-900 dark:text-white mb-2">{title}</h2>
    <p className="text-slate-500 dark:text-slate-400 text-sm mb-6 max-w-xs">{description}</p>
    <button
      onClick={() => navigate('/login')}
      className="w-full max-w-xs h-12 flex items-center justify-center gap-3 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-600 rounded-2xl font-semibold text-slate-700 dark:text-slate-200 text-sm shadow-sm hover:bg-slate-50 active:scale-95 transition-all"
    >
      <svg width="18" height="18" viewBox="0 0 48 48" xmlns="http://www.w3.org/2000/svg">
        <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/>
        <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/>
        <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"/>
        <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/>
        <path fill="none" d="M0 0h48v48H0z"/>
      </svg>
      Conectar con Google
    </button>
    <p className="text-xs text-slate-400 mt-3">Tu carrito y búsquedas se conservan</p>
  </div>
);

export default Notifications;

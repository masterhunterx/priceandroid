import React, { useState, useEffect } from 'react';

const STORE_COLORS: Record<string, string> = {
  jumbo:        '#00a650',
  santa_isabel: '#e30613',
  lider:        '#0071ce',
  unimarc:      '#da291c',
};

const DEFAULT_COLOR = '#16a34a';

const MESSAGES = [
  'Buscando las mejores ofertas...',
  'Comparando precios entre tiendas...',
  'Revisando descuentos de hoy...',
  'Preparando tu canasta...',
  '¡Listo para ahorrar!',
];

const SplashScreen: React.FC<{ onComplete: () => void }> = ({ onComplete }) => {
  const [progress, setProgress] = useState(0);
  const [msgIndex, setMsgIndex] = useState(0);

  const isDark = document.documentElement.classList.contains('dark');
  const savedStore = localStorage.getItem('selected_store') ?? '';
  const accentColor = STORE_COLORS[savedStore] ?? DEFAULT_COLOR;

  const bg    = isDark ? '#0a0a0a' : '#ffffff';
  const text  = isDark ? '#ffffff' : '#111111';
  const sub   = isDark ? '#9ca3af' : '#6b7280';
  const track = isDark ? '#1f2937' : '#f3f4f6';

  useEffect(() => {
    const duration = 2800;
    const interval = 30;
    const increment = 100 / (duration / interval);

    const timer = setInterval(() => {
      setProgress(prev => {
        const next = prev + increment;
        if (next >= 100) {
          clearInterval(timer);
          setTimeout(onComplete, 300);
          return 100;
        }
        return next;
      });
    }, interval);

    const msgTimer = setInterval(() => {
      setMsgIndex(prev => (prev + 1) % MESSAGES.length);
    }, 560);

    return () => { clearInterval(timer); clearInterval(msgTimer); };
  }, []);

  return (
    <div
      className="fixed inset-0 z-[1000] flex flex-col items-center justify-center p-8"
      style={{ background: bg }}
    >
      {/* Ícono */}
      <div className="mb-10 flex flex-col items-center gap-5">
        <div
          className="size-24 rounded-[28px] flex items-center justify-center shadow-lg"
          style={{ background: accentColor }}
        >
          <span
            className="material-symbols-outlined text-white"
            style={{ fontSize: 52, fontVariationSettings: "'FILL' 1" }}
          >
            shopping_basket
          </span>
        </div>

        <div className="text-center">
          <h1 className="text-3xl font-black tracking-tight" style={{ color: text }}>
            FreshCart
          </h1>
          <p className="text-sm font-medium mt-1" style={{ color: sub }}>
            Compara precios, ahorra más
          </p>
        </div>
      </div>

      {/* Progreso */}
      <div className="w-full max-w-[260px] space-y-3">
        <div className="h-1.5 w-full rounded-full overflow-hidden" style={{ background: track }}>
          <div
            className="h-full rounded-full transition-all duration-100 ease-out"
            style={{ width: `${progress}%`, background: accentColor }}
          />
        </div>

        <div className="flex items-center justify-between">
          <p className="text-xs font-medium" style={{ color: sub }}>
            {MESSAGES[msgIndex]}
          </p>
          <span className="text-xs font-bold tabular-nums" style={{ color: text }}>
            {Math.round(progress)}%
          </span>
        </div>
      </div>

      {/* Tiendas */}
      <div className="absolute bottom-10">
        <p className="text-[10px] font-semibold uppercase tracking-widest text-center" style={{ color: sub }}>
          Jumbo · Lider · Santa Isabel · Unimarc
        </p>
      </div>
    </div>
  );
};

export default SplashScreen;

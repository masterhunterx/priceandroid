import React, { useState, useEffect } from 'react';

const SplashScreen: React.FC<{ onComplete: () => void }> = ({ onComplete }) => {
  const [progress, setProgress] = useState(0);
  const [message, setMessage] = useState('Iniciando FluxEngine...');

  const messages = [
    'Iniciando FluxEngine v4.0...',
    'Ejecutando Doble Check de Ubicaciones...',
    'Auditando 346 Comunas de Chile...',
    'Sincronizando Precios Nacionales...',
    'Verificando Inventarios 2026...',
    'Optimizando Canastas de Ahorro...',
    'Geolocalización Verificada al 100%',
    'Bienvenido a FreshCart'
  ];

  useEffect(() => {
    const duration = 2800; // 2.8 seconds
    const interval = 30;
    const steps = duration / interval;
    const increment = 100 / steps;

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

    // Rotate messages
    const messageInterval = setInterval(() => {
      setMessage(prev => {
        const currentIndex = messages.indexOf(prev);
        return messages[(currentIndex + 1) % messages.length];
      });
    }, 500);

    return () => {
      clearInterval(timer);
      clearInterval(messageInterval);
    };
  }, []);

  return (
    <div className="fixed inset-0 z-[1000] bg-background-dark flex flex-col items-center justify-center p-8 animate-in fade-in duration-500">
      <div className="relative mb-12">
        <div className="size-24 rounded-3xl bg-primary/20 flex items-center justify-center p-4 ring-2 ring-primary/40 animate-pulse">
          <span className="material-symbols-outlined text-primary text-[64px] animate-spin-slow">cyclone</span>
        </div>
        <div className="absolute -top-3 -right-3 bg-primary text-background-dark font-black text-[12px] px-3 py-1.5 rounded-xl shadow-xl shadow-primary/40">
          FluxEngine v4.0
        </div>
      </div>

      <div className="w-full max-w-xs space-y-4">
        <div className="flex justify-between items-end">
          <div className="space-y-1">
            <h1 className="text-white text-2xl font-black tracking-tighter uppercase italic">FreshCart</h1>
            <p className="text-primary text-[10px] font-bold uppercase tracking-[0.2em]">{message}</p>
          </div>
          <span className="text-white font-black text-xl italic">{Math.round(progress)}%</span>
        </div>

        <div className="h-3 w-full bg-slate-800 rounded-full overflow-hidden border border-slate-700 p-0.5">
          <div 
            className="h-full bg-gradient-to-r from-primary via-emerald-400 to-primary rounded-full transition-all duration-100 ease-out shadow-[0_0_15px_rgba(34,197,94,0.5)]"
            style={{ width: `${progress}%` }}
          />
        </div>
        
        <div className="flex justify-center gap-1.5 opacity-50 mt-4">
          {[0, 1, 2].map(i => (
            <div 
              key={i} 
              className={`w-1 h-1 rounded-full bg-primary animate-bounce`}
              style={{ animationDelay: `${i * 0.15}s` }}
            />
          ))}
        </div>
      </div>
      
      <div className="absolute bottom-12 text-slate-600 text-[10px] font-bold uppercase tracking-widest flex items-center gap-2">
        <span className="w-8 h-px bg-slate-800"></span>
        DeepMind Agent Intelligence
        <span className="w-8 h-px bg-slate-800"></span>
      </div>
    </div>
  );
};

export default SplashScreen;

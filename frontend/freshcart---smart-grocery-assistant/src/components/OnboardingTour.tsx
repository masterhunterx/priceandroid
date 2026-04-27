import { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

const STORAGE_KEY = 'freshcart_tour_done';
const TESTER_KEY  = 'freshcart_tester_mode';

interface SpotlightRect { x: number; y: number; w: number; h: number; }

interface TourStep {
  selector: string | null;
  title: string;
  body: string;
  emoji: string;
  position: 'top' | 'bottom' | 'center';
}

const STEPS: TourStep[] = [
  {
    selector: '[data-tour="search"]',
    title: 'Busca y compara precios',
    body: 'Escribe cualquier producto y compara precios entre Jumbo, Lider, Santa Isabel y Unimarc al instante.',
    emoji: '🔍',
    position: 'bottom',
  },
  {
    selector: '[data-tour="categories"]',
    title: 'Explora por categorías',
    body: 'Navega por lácteos, carnes, bebidas y más. Toca cualquier categoría para ver los productos de tu tienda.',
    emoji: '🛒',
    position: 'bottom',
  },
  {
    selector: '[data-tour="feedback-btn"]',
    title: '¡Tu opinión importa!',
    body: 'Si encuentras un error o tienes una idea, repórtalo aquí. Tu feedback llega directo al equipo.',
    emoji: '💬',
    position: 'top',
  },
];

function getRect(selector: string): SpotlightRect | null {
  const el = document.querySelector(selector);
  if (!el) return null;
  const r = el.getBoundingClientRect();
  return { x: r.left, y: r.top, w: r.width, h: r.height };
}

function SpotlightOverlay({ rect }: { rect: SpotlightRect | null }) {
  const pad = 12;
  if (!rect) return <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.78)', zIndex: 400, pointerEvents: 'none' }} />;
  const sx = rect.x - pad, sy = rect.y - pad, sw = rect.w + pad * 2, sh = rect.h + pad * 2;
  return (
    <svg style={{ position: 'fixed', inset: 0, width: '100%', height: '100%', zIndex: 400, pointerEvents: 'none' }}>
      <defs>
        <mask id="tour-mask">
          <rect width="100%" height="100%" fill="white" />
          <rect x={sx} y={sy} width={sw} height={sh} rx="14" fill="black" />
        </mask>
      </defs>
      <rect width="100%" height="100%" fill="rgba(0,0,0,0.78)" mask="url(#tour-mask)" />
      {/* pulsing border around spotlight */}
      <rect x={sx} y={sy} width={sw} height={sh} rx="14" fill="none"
        stroke="rgba(0,240,118,0.8)" strokeWidth="2" />
    </svg>
  );
}

function TooltipCard({
  step, onNext, onSkip, stepIndex, total,
}: {
  step: TourStep; onNext: () => void; onSkip: () => void;
  stepIndex: number; total: number;
}) {
  const isLast = stepIndex === total - 1;

  return (
    <motion.div
      key={stepIndex}
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: 16 }}
      transition={{ duration: 0.22 }}
      style={{
        position: 'fixed',
        bottom: '90px',
        left: '16px',
        right: '16px',
        zIndex: 401,
        background: '#1a1a2e',
        borderRadius: '16px',
        padding: '16px 18px',
        border: '1.5px solid rgba(0,240,118,0.3)',
        boxShadow: '0 8px 32px rgba(0,0,0,0.6)',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '8px' }}>
        <span style={{ fontSize: '24px' }}>{step.emoji}</span>
        <h3 style={{ color: '#fff', fontSize: '16px', fontWeight: 700, margin: 0 }}>{step.title}</h3>
      </div>
      <p style={{ color: '#94a3b8', fontSize: '13px', lineHeight: 1.6, margin: '0 0 16px' }}>{step.body}</p>

      {/* Progress dots */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', gap: '6px' }}>
          {Array.from({ length: total }).map((_, i) => (
            <div key={i} style={{
              width: i === stepIndex ? '18px' : '6px', height: '6px', borderRadius: '3px',
              background: i === stepIndex ? '#00f076' : '#334155',
              transition: 'all 0.3s',
            }} />
          ))}
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          <button onClick={onSkip} style={{
            background: 'transparent', border: '1px solid #334155', color: '#94a3b8',
            borderRadius: '8px', padding: '6px 12px', fontSize: '12px', cursor: 'pointer',
          }}>
            Saltar
          </button>
          <button onClick={onNext} style={{
            background: 'linear-gradient(135deg, #00f076, #00c45e)',
            border: 'none', color: '#000', borderRadius: '8px',
            padding: '6px 16px', fontSize: '13px', fontWeight: 700, cursor: 'pointer',
          }}>
            {isLast ? '¡Listo! 🎉' : 'Siguiente →'}
          </button>
        </div>
      </div>
    </motion.div>
  );
}

export default function OnboardingTour() {
  const [phase, setPhase] = useState<'welcome' | 'tour' | 'done'>('done');
  const [stepIndex, setStepIndex] = useState(0);
  const [rect, setRect] = useState<SpotlightRect | null>(null);

  // Check localStorage on mount
  useEffect(() => {
    if (!localStorage.getItem(STORAGE_KEY)) {
      // Small delay to let page render completely
      setTimeout(() => setPhase('welcome'), 800);
    }
  }, []);

  // Update spotlight rect when step changes
  useEffect(() => {
    if (phase !== 'tour') return;
    const step = STEPS[stepIndex];
    if (!step.selector) { setRect(null); return; }
    const update = () => setRect(getRect(step.selector!));
    update();
    const interval = setInterval(update, 300);
    return () => clearInterval(interval);
  }, [phase, stepIndex]);

  const completeTour = useCallback(() => {
    localStorage.setItem(STORAGE_KEY, '1');
    localStorage.setItem(TESTER_KEY, '1');
    setPhase('done');
  }, []);

  const handleNext = useCallback(() => {
    if (stepIndex < STEPS.length - 1) {
      setStepIndex(i => i + 1);
    } else {
      completeTour();
    }
  }, [stepIndex, completeTour]);

  if (phase === 'done') return null;

  // ── Welcome modal ───────────────────────────────────────────────────────────
  if (phase === 'welcome') {
    return (
      <AnimatePresence>
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          style={{
            position: 'fixed', inset: 0, zIndex: 500,
            background: 'rgba(0,0,0,0.85)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            padding: '24px',
          }}
        >
          <motion.div
            initial={{ scale: 0.9, opacity: 0, y: 20 }}
            animate={{ scale: 1, opacity: 1, y: 0 }}
            transition={{ delay: 0.1, type: 'spring', stiffness: 200, damping: 20 }}
            style={{
              background: 'linear-gradient(160deg, #0f172a 0%, #1a1a2e 100%)',
              borderRadius: '24px',
              padding: '32px 24px',
              maxWidth: '360px',
              width: '100%',
              border: '1.5px solid rgba(0,240,118,0.25)',
              boxShadow: '0 25px 60px rgba(0,0,0,0.7), 0 0 40px rgba(0,240,118,0.08)',
              textAlign: 'center',
            }}
          >
            {/* Badge */}
            <div style={{
              display: 'inline-flex', alignItems: 'center', gap: '6px',
              background: 'rgba(0,240,118,0.12)', border: '1px solid rgba(0,240,118,0.35)',
              borderRadius: '999px', padding: '4px 14px', marginBottom: '20px',
            }}>
              <span style={{ fontSize: '13px' }}>🧪</span>
              <span style={{ color: '#00f076', fontSize: '12px', fontWeight: 700, letterSpacing: '0.05em' }}>
                USUARIO TESTER
              </span>
            </div>

            {/* Icon */}
            <div style={{
              width: '72px', height: '72px', borderRadius: '50%',
              background: 'linear-gradient(135deg, #00f076, #00c45e)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: '36px', margin: '0 auto 20px',
              boxShadow: '0 8px 24px rgba(0,240,118,0.35)',
            }}>
              🛒
            </div>

            <h1 style={{ color: '#fff', fontSize: '22px', fontWeight: 800, margin: '0 0 12px' }}>
              ¡Bienvenido a FreshCart!
            </h1>
            <p style={{ color: '#94a3b8', fontSize: '14px', lineHeight: 1.7, margin: '0 0 8px' }}>
              Estás entre los <strong style={{ color: '#e2e8f0' }}>primeros usuarios</strong> en probar
              la app. Tu misión es explorarla y reportarnos cualquier error o idea.
            </p>
            <p style={{ color: '#64748b', fontSize: '13px', lineHeight: 1.6, margin: '0 0 28px' }}>
              La app puede presentar problemas — eso es totalmente normal en esta etapa.
              Tu feedback es fundamental para mejorarla. 🙌
            </p>

            <button
              onClick={() => { setPhase('tour'); setStepIndex(0); }}
              style={{
                width: '100%', padding: '14px',
                background: 'linear-gradient(135deg, #00f076, #00c45e)',
                border: 'none', borderRadius: '14px',
                color: '#000', fontSize: '15px', fontWeight: 800,
                cursor: 'pointer', marginBottom: '12px',
                boxShadow: '0 4px 20px rgba(0,240,118,0.4)',
              }}
            >
              Ver cómo funciona →
            </button>
            <button
              onClick={completeTour}
              style={{
                background: 'transparent', border: 'none',
                color: '#64748b', fontSize: '13px', cursor: 'pointer',
              }}
            >
              Ya conozco la app, saltar
            </button>
          </motion.div>
        </motion.div>
      </AnimatePresence>
    );
  }

  // ── Tour with spotlight ─────────────────────────────────────────────────────
  const step = STEPS[stepIndex];
  return (
    <>
      <SpotlightOverlay rect={rect} />
      <AnimatePresence mode="wait">
        <motion.div key={stepIndex} style={{ display: 'contents' }}>
          <TooltipCard
            step={step}
            onNext={handleNext}
            onSkip={completeTour}
            stepIndex={stepIndex}
            total={STEPS.length}
          />
        </motion.div>
      </AnimatePresence>
    </>
  );
}

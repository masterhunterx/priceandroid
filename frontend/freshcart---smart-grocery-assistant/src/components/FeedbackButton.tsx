import { useState, useRef, useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import { submitFeedback } from '../lib/api';

type FeedbackType = 'bug' | 'mejora' | 'sugerencia';

interface TypeOption {
  value: FeedbackType;
  emoji: string;
  label: string;
  placeholder: string;
  color: string;
}

const TYPE_OPTIONS: TypeOption[] = [
  {
    value: 'bug',
    emoji: '🐛',
    label: 'Bug',
    placeholder: 'Describe qué pasó y en qué pantalla ocurrió. Ej: "Al buscar leche, la app se cierra"',
    color: '#ef4444',
  },
  {
    value: 'mejora',
    emoji: '✨',
    label: 'Mejora',
    placeholder: 'Describe qué mejorarías. Ej: "Que los precios se ordenen por distancia"',
    color: '#f59e0b',
  },
  {
    value: 'sugerencia',
    emoji: '💡',
    label: 'Sugerencia',
    placeholder: 'Comparte tu idea. Ej: "Agregar modo oscuro" o "Comparar más tiendas"',
    color: '#8b5cf6',
  },
];

type Stage = 'idle' | 'open' | 'sending' | 'success' | 'error';

export default function FeedbackButton() {
  const location = useLocation();
  const [stage, setStage] = useState<Stage>('idle');
  const [type, setType] = useState<FeedbackType>('bug');
  const [text, setText] = useState('');
  const [errorMsg, setErrorMsg] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const overlayRef = useRef<HTMLDivElement>(null);

  const selectedOption = TYPE_OPTIONS.find(o => o.value === type)!;

  // Auto-focus textarea when modal opens
  useEffect(() => {
    if (stage === 'open') {
      setTimeout(() => textareaRef.current?.focus(), 100);
    }
  }, [stage]);

  // Close on backdrop click
  function handleOverlayClick(e: React.MouseEvent) {
    if (e.target === overlayRef.current) close();
  }

  function open() {
    setText('');
    setErrorMsg('');
    setStage('open');
  }

  function close() {
    if (stage === 'sending') return;
    setStage('idle');
    setText('');
    setErrorMsg('');
  }

  async function handleSubmit() {
    if (!text.trim() || text.trim().length < 5) {
      setErrorMsg('Escribe al menos 5 caracteres para enviarlo.');
      return;
    }
    setStage('sending');
    setErrorMsg('');
    try {
      await submitFeedback(type, text.trim(), location.pathname);
      setStage('success');
      setTimeout(() => setStage('idle'), 3000);
    } catch (e: any) {
      setErrorMsg(e?.message || 'No se pudo enviar. Intenta de nuevo.');
      setStage('error');
    }
  }

  // Don't show on auth pages
  if (['/login', '/register'].includes(location.pathname)) return null;

  return (
    <>
      {/* Floating trigger button */}
      <button
        onClick={open}
        aria-label="Enviar feedback"
        style={{
          position: 'fixed',
          bottom: '80px',
          left: '16px',
          zIndex: 50,
          width: '44px',
          height: '44px',
          borderRadius: '50%',
          background: 'linear-gradient(135deg, #6366f1, #8b5cf6)',
          border: 'none',
          cursor: 'pointer',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          boxShadow: '0 4px 14px rgba(99,102,241,0.5)',
          transition: 'transform 0.15s, box-shadow 0.15s',
          fontSize: '20px',
        }}
        onMouseEnter={e => {
          (e.currentTarget as HTMLButtonElement).style.transform = 'scale(1.1)';
        }}
        onMouseLeave={e => {
          (e.currentTarget as HTMLButtonElement).style.transform = 'scale(1)';
        }}
      >
        💬
      </button>

      {/* Modal overlay */}
      {(stage === 'open' || stage === 'sending' || stage === 'error') && (
        <div
          ref={overlayRef}
          onClick={handleOverlayClick}
          style={{
            position: 'fixed',
            inset: 0,
            zIndex: 200,
            background: 'rgba(0,0,0,0.55)',
            display: 'flex',
            alignItems: 'flex-end',
            justifyContent: 'center',
            padding: '0',
          }}
        >
          <div
            style={{
              background: '#1e1e2e',
              borderRadius: '20px 20px 0 0',
              width: '100%',
              maxWidth: '480px',
              padding: '24px 20px 32px',
              animation: 'slideUp 0.25s ease',
            }}
          >
            {/* Header */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
              <div>
                <p style={{ color: '#a78bfa', fontSize: '12px', fontWeight: 600, marginBottom: '2px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  Modo Test
                </p>
                <h2 style={{ color: '#fff', fontSize: '18px', fontWeight: 700, margin: 0 }}>
                  Reportar al equipo
                </h2>
              </div>
              <button
                onClick={close}
                style={{ background: 'transparent', border: 'none', color: '#6b7280', cursor: 'pointer', fontSize: '22px', lineHeight: 1, padding: '4px' }}
              >
                ✕
              </button>
            </div>

            {/* Type selector */}
            <div style={{ display: 'flex', gap: '8px', marginBottom: '16px' }}>
              {TYPE_OPTIONS.map(opt => (
                <button
                  key={opt.value}
                  onClick={() => setType(opt.value)}
                  style={{
                    flex: 1,
                    padding: '10px 4px',
                    borderRadius: '12px',
                    border: `2px solid ${type === opt.value ? opt.color : 'transparent'}`,
                    background: type === opt.value ? `${opt.color}20` : '#2d2d3f',
                    color: type === opt.value ? opt.color : '#9ca3af',
                    cursor: 'pointer',
                    fontSize: '13px',
                    fontWeight: 600,
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    gap: '4px',
                    transition: 'all 0.15s',
                  }}
                >
                  <span style={{ fontSize: '22px' }}>{opt.emoji}</span>
                  {opt.label}
                </button>
              ))}
            </div>

            {/* Textarea */}
            <textarea
              ref={textareaRef}
              value={text}
              onChange={e => { setText(e.target.value); setErrorMsg(''); }}
              placeholder={selectedOption.placeholder}
              rows={4}
              maxLength={2000}
              style={{
                width: '100%',
                background: '#2d2d3f',
                border: `1.5px solid ${errorMsg ? '#ef4444' : '#3f3f5a'}`,
                borderRadius: '12px',
                color: '#e5e7eb',
                fontSize: '14px',
                padding: '12px',
                resize: 'none',
                outline: 'none',
                fontFamily: 'inherit',
                lineHeight: '1.5',
                boxSizing: 'border-box',
              }}
              onFocus={e => { e.currentTarget.style.borderColor = selectedOption.color; }}
              onBlur={e => { e.currentTarget.style.borderColor = errorMsg ? '#ef4444' : '#3f3f5a'; }}
            />

            {/* Character count + error */}
            <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '6px', marginBottom: '16px' }}>
              {errorMsg
                ? <p style={{ color: '#ef4444', fontSize: '12px', margin: 0 }}>{errorMsg}</p>
                : <span />
              }
              <span style={{ color: '#6b7280', fontSize: '12px' }}>{text.length}/2000</span>
            </div>

            {/* Submit */}
            <button
              onClick={handleSubmit}
              disabled={stage === 'sending'}
              style={{
                width: '100%',
                padding: '14px',
                borderRadius: '12px',
                border: 'none',
                background: stage === 'sending'
                  ? '#4b4b6a'
                  : `linear-gradient(135deg, ${selectedOption.color}, ${selectedOption.color}cc)`,
                color: '#fff',
                fontSize: '15px',
                fontWeight: 700,
                cursor: stage === 'sending' ? 'not-allowed' : 'pointer',
                transition: 'opacity 0.15s',
              }}
            >
              {stage === 'sending' ? 'Enviando...' : `Enviar ${selectedOption.emoji}`}
            </button>

            <p style={{ textAlign: 'center', color: '#6b7280', fontSize: '11px', marginTop: '12px', marginBottom: 0 }}>
              Pantalla actual: <code style={{ color: '#a78bfa' }}>{location.pathname}</code>
            </p>
          </div>
        </div>
      )}

      {/* Success toast */}
      {stage === 'success' && (
        <div
          style={{
            position: 'fixed',
            bottom: '90px',
            left: '50%',
            transform: 'translateX(-50%)',
            zIndex: 300,
            background: '#065f46',
            color: '#d1fae5',
            padding: '12px 20px',
            borderRadius: '12px',
            fontSize: '14px',
            fontWeight: 600,
            boxShadow: '0 4px 20px rgba(0,0,0,0.4)',
            animation: 'fadeIn 0.2s ease',
            whiteSpace: 'nowrap',
          }}
        >
          ✅ ¡Reporte enviado! Gracias por ayudarnos a mejorar.
        </div>
      )}

      <style>{`
        @keyframes slideUp {
          from { transform: translateY(100%); opacity: 0; }
          to { transform: translateY(0); opacity: 1; }
        }
        @keyframes fadeIn {
          from { opacity: 0; transform: translateX(-50%) translateY(8px); }
          to { opacity: 1; transform: translateX(-50%) translateY(0); }
        }
      `}</style>
    </>
  );
}

import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { chatAssistant, getAssistantState, getDealsMenu, formatCurrency } from '../lib/api';
import { toast } from 'react-hot-toast';
import { useCart } from '../context/CartContext';

interface MealPlanItem {
  name: string;
  query: string;
  price: number | null;
  status: 'found' | 'not_found';
  image_url?: string;
  brand?: string;
  qty?: number;
  total?: number | null;
}

interface MealPlanStore {
  store: string;
  store_slug: string;
  emoji: string;
  total_cost: number;
  is_optimal: boolean;
  is_cheapest: boolean;
  found_count: number;
  total_items: number;
  items: MealPlanItem[];
}

interface AssistantState {
  budget: number | null;
  persons: number;
}

interface DealHighlight {
  name: string;
  store: string;
  store_slug: string;
  price: number;
  list_price: number | null;
  discount_percent: number | null;
  savings_amount: number | null;
  image_url: string;
  category: string;
  qty: number;
}

interface Message {
  role: 'user' | 'assistant';
  content: string;
  mealPlans?: MealPlanStore[];
  dealsHighlight?: DealHighlight[];
  estimatedSavings?: number;
}

// Quick-reply chip options
const BUDGET_CHIPS = [
  { label: '10 lucas', value: 'Tengo 10 lucas' },
  { label: '20 lucas', value: 'Tengo 20 lucas' },
  { label: '30 lucas', value: 'Tengo 30 lucas' },
  { label: '50 lucas', value: 'Tengo 50 lucas' },
];
const CONTEXT_CHIPS = [
  { label: '2 personas', value: 'Somos 2 personas' },
  { label: '4 personas', value: 'Somos 4 personas' },
  { label: 'Nuevo menú', value: 'Quiero un menú diferente' },
];

// Store colour map
const STORE_STYLES: Record<string, { bg: string; border: string; badge: string }> = {
  optimal:       { bg: 'bg-primary/10 dark:bg-primary/10',            border: 'border-primary/40',              badge: 'bg-primary text-white' },
  jumbo:         { bg: 'bg-blue-50 dark:bg-blue-900/20',              border: 'border-blue-300 dark:border-blue-700/50', badge: 'bg-blue-500 text-white' },
  lider:         { bg: 'bg-yellow-50 dark:bg-yellow-900/20',          border: 'border-yellow-300 dark:border-yellow-700/50', badge: 'bg-yellow-500 text-white' },
  unimarc:       { bg: 'bg-emerald-50 dark:bg-emerald-900/20',        border: 'border-emerald-300 dark:border-emerald-700/50', badge: 'bg-emerald-500 text-white' },
  'santa-isabel':{ bg: 'bg-red-50 dark:bg-red-900/20',               border: 'border-red-300 dark:border-red-700/50',      badge: 'bg-red-500 text-white' },
  santaisabel:   { bg: 'bg-red-50 dark:bg-red-900/20',               border: 'border-red-300 dark:border-red-700/50',      badge: 'bg-red-500 text-white' },
};

function getStoreStyle(slug: string) {
  return STORE_STYLES[slug] ?? { bg: 'bg-slate-50 dark:bg-[#14261c]', border: 'border-slate-200 dark:border-slate-700', badge: 'bg-slate-500 text-white' };
}

// ── Plan detail drawer ─────────────────────────────────────────────────────────
const PlanDrawer: React.FC<{
  plan: MealPlanStore;
  onClose: () => void;
  onAddToCart: (plan: MealPlanStore) => void;
}> = ({ plan, onClose, onAddToCart }) => {
  const style = getStoreStyle(plan.store_slug);
  const foundItems   = plan.items.filter(i => i.status === 'found');
  const missingItems = plan.items.filter(i => i.status === 'not_found');

  return (
    <div className="fixed inset-0 z-50 flex flex-col justify-end" onClick={onClose}>
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" />

      {/* Sheet */}
      <div
        className="relative bg-white dark:bg-[#0a150f] rounded-t-3xl max-h-[85vh] flex flex-col shadow-2xl"
        onClick={e => e.stopPropagation()}
      >
        {/* Handle */}
        <div className="flex justify-center pt-3 pb-1">
          <div className="w-10 h-1 rounded-full bg-slate-200 dark:bg-slate-700" />
        </div>

        {/* Header */}
        <div className={`mx-4 mb-3 rounded-2xl p-4 border ${style.bg} ${style.border}`}>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="text-2xl">{plan.emoji}</span>
              <div>
                <p className="font-black text-sm text-slate-900 dark:text-white">{plan.store}</p>
                <p className="text-[10px] text-slate-500">{foundItems.length}/{plan.total_items} productos encontrados</p>
              </div>
            </div>
            <div className="text-right">
              {plan.is_optimal && (
                <span className={`text-[9px] font-black px-2 py-1 rounded-full mb-1 block ${style.badge}`}>ÓPTIMO</span>
              )}
              {plan.is_cheapest && !plan.is_optimal && (
                <span className={`text-[9px] font-black px-2 py-1 rounded-full mb-1 block ${style.badge}`}>MÁS BARATO</span>
              )}
              <p className="font-black text-xl text-primary">{formatCurrency(plan.total_cost)}</p>
            </div>
          </div>
        </div>

        {/* Items list */}
        <div className="overflow-y-auto flex-1 px-4 space-y-2">
          {foundItems.map((it, i) => (
            <div key={i} className="flex items-center gap-3 bg-slate-50 dark:bg-[#14261c] rounded-xl p-2.5">
              {it.image_url ? (
                <img
                  src={it.image_url}
                  alt={it.name}
                  className="size-11 rounded-lg object-contain bg-white dark:bg-[#0a150f] shrink-0"
                  onError={e => { (e.target as HTMLImageElement).style.display = 'none'; }}
                />
              ) : (
                <div className="size-11 rounded-lg bg-slate-200 dark:bg-slate-700 shrink-0 flex items-center justify-center">
                  <span className="material-symbols-outlined text-slate-400 text-base">image</span>
                </div>
              )}
              <div className="flex-1 min-w-0">
                <p className="text-xs font-bold text-slate-800 dark:text-white leading-tight line-clamp-2">{it.name || it.query}</p>
                {it.brand && <p className="text-[10px] text-slate-400">{it.brand}</p>}
                <p className="text-[10px] text-slate-400 mt-0.5">{it.qty} unidad{it.qty > 1 ? 'es' : ''}</p>
              </div>
              <div className="text-right shrink-0">
                <p className="text-xs font-bold text-slate-500">{formatCurrency(it.price)}</p>
                <p className="text-sm font-black text-primary">{formatCurrency(it.total)}</p>
              </div>
            </div>
          ))}

          {missingItems.length > 0 && (
            <div className="pt-2">
              <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2">No encontrados</p>
              {missingItems.map((it, i) => (
                <div key={i} className="flex items-center gap-2 px-3 py-2 rounded-xl bg-slate-100/60 dark:bg-white/5 mb-1.5">
                  <span className="material-symbols-outlined text-slate-400 text-base">search_off</span>
                  <p className="text-xs text-slate-400 italic">{it.name || it.query}</p>
                </div>
              ))}
            </div>
          )}
          <div className="h-4" />
        </div>

        {/* CTA */}
        <div className="px-4 py-4 border-t border-slate-100 dark:border-white/5">
          <button
            onClick={() => onAddToCart(plan)}
            className="w-full py-4 rounded-2xl bg-primary text-black font-black text-base active:scale-95 transition-all flex items-center justify-center gap-2 shadow-lg shadow-primary/30"
          >
            <span className="material-symbols-outlined text-xl">shopping_cart</span>
            Agregar al Carro · {formatCurrency(plan.total_cost)}
          </button>
        </div>
      </div>
    </div>
  );
};

// ── Per-store plan card ────────────────────────────────────────────────────────
const StorePlanCard: React.FC<{
  plan: MealPlanStore;
  cheapestCost: number;
  onSelect: (plan: MealPlanStore) => void;
}> = ({ plan, cheapestCost, onSelect }) => {
  const style  = getStoreStyle(plan.store_slug);
  const saving = plan.store_slug !== 'optimal' && cheapestCost > 0
    ? plan.total_cost - cheapestCost
    : 0;

  return (
    <button
      onClick={() => onSelect(plan)}
      className={`snap-start shrink-0 w-[220px] rounded-2xl border p-4 flex flex-col gap-3 text-left active:scale-95 transition-all cursor-pointer ${style.bg} ${style.border}`}
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="text-lg leading-none">{plan.emoji}</div>
          <p className="font-black text-xs mt-1 leading-tight text-slate-900 dark:text-white">{plan.store}</p>
        </div>
        <div className="flex flex-col items-end gap-1 shrink-0">
          {plan.is_optimal && (
            <span className={`text-[9px] font-black px-1.5 py-0.5 rounded ${style.badge}`}>ÓPTIMO</span>
          )}
          {plan.is_cheapest && !plan.is_optimal && (
            <span className={`text-[9px] font-black px-1.5 py-0.5 rounded ${style.badge}`}>MÁS BARATO</span>
          )}
          {saving > 0 && (
            <span className="text-[9px] font-bold text-red-400">+{formatCurrency(saving)}</span>
          )}
        </div>
      </div>

      {/* Items (capped at 5 visible) */}
      <div className="flex flex-col gap-1 flex-1">
        {plan.items.slice(0, 5).map((it: any, ii: number) => (
          <div key={ii} className="flex justify-between gap-1 text-[10px]">
            <span className={`truncate max-w-[120px] ${it.status === 'not_found' ? 'text-slate-400 italic' : 'text-slate-700 dark:text-slate-300'}`}>
              {it.name || it.query}
            </span>
            <span className={`font-bold shrink-0 ${it.status === 'not_found' ? 'text-slate-400' : 'text-slate-900 dark:text-white'}`}>
              {it.status === 'not_found' ? '–' : formatCurrency(it.price)}
            </span>
          </div>
        ))}
        {plan.items.length > 5 && (
          <p className="text-[9px] text-slate-400 mt-0.5">+{plan.items.length - 5} ingredientes más</p>
        )}
      </div>

      {/* Total */}
      <div className="pt-2 border-t border-slate-200/60 dark:border-white/10 flex justify-between items-end">
        <span className="text-[9px] uppercase font-black tracking-widest text-slate-400">Total</span>
        <span className="font-black text-base text-primary">{formatCurrency(plan.total_cost)}</span>
      </div>

      {/* Tap hint */}
      <p className="text-[9px] text-slate-400 flex items-center gap-0.5 -mt-1">
        <span className="material-symbols-outlined text-[11px]">touch_app</span>
        Toca para ver detalle
      </p>
    </button>
  );
};

// ── Deals highlight strip ─────────────────────────────────────────────────────
const CAT_EMOJI: Record<string, string> = {
  protein: '🥩', carbs: '🍚', dairy: '🥛', vegetables: '🥦', eggs: '🥚', legumes: '🫘',
};

const DealsHighlightBar: React.FC<{ deals: DealHighlight[]; savings: number }> = ({ deals, savings }) => {
  if (!deals || deals.length === 0) return null;
  return (
    <div className="mt-3 space-y-2">
      {savings > 0 && (
        <div className="flex items-center gap-1.5 text-[10px] font-black text-primary">
          <span className="material-symbols-outlined text-sm">local_fire_department</span>
          Menú construido con ofertas de hoy · ahorras ~{formatCurrency(savings)} vs. precio normal
        </div>
      )}
      <div className="flex gap-2 overflow-x-auto pb-1 -mx-1 px-1">
        {deals.map((d, i) => (
          <div
            key={i}
            className="shrink-0 flex flex-col gap-1 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-700/40 rounded-xl p-2.5 w-[130px]"
          >
            <div className="flex items-center justify-between">
              <span className="text-base">{CAT_EMOJI[d.category] ?? '🛒'}</span>
              {d.discount_percent != null && (
                <span className="text-[9px] font-black bg-red-500 text-white px-1.5 py-0.5 rounded-full">
                  -{Math.round(d.discount_percent)}%
                </span>
              )}
            </div>
            <p className="text-[10px] font-bold text-slate-800 dark:text-white leading-tight line-clamp-2">{d.name}</p>
            <p className="text-[9px] text-slate-500">{d.store}</p>
            <p className="text-xs font-black text-primary">{formatCurrency(d.price)}</p>
            {d.list_price && d.list_price > d.price && (
              <p className="text-[9px] text-slate-400 line-through">{formatCurrency(d.list_price)}</p>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};

// ── Meal plans horizontal scroll ──────────────────────────────────────────────
const MealPlanScroll: React.FC<{
  plans: MealPlanStore[];
  onSelect: (plan: MealPlanStore) => void;
}> = ({ plans, onSelect }) => {
  if (!plans || plans.length === 0) return null;

  const storePlans    = plans.filter(p => !p.is_optimal);
  const cheapestCost  = storePlans.length > 0 ? Math.min(...storePlans.map(p => p.total_cost)) : 0;
  const mostExpensive = storePlans.length > 0 ? Math.max(...storePlans.map(p => p.total_cost)) : 0;
  const maxSaving     = mostExpensive - cheapestCost;

  return (
    <div className="mt-3">
      {maxSaving > 500 && (
        <p className="text-[10px] font-black text-primary mb-2 flex items-center gap-1">
          <span className="material-symbols-outlined text-sm">savings</span>
          Podrías ahorrar hasta {formatCurrency(maxSaving)} eligiendo bien
        </p>
      )}
      <div className="flex gap-3 overflow-x-auto pb-3 -mx-1 px-1 snap-x snap-mandatory">
        {plans.map((plan) => (
          <StorePlanCard key={plan.store_slug} plan={plan} cheapestCost={cheapestCost} onSelect={onSelect} />
        ))}
      </div>
    </div>
  );
};

// ── Main Component ─────────────────────────────────────────────────────────────
const ShoppingAssistant: React.FC = () => {
  const navigate = useNavigate();
  const { addItem } = useCart();

  const [messages, setMessages]         = useState<Message[]>([]);
  const [input, setInput]               = useState('');
  const [isLoading, setIsLoading]       = useState(false);
  const [state, setState]               = useState<AssistantState | null>(null);
  const [showChips, setShowChips]       = useState(true);
  const [selectedPlan, setSelectedPlan] = useState<MealPlanStore | null>(null);

  const scrollRef = useRef<HTMLDivElement>(null);
  const mountedRef = useRef(true);
  const loadingTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; };
  }, []);

  const handleAddToCart = (plan: MealPlanStore) => {
    plan.items.filter(i => i.status === 'found').forEach(item => {
      addItem({
        product_id: `${plan.store_slug}-${item.query}`,
        name: item.name,
        brand: item.brand || '',
        image_url: item.image_url || '',
        price: item.price || 0,
        store_slug: plan.store_slug,
        store_name: plan.store,
      });
    });
    setSelectedPlan(null);
    toast.success(`Plan de ${plan.store} guardado en tu carro`, { duration: 2500 });
    navigate('/cart');
  };

  useEffect(() => {
    let cancelled = false;
    const init = async () => {
      try {
        const s = await getAssistantState();
        if (cancelled || !mountedRef.current) return;
        setState(s);

        let content: string;
        if (s?.budget) {
          content =
            `¡Bienvenido de vuelta! La última vez trabajamos con ` +
            `${formatCurrency(s.budget)} para ${s.persons ?? 1} ` +
            `${(s.persons ?? 1) > 1 ? 'personas' : 'persona'}.\n\n` +
            `¿Seguimos con ese presupuesto o tienes uno nuevo esta semana? ` +
            `Responde "dale" para repetir el menú o dime tu nuevo monto.`;
        } else {
          content =
            `¡Hola! Soy KAIROS, tu asistente de ahorro para supermercados chilenos 🛒\n\n` +
            `Comparo precios en tiempo real entre Jumbo, Lider, Unimarc y Santa Isabel. ` +
            `Con tu presupuesto te armo menús para la semana y te muestro cuánto cuesta ` +
            `en cada tienda para que elijas el más conveniente.\n\n` +
            `¿Cuánto tienes disponible esta semana?`;
        }
        setMessages([{ role: 'assistant', content }]);
      } catch {
        if (cancelled || !mountedRef.current) return;
        setMessages([{
          role: 'assistant',
          content:
            '¡Hola! Soy KAIROS, tu asistente de ahorro. ' +
            '¿Cuánto tienes para gastar esta semana? ' +
            'Te armo menús comparados por supermercado.'
        }]);
      }
    };
    init();
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, isLoading]);

  const sendMessage = async (text: string) => {
    if (!text.trim() || isLoading) return;
    setShowChips(false);

    const userMsg: Message = { role: 'user', content: text };
    const newMessages = [...messages, userMsg];
    setMessages(newMessages);
    setInput('');
    setIsLoading(true);

    // Seguridad: si en 14s no hay respuesta, mostramos error y liberamos el loading
    if (loadingTimerRef.current) clearTimeout(loadingTimerRef.current);
    loadingTimerRef.current = setTimeout(() => {
      if (!mountedRef.current) return;
      setIsLoading(false);
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: 'El servidor tardó demasiado. Verifica tu conexión e intenta de nuevo.',
      }]);
    }, 14_000);

    try {
      const response = await chatAssistant(newMessages.map(m => ({ role: m.role, content: m.content })));
      if (!mountedRef.current) return;
      const assistantMsg: Message = {
        role: 'assistant',
        content: response.reply || '(sin respuesta del servidor)',
        mealPlans: response.meal_plans,
      };
      setMessages(prev => [...prev, assistantMsg]);
      if (response.state) setState(response.state);
      setShowChips(!response.meal_plans);
    } catch (err: any) {
      if (!mountedRef.current) return;
      const errMsg = err?.message || String(err) || 'Error desconocido';
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: `⚠️ Error: ${errMsg}`,
      }]);
    } finally {
      if (loadingTimerRef.current) clearTimeout(loadingTimerRef.current);
      if (mountedRef.current) setIsLoading(false);
    }
  };

  const handleSend = () => sendMessage(input);
  const handleChip = (value: string) => sendMessage(value);

  const handleDealsMenu = async () => {
    if (isLoading) return;
    setShowChips(false);
    const persons = state?.persons ?? 2;
    const userMsg: Message = { role: 'user', content: `🔥 Generar menú con las ofertas de hoy (${persons} persona${persons > 1 ? 's' : ''})` };
    setMessages(prev => [...prev, userMsg]);
    setIsLoading(true);
    try {
      const data = await getDealsMenu(persons);
      const assistantMsg: Message = {
        role: 'assistant',
        content: data.reply || 'Menú de ofertas generado.',
        mealPlans: data.meal_plans,
        dealsHighlight: data.deals_highlight,
        estimatedSavings: data.estimated_savings,
      };
      setMessages(prev => [...prev, assistantMsg]);
    } catch (err: any) {
      setMessages(prev => [...prev, { role: 'assistant', content: `⚠️ Error al obtener ofertas: ${err?.message ?? 'Error desconocido'}` }]);
    } finally {
      setIsLoading(false);
    }
  };

  // Chips to show: budget chips if no budget, context chips if has budget
  const chips = state?.budget ? CONTEXT_CHIPS : BUDGET_CHIPS;

  return (
    <div className="flex flex-col h-[calc(100vh-80px)] bg-slate-50 dark:bg-[#050c08]">
      {/* Plan detail drawer */}
      {selectedPlan && (
        <PlanDrawer
          plan={selectedPlan}
          onClose={() => setSelectedPlan(null)}
          onAddToCart={handleAddToCart}
        />
      )}

      {/* Header */}
      <header className="px-4 py-3 bg-white dark:bg-[#0a150f] border-b border-slate-200 dark:border-slate-800 flex items-center gap-3">
        <div className="size-10 rounded-full bg-primary flex items-center justify-center text-background-dark shrink-0">
          <span className="material-symbols-outlined text-2xl font-black">auto_awesome</span>
        </div>
        <div className="flex-1 min-w-0">
          <h1 className="font-black text-base leading-tight">Asistente KAIROS</h1>
          <p className="text-[10px] text-primary font-bold uppercase tracking-widest flex items-center gap-1">
            <span className="size-1.5 rounded-full bg-primary animate-pulse" />
            En línea · IA de Ahorro
          </p>
        </div>
        {/* Budget badge */}
        {state?.budget && (
          <div className="flex items-center gap-1.5 bg-primary/10 rounded-full px-3 py-1.5 shrink-0">
            <span className="material-symbols-outlined text-primary text-sm">account_balance_wallet</span>
            <span className="text-[11px] font-black text-primary">
              {formatCurrency(state.budget)}
              {state.persons > 1 ? ` · ${state.persons}p` : ''}
            </span>
          </div>
        )}
        {/* Deals Menu shortcut */}
        <button
          onClick={handleDealsMenu}
          disabled={isLoading}
          title="Menú de Hoy — construido con las mejores ofertas activas"
          className="shrink-0 flex items-center gap-1 bg-amber-400/20 border border-amber-400/40 text-amber-600 dark:text-amber-400 rounded-full px-2.5 py-1.5 text-[11px] font-black active:scale-95 transition-all disabled:opacity-40"
        >
          <span className="text-sm">🔥</span>
          Hoy
        </button>
      </header>

      {/* Store comparison legend */}
      <div className="flex items-center gap-2 px-4 py-1.5 bg-slate-100 dark:bg-[#0d1a12] border-b border-slate-200/60 dark:border-white/5 overflow-x-auto">
        {[
          { emoji: '⭐', name: 'Óptimo' },
          { emoji: '🔵', name: 'Jumbo' },
          { emoji: '🟡', name: 'Lider' },
          { emoji: '🟢', name: 'Unimarc' },
          { emoji: '🔴', name: 'Sta. Isabel' },
        ].map(s => (
          <span key={s.name} className="flex items-center gap-1 text-[10px] text-slate-500 dark:text-slate-400 shrink-0">
            <span>{s.emoji}</span>{s.name}
          </span>
        ))}
        <span className="text-[9px] text-slate-400 ml-auto shrink-0">↔ desliza las tarjetas</span>
      </div>

      {/* Messages */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-5">
        {messages.map((m, i) => (
          <div key={i} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-[90%] rounded-2xl p-4 shadow-sm ${
              m.role === 'user'
                ? 'bg-primary text-background-dark rounded-tr-none'
                : 'bg-white dark:bg-[#0a150f] border border-slate-200 dark:border-slate-800 rounded-tl-none'
            }`}>
              {/* Message text: preserve line breaks */}
              {m.content.split('\n').map((line, li) => (
                <p key={li} className={`text-sm leading-relaxed ${li > 0 && line === '' ? 'mt-2' : li > 0 ? 'mt-1' : ''}`}>
                  {line}
                </p>
              ))}

              {/* Today's deals strip */}
              {m.dealsHighlight && m.dealsHighlight.length > 0 && (
                <DealsHighlightBar deals={m.dealsHighlight} savings={m.estimatedSavings ?? 0} />
              )}

              {/* Per-store meal plan cards */}
              {m.mealPlans && (
                <MealPlanScroll plans={m.mealPlans} onSelect={setSelectedPlan} />
              )}
            </div>
          </div>
        ))}

        {/* Typing indicator */}
        {isLoading && (
          <div className="flex justify-start">
            <div className="bg-white dark:bg-[#0a150f] border border-slate-200 dark:border-slate-800 rounded-2xl rounded-tl-none p-4 flex items-center gap-2">
              <span className="size-2 rounded-full bg-primary animate-bounce" />
              <span className="size-2 rounded-full bg-primary animate-bounce [animation-delay:0.15s]" />
              <span className="size-2 rounded-full bg-primary animate-bounce [animation-delay:0.30s]" />
            </div>
          </div>
        )}
      </div>

      {/* Quick-reply chips */}
      {showChips && !isLoading && (
        <div className="flex gap-2 px-4 py-2 overflow-x-auto bg-white dark:bg-[#0a150f] border-t border-slate-100 dark:border-slate-800/60">
          {chips.map(chip => (
            <button
              key={chip.value}
              onClick={() => handleChip(chip.value)}
              className="shrink-0 px-3 py-1.5 rounded-full border border-primary/40 text-primary text-[11px] font-bold bg-primary/5 hover:bg-primary/15 active:scale-95 transition-all"
            >
              {chip.label}
            </button>
          ))}
        </div>
      )}

      {/* Input area */}
      <footer className="p-4 bg-white dark:bg-[#0a150f] border-t border-slate-200 dark:border-slate-800">
        <div className="flex items-center gap-2">
          <input
            type="text"
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') handleSend(); }}
            onFocus={() => setShowChips(false)}
            disabled={isLoading}
            placeholder={state?.budget ? 'Escríbeme algo...' : '¿Cuánto tienes para esta semana?'}
            className="flex-1 bg-slate-100 dark:bg-[#14261c] border-none rounded-full px-5 py-3 text-sm focus:ring-2 focus:ring-primary transition-all disabled:opacity-50 outline-none"
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || isLoading}
            className="size-11 rounded-full bg-primary text-background-dark flex items-center justify-center disabled:opacity-40 transition-all hover:scale-105 active:scale-95 shrink-0"
          >
            <span className="material-symbols-outlined">send</span>
          </button>
        </div>
        <p className="text-center text-[9px] text-slate-400 mt-2 font-medium tracking-wide">
          KAIROS compara precios en Jumbo · Lider · Unimarc · Santa Isabel
        </p>
      </footer>
    </div>
  );
};

export default ShoppingAssistant;

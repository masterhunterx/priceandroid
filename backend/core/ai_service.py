"""
KAIROS AI Service — Arquitectura Desacoplada
=============================================
  • Extracción de presupuesto/personas  → regex local (instantáneo, confiable)
  • Generación de menú + precios reales → motor local + consulta BD real
  • Respuesta conversacional natural    → IA externa (solo texto, nunca JSON)

Proveedores (en orden de prioridad):
  1. OpenRouter  (OPENROUTER_API_KEY) — modelos gratuitos, API OpenAI-compatible
  2. HuggingFace (HUGGINGFACE_TOKEN) — InferenceClient, modelos gratuitos
  3. Motor local                      — fallback instantáneo, siempre disponible
"""

import os
import re
import logging
import threading
from dotenv import load_dotenv
load_dotenv()

from typing import List, Dict, Any, Optional

logger = logging.getLogger("FreshCartAPI")

# ── Configuración ──────────────────────────────────────────────────────────────
OPENROUTER_MODELS = [
    "meta-llama/llama-3.2-3b-instruct:free",
    "mistralai/mistral-7b-instruct:free",
]
HF_MODEL = "Qwen/Qwen2.5-72B-Instruct"

AI_MAX_TOKENS   = 120   # Solo texto conversacional corto
AI_TIMEOUT_SECS = 5     # Timeout agresivo: siempre responde antes del timeout de 15s del frontend
MAX_HISTORY_TURNS = 6


# ── Menús base por tier de presupuesto ────────────────────────────────────────
_MENUS = {
    "micro": {
        "label": "Ultra-Económico",
        "intro": "Con ese presupuesto ajustado te armo lo más esencial",
        "menu": {
            "title": "Semana Ultra-Económica · Lo Básico",
            "ingredients": [
                {"query": "fideos espiral 500g",       "qty": 2},
                {"query": "arroz 1 kilo",               "qty": 1},
                {"query": "porotos 500g",               "qty": 1},
                {"query": "huevos blancos docena",      "qty": 1},
                {"query": "aceite maravilla 900ml",     "qty": 1},
                {"query": "salsa de tomate 200g",       "qty": 2},
                {"query": "cebolla",                    "qty": 1},
            ]
        }
    },
    "low": {
        "label": "Económico",
        "intro": "Con ese presupuesto te armo una semana completa con proteína incluida",
        "menu": {
            "title": "Semana Económica · Con Proteína",
            "ingredients": [
                {"query": "pollo trozado 1 kilo",       "qty": 1},
                {"query": "fideos espiral 500g",        "qty": 2},
                {"query": "arroz grado 1 kilo",         "qty": 1},
                {"query": "huevos blancos docena",      "qty": 1},
                {"query": "aceite maravilla 900ml",     "qty": 1},
                {"query": "salsa de tomate 200g",       "qty": 2},
                {"query": "zanahoria",                  "qty": 1},
                {"query": "cebolla",                    "qty": 1},
                {"query": "ajo",                        "qty": 1},
            ]
        }
    },
    "medium": {
        "label": "Balanceado",
        "intro": "Buen presupuesto, te armo una semana muy completa y variada",
        "menu": {
            "title": "Semana Balanceada · Variedad y Nutrición",
            "ingredients": [
                {"query": "pechuga de pollo 1 kilo",    "qty": 1},
                {"query": "carne molida 500g",          "qty": 1},
                {"query": "fideos spaghetti 500g",      "qty": 2},
                {"query": "arroz grado 1 kilo",         "qty": 1},
                {"query": "huevos blancos docena",      "qty": 1},
                {"query": "leche entera 1 litro",       "qty": 2},
                {"query": "aceite maravilla 900ml",     "qty": 1},
                {"query": "tomate",                     "qty": 2},
                {"query": "lechuga",                    "qty": 1},
                {"query": "zanahoria",                  "qty": 1},
                {"query": "cebolla",                    "qty": 1},
                {"query": "pan molde",                  "qty": 1},
            ]
        }
    },
    "high": {
        "label": "Completo",
        "intro": "Excelente presupuesto, te armo una semana con mucha variedad y calidad",
        "menu": {
            "title": "Semana Completa · Calidad y Variedad",
            "ingredients": [
                {"query": "filete de pollo 1 kilo",     "qty": 1},
                {"query": "carne molida 500g",          "qty": 1},
                {"query": "atun en trozos lata",        "qty": 2},
                {"query": "fideos spaghetti 500g",      "qty": 2},
                {"query": "arroz grado 1 kilo",         "qty": 1},
                {"query": "huevos blancos docena",      "qty": 1},
                {"query": "leche entera 1 litro",       "qty": 3},
                {"query": "queso laminado",             "qty": 1},
                {"query": "yogurt natural",             "qty": 4},
                {"query": "aceite maravilla 900ml",     "qty": 1},
                {"query": "tomate",                     "qty": 2},
                {"query": "lechuga",                    "qty": 1},
                {"query": "palta",                      "qty": 2},
                {"query": "manzana 1 kilo",             "qty": 1},
                {"query": "pan molde integral",         "qty": 1},
            ]
        }
    },
    "premium": {
        "label": "Premium",
        "intro": "Con ese presupuesto te armo una semana gourmet y muy nutritiva",
        "menu": {
            "title": "Semana Premium · Gourmet y Completa",
            "ingredients": [
                {"query": "pechuga de pollo 1 kilo",    "qty": 2},
                {"query": "carne vacuno bistec",        "qty": 1},
                {"query": "salmon filete 300g",         "qty": 1},
                {"query": "pasta spaghetti 500g",       "qty": 2},
                {"query": "arroz grano largo 1 kilo",   "qty": 1},
                {"query": "huevos blancos docena",      "qty": 1},
                {"query": "leche entera 1 litro",       "qty": 3},
                {"query": "queso mantecoso",            "qty": 1},
                {"query": "yogurt griego",              "qty": 4},
                {"query": "aceite oliva",               "qty": 1},
                {"query": "tomate",                     "qty": 3},
                {"query": "lechuga hidroponica",        "qty": 1},
                {"query": "palta",                      "qty": 3},
                {"query": "brocoli",                    "qty": 1},
                {"query": "zapallo italiano",           "qty": 1},
                {"query": "manzana 1 kilo",             "qty": 1},
                {"query": "pan molde integral",         "qty": 1},
            ]
        }
    },
}


def _get_tier(budget_per_person: float) -> str:
    if budget_per_person < 8_000:   return "micro"
    if budget_per_person < 18_000:  return "low"
    if budget_per_person < 35_000:  return "medium"
    if budget_per_person < 65_000:  return "high"
    return "premium"


# ── Extractores locales confiables ─────────────────────────────────────────────

def _extract_budget(text: str) -> Optional[float]:
    t = text.lower().replace(".", "").replace(",", "")
    m = re.search(r'(\d+(?:\.\d+)?)\s*(lucas?|luca|mil|miles|k\b)', t)
    if m:
        return float(m.group(1)) * 1000
    m = re.search(r'\$?\s*(\d{4,8})', t)
    if m:
        val = float(m.group(1))
        if val >= 1000:
            return val
    return None


def _extract_persons(text: str) -> Optional[int]:
    t = text.lower()
    m = re.search(r'(\d+)\s*(?:persona|persone|adulto|gente)', t)
    if m: return int(m.group(1))
    m = re.search(r'somos\s+(\d+)', t)
    if m: return int(m.group(1))
    if re.search(r'\bsoy solo\b|\bsolo yo\b|\bpara mi\b|\bpara m[íi]\b', t):
        return 1
    return None


# ── Servicio principal ─────────────────────────────────────────────────────────

class KairosAIService:

    def __init__(self):
        self._openrouter = self._init_openrouter()
        self._hf         = self._init_huggingface()

    def _init_openrouter(self):
        key = os.getenv("OPENROUTER_API_KEY", "").strip()
        if not key:
            logger.info("[KAIROS] OPENROUTER_API_KEY no configurada.")
            return None
        try:
            from openai import OpenAI
            client = OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=key,
                max_retries=0,  # fallback manual a HF, no reintentos automáticos
                timeout=AI_TIMEOUT_SECS,
                default_headers={
                    "HTTP-Referer": "https://freshcart.app",
                    "X-Title": "KAIROS Grocery Assistant",
                },
            )
            logger.info("[KAIROS] OpenRouter listo → %s", OPENROUTER_MODELS[0])
            return client
        except Exception as e:
            logger.warning("[KAIROS] OpenRouter init falló: %s", e)
            return None

    def _init_huggingface(self):
        token = os.getenv("HUGGINGFACE_TOKEN", "").strip()
        if not token:
            logger.info("[KAIROS] HUGGINGFACE_TOKEN no configurado.")
            return None
        try:
            from huggingface_hub import InferenceClient
            client = InferenceClient(token=token)
            logger.info("[KAIROS] HuggingFace listo → %s", HF_MODEL)
            return client
        except Exception as e:
            logger.warning("[KAIROS] HuggingFace init falló: %s", e)
            return None

    # ── API pública ────────────────────────────────────────────────────────────

    def get_chat_response(
        self,
        messages: List[Dict[str, str]],
        context: Dict[str, Any],
        saved_history: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        user_text  = messages[-1]["content"].strip() if messages else ""
        user_lower = user_text.lower()

        stored_budget  = context.get("budget")
        stored_persons = context.get("persons") or 1

        new_budget  = _extract_budget(user_lower)
        new_persons = _extract_persons(user_lower)

        eff_budget  = new_budget  or stored_budget
        eff_persons = new_persons or stored_persons or 1

        is_greeting = any(k in user_lower for k in ["hola", "hi", "buenas", "hey", "kairos"])

        meal_plan = None
        if eff_budget:
            tier  = _get_tier(eff_budget / eff_persons)
            tdata = _MENUS[tier]
            meal_plan = {
                "title": f"{tdata['menu']['title']} · {eff_persons}p",
                "ingredients": [
                    {"query": i["query"], "qty": max(1, round(i["qty"] * eff_persons))}
                    for i in tdata["menu"]["ingredients"]
                ]
            }

        # Filtrar historial corrupto (turnos con JSON del asistente)
        clean_history = [
            m for m in (saved_history or [])[-(MAX_HISTORY_TURNS * 2):]
            if not (m.get("role") == "assistant" and m.get("content", "").startswith("{"))
        ]

        reply = self._get_reply(user_text, eff_budget, eff_persons, meal_plan, is_greeting, clean_history)

        return {
            "reply":     reply,
            "budget":    eff_budget  if new_budget  else None,
            "persons":   eff_persons if new_persons else None,
            "meal_plan": meal_plan,
        }

    # ── Respuesta conversacional ───────────────────────────────────────────────

    def _get_reply(self, user_text, budget, persons, meal_plan, is_greeting, history):
        if not budget and not is_greeting:
            return self._local_ask_budget()

        sys_prompt = (
            "Eres KAIROS, asistente de ahorro para supermercados chilenos. "
            "Responde SOLO en español, máximo 2 oraciones, tono amigable. "
            "NUNCA uses JSON, listas ni caracteres especiales."
        )
        if budget:
            sys_prompt += (
                f" El usuario tiene ${budget:,.0f} CLP para {persons} persona(s). "
                "Ya generamos el plan de compras por tienda."
            )

        ai_reply = self._call_ai_text(sys_prompt, history, user_text[:200])
        return ai_reply if ai_reply else self._local_reply(budget, persons, is_greeting)

    def _call_ai_text(self, system: str, history: List[Dict], user_msg: str) -> Optional[str]:
        """Llama IA en hilo daemon con timeout estricto. Prueba OpenRouter → HuggingFace."""
        result: Dict = {}

        def _try_openrouter():
            if not self._openrouter:
                return
            msgs = [{"role": "system", "content": system}] + history + [{"role": "user", "content": user_msg}]
            for model in OPENROUTER_MODELS:
                try:
                    comp = self._openrouter.chat.completions.create(
                        model=model,
                        messages=msgs,
                        max_tokens=AI_MAX_TOKENS,
                        temperature=0.7,
                    )
                    text = comp.choices[0].message.content.strip()
                    if self._is_valid_text(text):
                        result["text"] = text
                        logger.info("[KAIROS] OpenRouter OK (%s): %s", model, text[:50])
                        return
                except Exception as e:
                    logger.warning("[KAIROS] OpenRouter %s falló: %s", model, str(e)[:80])

        def _try_huggingface():
            if not self._hf:
                return
            msgs = [{"role": "system", "content": system}] + history + [{"role": "user", "content": user_msg}]
            try:
                comp = self._hf.chat_completion(
                    model=HF_MODEL,
                    messages=msgs,
                    max_tokens=AI_MAX_TOKENS,
                    temperature=0.7,
                )
                text = comp.choices[0].message.content.strip()
                if self._is_valid_text(text):
                    result["text"] = text
                    logger.info("[KAIROS] HuggingFace OK: %s", text[:50])
            except Exception as e:
                logger.warning("[KAIROS] HuggingFace falló: %s", e)

        # Intenta OpenRouter primero; si no hay clave, pasa a HF
        primary = _try_openrouter if self._openrouter else _try_huggingface
        t = threading.Thread(target=primary, daemon=True)
        t.start()
        t.join(timeout=AI_TIMEOUT_SECS)

        if not result.get("text") and self._hf and self._openrouter:
            # OpenRouter no respondió a tiempo → intenta HuggingFace
            t2 = threading.Thread(target=_try_huggingface, daemon=True)
            t2.start()
            t2.join(timeout=AI_TIMEOUT_SECS)

        return result.get("text")

    def _is_valid_text(self, text: str) -> bool:
        if not text or len(text) < 5:
            return False
        if text.startswith("{"):
            return False
        # Rechazar si contiene estructura JSON de nuestra API
        if "{" in text and "}" in text and any(k in text for k in ['"reply"', '"budget"', '"meal_plan"']):
            return False
        return True

    # ── Motor local de fallback ────────────────────────────────────────────────

    def _local_ask_budget(self) -> str:
        return (
            "¡Hola! Soy KAIROS, comparo precios en Jumbo, Lider, Unimarc y Santa Isabel.\n"
            "¿Cuánto tienes para esta semana? Ej: \"30 lucas\" o \"$45.000 para 4 personas\""
        )

    def _local_reply(self, budget: Optional[float], persons: int, is_greeting: bool) -> str:
        if not budget:
            return self._local_ask_budget()
        tier  = _get_tier(budget / persons)
        intro = _MENUS[tier]["intro"]
        return (
            f"{intro}.\n"
            f"Presupuesto: ${budget:,.0f} · {persons} persona{'s' if persons > 1 else ''} · "
            "Desliza las tarjetas para ver precios por tienda."
        )

    # ── Compatibilidad con scraper fallback ───────────────────────────────────

    def extract_product_fallback(self, raw_json: dict) -> Optional[Dict[str, Any]]:
        import json as _json
        client = self._openrouter or self._hf
        if not client:
            return None
        system = "Extract from the JSON: 'name'(str), 'price'(int), 'brand'(str), 'image_url'(str). Return ONLY raw JSON."
        msgs   = [{"role": "system", "content": system}, {"role": "user", "content": _json.dumps(raw_json)[:2000]}]
        try:
            if self._openrouter:
                comp = self._openrouter.chat.completions.create(model=OPENROUTER_MODELS[0], messages=msgs, max_tokens=150, temperature=0.1)
            else:
                comp = self._hf.chat_completion(model=HF_MODEL, messages=msgs, max_tokens=150, temperature=0.1)
            raw = comp.choices[0].message.content
            m = re.search(r'(\{.*\})', raw.replace('\n', ' '), re.DOTALL)
            if m:
                d = _json.loads(m.group(1))
                if "name" in d and "price" in d:
                    return d
        except Exception as e:
            logger.error("[AI-FALLBACK] %s", e)
        return None

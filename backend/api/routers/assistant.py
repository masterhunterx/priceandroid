import json
import re
import time
import logging
from collections import defaultdict
from threading import Lock
from datetime import datetime, timezone
from typing import List, Literal, Optional
from fastapi import APIRouter, Query, HTTPException, Depends, Request
from core.db import get_session
from core.models import Product, UserPreference, Notification, UserAssistantState, Price
from ..schemas import UnifiedResponse, NotificationOut, ChatRequest, OptimizeCartRequest
from ..middleware import get_api_key
from core.ai_service import KairosAIService
from domain.cart_optimizer import optimize_cart
from domain.meal_planner import MealPlannerContext, generate_per_store_plans
from ..utils import get_price_insight

logger = logging.getLogger("AntigravityAPI")

# Rate limiter para el endpoint de refresh manual (operación costosa)
_refresh_attempts: dict = defaultdict(list)
_refresh_lock = Lock()
_REFRESH_WINDOW = 60   # segundos
_REFRESH_LIMIT  = 3    # máximo 3 ejecuciones por minuto por IP

def _check_refresh_rate_limit(ip: str) -> bool:
    now = time.time()
    with _refresh_lock:
        recent = [t for t in _refresh_attempts[ip] if now - t < _REFRESH_WINDOW]
        if len(recent) >= _REFRESH_LIMIT:
            _refresh_attempts[ip] = recent
            return False
        recent.append(now)
        _refresh_attempts[ip] = recent
        return True

UTC = timezone.utc

router = APIRouter(
    prefix="/api/assistant",
    tags=["Assistant & KAIROS Intelligence"],
    dependencies=[Depends(get_api_key)]
)

from pydantic import BaseModel

from pydantic import field_validator as _fv, conint as _conint

class FavoriteAction(BaseModel):
    product_id: _conint(gt=0)
    action: Literal["add", "remove", "toggle"]

ai_service = KairosAIService()

@router.post("/optimize_cart", response_model=UnifiedResponse)
def optimize_cart_endpoint(req: OptimizeCartRequest):
    """KAIROS Intelligence: Optimizar una lista de compras para el máximo ahorro."""
    try:
        with get_session() as session:
            result = optimize_cart(session, list(req.items))
            return UnifiedResponse(data=result)
    except Exception as e:
        logger.error("[KAIROS] Error en optimize_cart: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Error interno en el motor de optimización.")


@router.get("/favorites", response_model=UnifiedResponse)
def get_favorites(
    limit: int = Query(50, ge=1, le=200, description="Máximo de favoritos a retornar"),
    offset: int = Query(0, ge=0, description="Desplazamiento para paginación"),
    current_user: str = Depends(get_api_key),
):
    """
    Listar productos marcados como favoritos.
    Soporta paginación para evitar cargas masivas con limit/offset.
    """
    user_id = current_user or "default_user"
    with get_session() as session:
        favorites = session.query(UserPreference).filter_by(user_id=user_id).offset(offset).limit(limit).all()
        product_ids = [fav.product_id for fav in favorites]
        
        if not product_ids:
            return UnifiedResponse(success=True, data=[])

        # Optimizamos mediante una consulta única in_() para todos los IDs
        products = session.query(Product).filter(Product.id.in_(product_ids)).all()
        
        results = []
        for product in products:
            results.append({
                "id": product.id,
                "name": product.canonical_name,
                "brand": product.brand,
                "category": product.category,
                "image_url": product.image_url,
                "price_insight": get_price_insight(session, product.id),
                "is_favorite": True
            })
            
        return UnifiedResponse(success=True, data=results)


@router.post("/favorites", response_model=UnifiedResponse)
def toggle_favorite(data: FavoriteAction, current_user: str = Depends(get_api_key)):
    """Alternar el estado de favorito de un producto (agregar, eliminar o toggle)."""
    user_id = current_user or "default_user"
    with get_session() as session:
        product = session.get(Product, data.product_id)
        if not product:
            raise HTTPException(status_code=404, detail="Producto no encontrado")

        pref = session.query(UserPreference).filter_by(product_id=data.product_id, user_id=user_id).first()

        if data.action == "toggle":
            if pref:
                session.delete(pref)
                msg = "Eliminado de favoritos"
                status = False
            else:
                session.add(UserPreference(product_id=data.product_id, user_id=user_id))
                msg = "Agregado a favoritos"
                status = True
        elif data.action == "remove":
            if pref:
                session.delete(pref)
            msg = "Eliminado de favoritos"
            status = False
        else:  # 'add'
            if not pref:
                session.add(UserPreference(product_id=data.product_id, user_id=user_id))
            msg = "Agregado a favoritos"
            status = True

        session.commit()
        return UnifiedResponse(success=True, data={"is_favorite": status, "message": msg})


@router.get("/notifications", response_model=UnifiedResponse)
def get_notifications(
    limit: int = Query(50, ge=1, le=100, description="Máximo de notificaciones"),
    unread_only: bool = Query(False, description="Solo no leídas"),
    current_user: str = Depends(get_api_key),
):
    """Obtener notificaciones generadas por KAIROS."""
    user_id = current_user or "default_user"
    with get_session() as session:
        query = session.query(Notification).filter(Notification.user_id == user_id)
        if unread_only:
            query = query.filter(Notification.is_read == False)

        notifs = query.order_by(Notification.created_at.desc()).limit(limit).all()
        return UnifiedResponse(data=[
            NotificationOut(
                id=n.id,
                product_id=n.product_id,
                title=n.title,
                message=n.message,
                type=n.type,
                link_url=n.link_url,
                is_read=n.is_read,
                created_at=n.created_at.isoformat() if n.created_at else ""
            ) for n in notifs
        ])


@router.post("/notifications/{notification_id}/read", response_model=UnifiedResponse)
def mark_notification_read(notification_id: int, current_user: str = Depends(get_api_key)):
    """Marcar una notificación como leída."""
    user_id = current_user or "default_user"
    with get_session() as session:
        notif = session.get(Notification, notification_id)
        if not notif or notif.user_id != user_id:
            raise HTTPException(status_code=404, detail="Notification not found")
        notif.is_read = True
        session.commit()
        return UnifiedResponse(success=True, data={"id": notification_id, "is_read": True})


@router.delete("/notifications/{notification_id}", response_model=UnifiedResponse)
def delete_notification(notification_id: int, current_user: str = Depends(get_api_key)):
    """Eliminar una notificación específica."""
    user_id = current_user or "default_user"
    with get_session() as session:
        notif = session.get(Notification, notification_id)
        if not notif or notif.user_id != user_id:
            raise HTTPException(status_code=404, detail="Notification not found")
        session.delete(notif)
        session.commit()
        return UnifiedResponse(success=True, data={"deleted": notification_id})


@router.delete("/notifications", response_model=UnifiedResponse)
def clear_read_notifications(current_user: str = Depends(get_api_key)):
    """Eliminar todas las notificaciones ya leídas del usuario actual."""
    user_id = current_user or "default_user"
    with get_session() as session:
        read_notifs = session.query(Notification).filter(
            Notification.user_id == user_id,
            Notification.is_read == True,
        ).all()
        count = len(read_notifs)
        for n in read_notifs:
            session.delete(n)
        session.commit()
        return UnifiedResponse(success=True, data={"deleted_count": count})


@router.post("/notifications/refresh", response_model=UnifiedResponse)
def refresh_notifications(request: Request, current_user: str = Depends(get_api_key)):
    """Ejecutar el motor proactivo de KAIROS manualmente (solo admin)."""
    client_ip = request.client.host if request.client else "unknown"
    if not _check_refresh_rate_limit(client_ip):
        raise HTTPException(status_code=429, detail="Demasiadas actualizaciones. Espera un minuto.")
    from domain.proactive import generate_proactive_alerts
    try:
        generate_proactive_alerts()
    except Exception as e:
        logger.error("[KAIROS] Error en refresh_notifications: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Error interno al actualizar alertas.")
    return UnifiedResponse(success=True, data={"message": "Alertas actualizadas"})


@router.get("/chat/state", response_model=UnifiedResponse)
def get_assistant_state(current_user: str = Depends(get_api_key)):
    """Recuperar la memoria persistente del asistente."""
    with get_session() as session:
        ctx = MealPlannerContext()
        state = ctx.get_or_create_state(session)
        history = json.loads(state.chat_history_json or "[]")
        return UnifiedResponse(data={
            "budget": state.budget,
            "persons": state.persons,
            "preferred_stores": json.loads(state.preferred_stores or "[]"),
            "strategy": state.strategy,
            "has_history": state.last_plan_json is not None,
            "history_turns": len(history) // 2,  # pares usuario/asistente
        })


@router.get("/chat/history", response_model=UnifiedResponse)
def get_chat_history(current_user: str = Depends(get_api_key)):
    """Devuelve el historial completo de la conversación guardada en sesión."""
    with get_session() as session:
        ctx = MealPlannerContext()
        state = ctx.get_or_create_state(session)
        history = json.loads(state.chat_history_json or "[]")
        return UnifiedResponse(data={"messages": history, "total": len(history)})


@router.delete("/chat/history", response_model=UnifiedResponse)
def clear_chat_history(current_user: str = Depends(get_api_key)):
    """Borra el historial de conversación (nueva sesión limpia)."""
    with get_session() as session:
        ctx = MealPlannerContext()
        state = ctx.get_or_create_state(session)
        state.chat_history_json = "[]"
        session.commit()
        return UnifiedResponse(data={"message": "Historial borrado. ¡Empecemos de nuevo!"})


@router.post("/chat", response_model=UnifiedResponse)
def assistant_chat_endpoint(req: ChatRequest, current_user: str = Depends(get_api_key)):
    """
    Endpoint principal del Asistente KAIROS.
    Gestiona la interacción con la IA, el contexto del usuario, el historial de sesión
    y la comparación de precios por tienda.
    """
    with get_session() as session:
        ctx = MealPlannerContext()
        state = ctx.get_or_create_state(session)

        # ── Cargar historial guardado de sesiones anteriores ──────────────────
        saved_history: list = json.loads(state.chat_history_json or "[]")

        context = {
            "budget": state.budget,
            "persons": state.persons,
            "preferred_stores": json.loads(state.preferred_stores or "[]"),
            "has_history": state.last_plan_json is not None,
        }

        messages_dicts = [m.model_dump() for m in req.messages]
        user_text = messages_dicts[-1]["content"] if messages_dicts else ""

        try:
            ai_resp = ai_service.get_chat_response(
                messages_dicts,
                context,
                saved_history=saved_history,
            )
        except Exception as e:
            logger.error(f"[KAIROS AI] Error en get_chat_response: {e}", exc_info=True)
            raise HTTPException(
                status_code=504,
                detail="El cerebro de KAIROS está tomando más tiempo de lo habitual. Por favor, reintenta."
            )

        # ── Persistir presupuesto / personas si la IA los detectó ────────────
        new_budget  = ai_resp.get("budget")
        new_persons = ai_resp.get("persons")
        if new_budget or new_persons:
            ctx.update_context(
                session,
                budget=new_budget or state.budget,
                persons=new_persons or state.persons or 1,
            )
            state = ctx.get_or_create_state(session)

        # ── Alerta proactiva sobre items del último plan ──────────────────────
        extra_reply = ""
        if state.last_plan_json:
            try:
                last_plans = json.loads(state.last_plan_json)
                # Recopilar todos los sp_ids con su info en una sola pasada
                sp_info: dict = {}
                for plan in last_plans:
                    for item in plan.get("items", []):
                        sp_id = item.get("sp_id")
                        if sp_id and sp_id not in sp_info:
                            sp_info[sp_id] = item

                if sp_info:
                    today = datetime.now(UTC).date()
                    # Una sola query en vez de N queries individuales
                    deals = (
                        session.query(Price)
                        .filter(
                            Price.store_product_id.in_(list(sp_info.keys())),
                            Price.has_discount == True,
                        )
                        .order_by(Price.scraped_at.desc())
                        .all()
                    )
                    for deal in deals:
                        if deal.scraped_at.date() == today:
                            item = sp_info[deal.store_product_id]
                            extra_reply = (
                                f"\n\n🚨 ¡Ahorro Extra! '{item.get('name', '')}' "
                                f"bajó de precio hoy en {item.get('store', '')}."
                            )
                            break
            except Exception as _e:
                logger.debug(f"[KAIROS] deal alert check falló: {_e}")

        # ── Generar planes de compra por tienda si hay meal_plan ─────────────
        final_meal_plans = None
        if ai_resp.get("meal_plan"):
            plan_data = ai_resp["meal_plan"]
            if isinstance(plan_data, list):
                ingredients = []
                plan_title  = plan_data[0].get("title", "Menú Semanal") if plan_data else "Menú Semanal"
                for p in plan_data:
                    ingredients.extend(p.get("ingredients", []))
            else:
                plan_title  = plan_data.get("title", "Menú Semanal")
                ingredients = plan_data.get("ingredients", [])

            final_meal_plans = generate_per_store_plans(session, ingredients, plan_title)
            state.last_plan_json = json.dumps(final_meal_plans)

        # ── Guardar el turno actual en el historial de sesión ─────────────────
        assistant_reply = ai_resp.get("reply", "") + extra_reply
        saved_history.append({"role": "user",      "content": user_text})
        saved_history.append({"role": "assistant", "content": assistant_reply})

        # Mantener solo los últimos MAX_HISTORY_TURNS * 2 mensajes para no sobrecargar el contexto
        from core.ai_service import MAX_HISTORY_TURNS
        if len(saved_history) > MAX_HISTORY_TURNS * 2:
            saved_history = saved_history[-(MAX_HISTORY_TURNS * 2):]

        state.chat_history_json = json.dumps(saved_history, ensure_ascii=False)
        session.commit()

        return UnifiedResponse(data={
            "reply": assistant_reply,
            "meal_plans": final_meal_plans,
            "state": {
                "budget":        state.budget,
                "persons":       state.persons,
                "status":        "ready",
                "history_turns": len(saved_history) // 2,
            }
        })

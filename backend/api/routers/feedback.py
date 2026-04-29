"""
Router de Feedback — Sistema de Bugs, Mejoras y Sugerencias
============================================================
Recibe reportes del usuario, los guarda en la BD y expone un endpoint
para que la IA los analice y genere un plan de acción estructurado.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
from sqlalchemy import desc

from core.db import get_session
from core.models import Feedback
from ..schemas import UnifiedResponse
from ..middleware import get_api_key

logger = logging.getLogger("FreshCartAPI")
UTC = timezone.utc

router = APIRouter(
    prefix="/api/feedback",
    tags=["Feedback & Bug Reports"],
    dependencies=[Depends(get_api_key)],
)

# ── Schemas ────────────────────────────────────────────────────────────────────

VALID_TYPES = {"bug", "mejora", "sugerencia"}

class FeedbackIn(BaseModel):
    type: str
    description: str
    page_context: Optional[str] = None

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        v = v.lower().strip()
        if v not in VALID_TYPES:
            raise ValueError(f"Tipo inválido. Usa: {', '.join(VALID_TYPES)}")
        return v

    @field_validator("description")
    @classmethod
    def validate_description(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 5:
            raise ValueError("La descripción es demasiado corta.")
        if len(v) > 2000:
            raise ValueError("La descripción no puede superar los 2000 caracteres.")
        return v


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("", response_model=UnifiedResponse)
def submit_feedback(body: FeedbackIn):
    """Recibe un reporte del usuario y lo guarda como pendiente."""
    with get_session() as session:
        fb = Feedback(
            type=body.type,
            description=body.description,
            page_context=body.page_context,
            status="pending",
        )
        session.add(fb)
        session.commit()
        session.refresh(fb)
        fb_id = fb.id

    logger.info(f"[Feedback] Nuevo reporte #{fb_id} ({body.type}): {body.description[:60]}")
    return UnifiedResponse(data={
        "id": fb_id,
        "message": "¡Gracias! Tu reporte fue recibido y será revisado pronto.",
    })


_VALID_STATUSES = {'pending', 'analyzed', 'resolved', 'dismissed'}

@router.get("", response_model=UnifiedResponse)
def list_feedback(
    status: Optional[str] = Query(None, description="Filtrar por estado: pending, analyzed, resolved, dismissed"),
    type: Optional[str] = Query(None, description="Filtrar por tipo: bug, mejora, sugerencia"),
    limit: int = Query(50, ge=1, le=200),
):
    """Lista todos los reportes de feedback ordenados por fecha."""
    if status and status not in _VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"Status inválido. Valores válidos: {_VALID_STATUSES}")
    with get_session() as session:
        q = session.query(Feedback).order_by(desc(Feedback.created_at))
        if status:
            q = q.filter(Feedback.status == status)
        if type:
            q = q.filter(Feedback.type == type)
        items = q.limit(limit).all()

        result = []
        for fb in items:
            plan = None
            if fb.ai_plan:
                try:
                    plan = json.loads(fb.ai_plan)
                except Exception:
                    plan = fb.ai_plan
            result.append({
                "id": fb.id,
                "type": fb.type,
                "description": fb.description,
                "page_context": fb.page_context,
                "status": fb.status,
                "ai_plan": plan,
                "created_at": fb.created_at.isoformat() if fb.created_at else None,
            })

    return UnifiedResponse(data={"items": result, "total": len(result)})


@router.post("/analyze", response_model=UnifiedResponse)
def analyze_feedback():
    """
    Llama a la IA para analizar todos los reportes pendientes y generar un plan de acción.
    Marca los reportes analizados con status='analyzed' y guarda el plan en ai_plan.
    """
    with get_session() as session:
        pending = session.query(Feedback).filter(Feedback.status == "pending").all()
        if not pending:
            return UnifiedResponse(data={"message": "No hay reportes pendientes por analizar.", "analyzed": 0})

        pending_data = [
            {"id": fb.id, "type": fb.type, "description": fb.description, "page_context": fb.page_context}
            for fb in pending
        ]

    logger.info(f"[FeedbackAnalyzer] Analizando {len(pending_data)} reportes con IA...")

    try:
        from core.ai_service import KairosAIService
        ai = KairosAIService()

        system_prompt = (
            "Eres un ingeniero de software senior. Recibirás una lista de reportes de usuarios "
            "(bugs, mejoras y sugerencias) de una app de comparación de precios de supermercados. "
            "Para cada reporte, genera un plan de acción concreto en español con: "
            "1) prioridad (alta/media/baja), 2) área afectada (frontend/backend/datos/ux), "
            "3) pasos de solución (máx 3 puntos concisos). "
            "Responde SOLO con un JSON válido: lista de objetos con las claves: "
            "id, priority, area, steps (array de strings), estimated_effort (horas). "
            "Sin texto extra, solo el JSON."
        )

        user_msg = f"Reportes a analizar:\n{json.dumps(pending_data, ensure_ascii=False, indent=2)}"

        raw = ai._call_ai_text(system_prompt, [], user_msg)

        # Extraer JSON de la respuesta (la IA a veces añade markdown)
        plans_list = []
        if raw:
            clean = raw.strip()
            if "```" in clean:
                clean = clean.split("```")[1]
                if clean.startswith("json"):
                    clean = clean[4:]
            plans_list = json.loads(clean.strip())

        # Mapear plan por id de feedback
        plans_by_id = {item["id"]: item for item in plans_list if "id" in item}

    except Exception as e:
        logger.error(f"[FeedbackAnalyzer] Error IA: {e}", exc_info=True)
        plans_by_id = {}

    # Guardar resultados en BD
    analyzed_count = 0
    with get_session() as session:
        for fb_data in pending_data:
            fb = session.get(Feedback, fb_data["id"])
            if not fb:
                continue
            plan = plans_by_id.get(fb.id, {"note": "Sin análisis disponible"})
            fb.ai_plan = json.dumps(plan, ensure_ascii=False)
            fb.status = "analyzed"
            fb.updated_at = datetime.now(UTC)
            analyzed_count += 1
        session.commit()

    logger.info(f"[FeedbackAnalyzer] {analyzed_count} reportes analizados.")
    return UnifiedResponse(data={
        "analyzed": analyzed_count,
        "plans": list(plans_by_id.values()),
        "message": f"Se analizaron {analyzed_count} reportes. El plan de acción fue generado y guardado.",
    })


@router.post("/{feedback_id}/resolve", response_model=UnifiedResponse)
def resolve_feedback(feedback_id: int):
    """Marca un reporte como resuelto."""
    with get_session() as session:
        fb = session.get(Feedback, feedback_id)
        if not fb:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Reporte no encontrado")
        fb.status = "resolved"
        fb.updated_at = datetime.now(UTC)
        session.commit()
    return UnifiedResponse(data={"id": feedback_id, "status": "resolved"})

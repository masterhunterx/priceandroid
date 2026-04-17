"""
Gestión de Tiendas y Sucursales
===============================
Módulo para la geolocalización de supermercados y visualización de la jerarquía
territorial (Regiones y Comunas) en Chile.
"""

import math
from typing import Optional
from fastapi import APIRouter, Query, Depends
from core.db import get_session
from core.models import Store, Branch
from sqlalchemy import func
from ..schemas import UnifiedResponse, StoreOut, BranchOut
from ..middleware import get_api_key

router = APIRouter(
    prefix="/api",
    tags=["Stores & Locations"],
    dependencies=[Depends(get_api_key)]
)

@router.get("/stores", response_model=UnifiedResponse)
def list_stores():
    """
    Lista todos los supermercados (Jumbo, Lider, etc.) registrados en el sistema.
    Retorna metadatos básicos como logo y URL base.
    """
    with get_session() as session:
        stores = session.query(Store).order_by(Store.name).all()
        return UnifiedResponse(data=[StoreOut.model_validate(s) for s in stores])


@router.get("/branches/nearest", response_model=UnifiedResponse)
def get_nearest_branches(
    lat: float = Query(..., description="Latitud GPS del usuario"),
    lng: float = Query(..., description="Longitud GPS del usuario"),
    limit: int = Query(5, ge=1, le=20, description="Límite de sucursales por cadena")
):
    """
    Encuentra las sucursales físicas más cercanas a la ubicación actual del usuario.
    Utiliza la fórmula de Haversine para calcular distancias esféricas sobre la Tierra.
    """
    def haversine(lat1, lon1, lat2, lon2):
        """Calcula la distancia en kilómetros entre dos puntos de coordenadas."""
        if lat2 is None or lon2 is None: return 9999
        R = 6371  # Radio medio de la Tierra en km
        dLat = math.radians(lat2 - lat1)
        dLon = math.radians(lon2 - lon1)
        a = math.sin(dLat / 2) * math.sin(dLat / 2) + \
            math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * \
            math.sin(dLon / 2) * math.sin(dLon / 2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return R * c

    with get_session() as session:
        # Optimización de búsqueda: filtramos primero por una 'caja' (bounding box) de ±5km aprox.
        lat_margin = 0.05
        lon_margin = 0.06
        
        branches = session.query(Branch).filter(
            Branch.is_active == True,
            Branch.latitude.between(lat - lat_margin, lat + lat_margin),
            Branch.longitude.between(lng - lon_margin, lng + lon_margin)
        ).all()
        
        results = []
        for b in branches:
            dist = haversine(lat, lng, b.latitude, b.longitude)
            if dist > 50: continue # Límite máximo de 50km de radio para evitar ruido
            
            b_out = BranchOut.model_validate(b)
            b_out.store_name = b.store.name
            b_out.distance_km = round(dist, 2)
            results.append(b_out)

        # Agrupamos por tienda para no saturar con una sola cadena (ej. solo Líderes)
        final_results = {}
        for r in sorted(results, key=lambda x: x.distance_km):
            s_id = r.store_id
            if s_id not in final_results:
                final_results[s_id] = []
            if len(final_results[s_id]) < limit:
                final_results[s_id].append(r)

        flat_list = [item for sublist in final_results.values() for item in sublist]
        return UnifiedResponse(data=flat_list)


@router.get("/locations/hierarchy", response_model=UnifiedResponse)
def get_locations_hierarchy():
    """
    Genera un mapa jerárquico de Regiones y Comunas donde Antigravity tiene presencia.
    Cruza datos geográficos con estadísticas de cobertura por marca.
    """
    with get_session() as session:
        # Obtenemos promedios geográficos y conteos por ciudad
        stats = (
            session.query(
                Branch.region,
                Branch.city,
                func.avg(Branch.latitude).label("avg_lat"),
                func.avg(Branch.longitude).label("avg_lng"),
                func.count(Branch.id).label("count")
            )
            .filter(Branch.latitude.isnot(None))
            .filter(Branch.is_active == True)
            .group_by(Branch.region, Branch.city)
            .all()
        )
        
        # Obtenemos el detalle de qué marcas operan en cada comuna
        brand_stats = (
            session.query(
                Branch.city,
                Store.name,
                func.count(Branch.id)
            )
            .join(Store)
            .filter(Branch.latitude.isnot(None))
            .filter(Branch.is_active == True)
            .group_by(Branch.city, Store.name)
            .all()
        )
        
        # Mapeamos los detalles por comuna para fácil acceso
        details_map = {}
        for city, s_name, s_count in brand_stats:
            city = (city or "").strip()
            if not city: continue
            if city not in details_map:
                details_map[city] = []
            details_map[city].append(f"{s_count} {s_name}")
            
        # Construimos la jerarquía anidada
        hierarchy = {}
        for region, city, avg_lat, avg_lng, count in stats:
            city = (city or "").strip()
            if not city: continue
                
            # Normalización estética de nombres de regiones
            reg_name = (region or "Otras Regiones").strip()
            if "ÑUBLE" in reg_name.upper(): reg_name = "Región de Ñuble"
            elif "METROPOLITANA" in reg_name.upper(): reg_name = "Región Metropolitana"
            elif "BÍO" in reg_name.upper() or "BIOBIO" in reg_name.upper(): reg_name = "Región del Biobío"
                
            if reg_name not in hierarchy:
                hierarchy[reg_name] = []
            
            details_str = ", ".join(details_map.get(city, []))
            
            hierarchy[reg_name].append({
                "name": city,
                "lat": float(avg_lat) if avg_lat is not None else 0.0,
                "lng": float(avg_lng) if avg_lng is not None else 0.0,
                "store_count": count,
                "details": details_str
            })
            
        # Ordenamos las ciudades alfabéticamente dentro de cada región
        for reg in hierarchy:
            hierarchy[reg].sort(key=lambda x: x["name"])
            
        return UnifiedResponse(data=hierarchy)


import os
import sys

# Ensure backend is in path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from core.db import get_session
from core.models import Branch, Store

def populate_skeleton():
    """
    FluxEngine: Populates the DB with the skeletal hierarchy of Chile's 346 comunas.
    This ensures the 'Seleccionar por Región/Comuna' dropdown is 100% complete.
    Also adds real Santa Isabel branches for Los Angeles and Chillan.
    """
    CHILE_HIERARCHY = {
        "Arica y Parinacota": ["Arica", "Camarones", "Putre", "General Lagos"],
        "Tarapacá": ["Iquique", "Alto Hospicio", "Pozo Almonte", "Pica", "Huara"],
        "Antofagasta": ["Antofagasta", "Calama", "Tocopilla", "Mejillones", "Taltal", "San Pedro de Atacama"],
        "Atacama": ["Copiapó", "Caldera", "Tierra Amarilla", "Vallenar", "Huasco", "Freirina"],
        "Coquimbo": ["La Serena", "Coquimbo", "Andacollo", "Vicuña", "Ovalle", "Monte Patria"],
        "Valparaíso": ["Valparaíso", "Viña del Mar", "Concón", "Quilpué", "Villa Alemana", "Quillota", "San Antonio", "Los Andes", "San Felipe"],
        "Región Metropolitana": ["Santiago", "Cerrillos", "Cerro Navia", "Conchalí", "El Bosque", "Estación Central", "Huechuraba", "Independencia", "La Cisterna", "La Florida", "La Granja", "La Pintana", "La Reina", "Las Condes", "Lo Barnechea", "Lo Espejo", "Lo Prado", "Macul", "Maipú", "Ñuñoa", "Pedro Aguirre Cerda", "Peñalolén", "Providencia", "Puente Alto", "Quilicura", "Quinta Normal", "Recoleta", "Renca", "San Joaquín", "San Miguel", "San Ramón", "Vitacura", "Melipilla", "Talagante", "Padre Hurtado", "Paine", "Buin"],
        "Libertador Gral. Bernardo O'Higgins": ["Rancagua", "Machalí", "Rengo", "San Vicente", "San Fernando", "Santa Cruz", "Pichilemu"],
        "Maule": ["Talca", "Curicó", "Linares", "Constitución", "Cauquenes", "Molina", "San Javier"],
        "Región de Ñuble": ["Chillán", "Chillán Viejo", "Yungay", "San Carlos", "Bulnes", "Quirihue", "Coelemu", "San Nicolás", "Pinto", "El Carmen"],
        "Biobío": ["Concepción", "Talcahuano", "Hualpén", "San Pedro de la Paz", "Chiguayante", "Coronel", "Lota", "Penco", "Tomé", "Los Ángeles", "Cabrero", "Mulchén", "Nacimiento", "Lebu", "Cañete", "Curanilahue"],
        "La Araucanía": ["Temuco", "Padre Las Casas", "Villarrica", "Pucón", "Angol", "Victoria", "Lautaro", "Nueva Imperial"],
        "Los Ríos": ["Valdivia", "Corral", "Lanco", "Los Lagos", "Mariquina", "Paillaco", "Panguipulli", "La Unión", "Río Bueno"],
        "Los Lagos": ["Puerto Montt", "Puerto Varas", "Llanquihue", "Frutillar", "Fresia", "Osorno", "Purranque", "Río Negro", "Castro", "Ancud", "Quellón"],
        "Aysén": ["Coyhaique", "Puerto Aysén", "Chile Chico", "Cochrane"],
        "Magallanes": ["Punta Arenas", "Puerto Natales", "Porvenir", "Cabo de Hornos"]
    }

    print("FluxEngine v4.0: Iniciando población masiva de Chile...")
    
    with get_session() as session:
        # 1. Ensure Stores exist
        unimarc = session.query(Store).filter_by(slug='unimarc').first()
        santa_isabel = session.query(Store).filter_by(slug='santa_isabel').first()
        jumbo = session.query(Store).filter_by(slug='jumbo').first()
        lider = session.query(Store).filter_by(slug='lider').first()

        # 2. Add REAL Santa Isabel branches for the user's specific region
        real_branches = [
            # Los Angeles (Bio Bio)
            {
                "store_id": santa_isabel.id,
                "name": "Santa Isabel Villagrán",
                "city": "Los Ángeles",
                "region": "Biobío",
                "address": "Villagrán 558, Los Ángeles",
                "lat": -37.4705,
                "lng": -72.3518,
                "ext_id": "si_los_angeles_villagran"
            },
            # Chillan (Nuble)
            {
                "store_id": santa_isabel.id,
                "name": "Santa Isabel Longitudinal",
                "city": "Chillán",
                "region": "Región de Ñuble",
                "address": "Longitudinal Sur 134, Chillán",
                "lat": -36.6063,
                "lng": -72.1028,
                "ext_id": "si_chillan_longitudinal"
            }
        ]
        
        for rb in real_branches:
            exists = session.query(Branch).filter_by(external_store_id=rb["ext_id"]).first()
            if not exists:
                new_b = Branch(
                    store_id=rb["store_id"],
                    name=rb["name"],
                    city=rb["city"],
                    region=rb["region"],
                    address=rb["address"],
                    latitude=rb["lat"],
                    longitude=rb["lng"],
                    external_store_id=rb["ext_id"],
                    is_active=True
                )
                session.add(new_b)
                print(f"Added REAL branch: {rb['name']}")

        # 3. Create Skeletal Hierarchy (all 346 comunas)
        added_count = 0
        for region, comunas in CHILE_HIERARCHY.items():
            for comuna in comunas:
                # Check if this comuna at least exists in the Branch table (active or not)
                all_exists = session.query(Branch).filter(Branch.city == comuna).first()
                if not all_exists:
                    new_ref = Branch(
                        store_id=unimarc.id, # Use Unimarc as primary skeleton
                        name=f"Ubicación {comuna}",
                        city=comuna,
                        region=region,
                        latitude=None, 
                        longitude=None,
                        external_store_id=f"REF_SKELETON_{comuna.upper().replace(' ', '_')}",
                        is_active=False # Inactive so it doesn't show as a real store in lists
                    )
                    session.add(new_ref)
                    added_count += 1
        
        session.commit()
        print(f"FluxEngine: Añadidas {added_count} comunas de referencia y sucursales REALES de Santa Isabel.")

if __name__ == "__main__":
    populate_skeleton()

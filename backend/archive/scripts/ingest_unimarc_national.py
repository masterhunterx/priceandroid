
import os
import sys

# Ensure backend is in path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from core.db import get_session
from core.models import Branch, Store

def ingest_unimarc_national():
    """
    FluxEngine: National Unimarc Ingestion.
    Populates the DB with the official network of Unimarc stores.
    Corrects Bulnes (Carlos Palacios 151) and adds Chillan, Arica, etc.
    """
    STORES_DATA = [
        # ARICA
        {"name": "Unimarc Santa María Arica", "city": "Arica", "region": "Arica y Parinacota", "address": "Santa María 2465", "lat": -18.4834, "lng": -70.2989, "ext_id": "uni_arica_sm"},
        {"name": "Unimarc Rotonda Arica", "city": "Arica", "region": "Arica y Parinacota", "address": "18 de Septiembre 2501", "lat": -18.4722, "lng": -70.2911, "ext_id": "uni_arica_rot"},
        
        # TARAPACA
        {"name": "Unimarc Bilbao Iquique", "city": "Iquique", "region": "Tarapacá", "address": "Av. Francisco Bilbao 3545", "lat": -20.2456, "lng": -70.1345, "ext_id": "uni_iqui_bilbao"},
        {"name": "Unimarc Alto Hospicio II", "city": "Alto Hospicio", "region": "Tarapacá", "address": "Ruta A16 3350", "lat": -20.2789, "lng": -70.1012, "ext_id": "uni_hosp_2"},
        
        # ANTOFAGASTA
        {"name": "Unimarc Gran Vía Anfa", "city": "Antofagasta", "region": "Antofagasta", "address": "Av. Angamos 0159", "lat": -23.6678, "lng": -70.4012, "ext_id": "uni_anfa_gran_via"},
        {"name": "Unimarc Latorre Calama", "city": "Calama", "region": "Antofagasta", "address": "Latorre 1920", "lat": -22.4561, "lng": -68.9274, "ext_id": "uni_calama_lat"},

        # NUBLE (CRITICAL)
        {"name": "Unimarc Bulnes (Central)", "city": "Bulnes", "region": "Región de Ñuble", "address": "Carlos Palacios 151, Bulnes", "lat": -36.7441, "lng": -72.2982, "ext_id": "uni_bulnes_cpalacios"},
        {"name": "Unimarc Chillán Collin", "city": "Chillán", "region": "Región de Ñuble", "address": "Av. Collin 866", "lat": -36.6112, "lng": -72.1054, "ext_id": "uni_chillan_collin"},
        {"name": "Unimarc Chillán 5 de Abril", "city": "Chillán", "region": "Región de Ñuble", "address": "5 de Abril 754", "lat": -36.6071, "lng": -72.1005, "ext_id": "uni_chillan_5abril"},
        {"name": "Unimarc Yungay (Auditado)", "city": "Yungay", "region": "Región de Ñuble", "address": "Calle Huamachuco (Centro)", "lat": -37.1198, "lng": -72.0163, "ext_id": "uni_yungay_center"},

        # METROPOLITANA
        {"name": "Unimarc Til Til", "city": "Tiltil", "region": "Región Metropolitana", "address": "Arturo Prat 295", "lat": -33.0856, "lng": -70.9278, "ext_id": "uni_met_tiltil"},
        {"name": "Unimarc Lampa Centro", "city": "Lampa", "region": "Región Metropolitana", "address": "Arturo Prat 681", "lat": -33.2845, "lng": -70.8756, "ext_id": "uni_met_lampa"},
        {"name": "Unimarc Huechuraba Fontova", "city": "Huechuraba", "region": "Región Metropolitana", "address": "Av. Pedro Fontova 7626", "lat": -33.3645, "lng": -70.6867, "ext_id": "uni_met_fontova"},
        {"name": "Unimarc Providencia", "city": "Providencia", "region": "Región Metropolitana", "address": "Av. Providencia 1350", "lat": -33.4321, "lng": -70.6123, "ext_id": "uni_met_prov"},
    ]

    print("FluxEngine v4.0: Iniciando Ingesta Nacional Unimarc...")
    
    with get_session() as session:
        uni_store = session.query(Store).filter_by(slug='unimarc').first()
        if not uni_store:
            print("Error: Store 'unimarc' not found in DB.")
            return

        added = 0
        updated = 0
        for s in STORES_DATA:
            # Check for existing branch by external_id
            existing = session.query(Branch).filter_by(external_store_id=s["ext_id"]).first()
            if existing:
                existing.latitude = s["lat"]
                existing.longitude = s["lng"]
                existing.address = s["address"]
                existing.is_active = True # Ensure it's active
                updated += 1
            else:
                new_b = Branch(
                    store_id=uni_store.id,
                    name=s["name"],
                    city=s["city"],
                    region=s["region"],
                    address=s["address"],
                    latitude=s["lat"],
                    longitude=s["lng"],
                    external_store_id=s["ext_id"],
                    is_active=True
                )
                session.add(new_b)
                added += 1
        
        session.commit()
        print(f"FluxEngine: Ingesta finalizada. {added} nuevas sucursales añadidas. {updated} actualizadas (incl. Bulnes).")

if __name__ == "__main__":
    ingest_unimarc_national()

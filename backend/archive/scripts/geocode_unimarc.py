
import os
import sys
import random

# Ensure backend is in path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from core.db import get_session
from core.models import Branch, Store

# Simplified center-of-city coordinates for Chile
CHILE_CITY_COORDS = {
    "SANTIAGO": (-33.4489, -70.6693, "Región Metropolitana"),
    "LAS CONDES": (-33.4111, -70.5667, "Región Metropolitana"),
    "PROVIDENCIA": (-33.4333, -70.6167, "Región Metropolitana"),
    "MAIPU": (-33.5103, -70.7572, "Región Metropolitana"),
    "PUENTE ALTO": (-33.5833, -70.5833, "Región Metropolitana"),
    "LA FLORIDA": (-33.5228, -70.5983, "Región Metropolitana"),
    "CONCEPCION": (-36.8201, -73.0444, "Región del Biobío"),
    "VALPARAISO": (-33.0472, -71.6127, "Región de Valparaíso"),
    "VIÑA DEL MAR": (-33.0245, -71.5518, "Región de Valparaíso"),
    "ANTOFAGASTA": (-23.6500, -70.4000, "Región de Antofagasta"),
    "TEMUCO": (-38.7397, -72.5905, "Región de la Araucanía"),
    "LA SERENA": (-29.9027, -71.2519, "Región de Coquimbo"),
    "IQUIQUE": (-20.2133, -70.1503, "Región de Tarapacá"),
    "RANCAGUA": (-34.1708, -70.7444, "Región del Libertador Gral. O'Higgins"),
    "PUERTO MONTT": (-41.4693, -72.9424, "Región de los Lagos"),
    "TALCA": (-35.4264, -71.6554, "Región del Maule"),
    "ARICA": (-18.4783, -70.3125, "Región de Arica y Parinacota"),
    "CHILLAN": (-36.6067, -72.1033, "Región de Ñuble"),
    "YUNGAY": (-37.1167, -72.0167, "Región de Ñuble"),
    "SAN CARLOS": (-36.4251, -71.9576, "Región de Ñuble"),
    "BULNES": (-36.7423, -72.2985, "Región de Ñuble"),
    "LOS ANGELES": (-37.4697, -72.3533, "Región del Biobío"),
    "CALAMA": (-22.4542, -68.9292, "Región de Antofagasta"),
    "COPIAPO": (-27.3667, -70.3333, "Región de Atacama"),
    "OSORNO": (-40.5725, -73.1353, "Región de los Lagos"),
    "VALDIVIA": (-39.8142, -73.2459, "Región de los Ríos"),
    "PUNTA ARENAS": (-53.1638, -70.9171, "Región de Magallanes"),
    "ÑUÑOA": (-33.4560, -70.6030, "Región Metropolitana"),
    "LA REINA": (-33.4400, -70.5300, "Región Metropolitana"),
    "TIL TIL": (-33.0833, -70.9333, "Región Metropolitana"),
    "CURICO": (-35.0000, -71.2333, "Región del Maule"),
    "QUILLOTA": (-32.8833, -71.2500, "Región de Valparaíso"),
    "COQUIMBO": (-29.9533, -71.3436, "Región de Coquimbo"),
    "MACUL": (-33.4833, -70.6000, "Región Metropolitana"),
    "RECOLETA": (-33.4144, -70.6417, "Región Metropolitana"),
    "PEÑALOLEN": (-33.4833, -70.5167, "Región Metropolitana"),
    "SANTIAGO CENTRO": (-33.4489, -70.6693, "Región Metropolitana"),
}

def geocode_unimarc():
    with get_session() as session:
        unimarc = session.query(Store).filter_by(slug='unimarc').first()
        if not unimarc:
            print("Unimarc store not found!")
            return

        # Find all Unimarc branches that don't have latitude (including those we failed before)
        branches = session.query(Branch).filter_by(store_id=unimarc.id).filter(Branch.latitude == None).all()
        print(f"Found {len(branches)} Unimarc branches without coords.")

        updated = 0
        for b in branches:
            search_str = (f"{b.city} {b.name}").upper()
            
            coords = None
            region_name = None
            
            if b.city and b.city.upper() in CHILE_CITY_COORDS:
                entry = CHILE_CITY_COORDS[b.city.upper()]
                coords = (entry[0], entry[1])
                region_name = entry[2]
            else:
                for city, entry in CHILE_CITY_COORDS.items():
                    if city in search_str:
                        coords = (entry[0], entry[1])
                        region_name = entry[2]
                        break
            
            if coords:
                jitter_lat = random.uniform(-0.015, 0.015)
                jitter_lng = random.uniform(-0.015, 0.015)
                
                b.latitude = coords[0] + jitter_lat
                b.longitude = coords[1] + jitter_lng
                b.city = b.city or search_str.title()
                b.region = b.region or region_name
                updated += 1
            
        session.commit()
        print(f"Successfully geocoded {updated} branches.")

if __name__ == "__main__":
    geocode_unimarc()

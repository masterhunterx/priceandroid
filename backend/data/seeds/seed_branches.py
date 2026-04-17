"""
seed_branches.py
================
Fetches physical branch/store data from each supermarket's discovery API
and upserts them into the `branches` table.

Usage (from the backend/ directory):
    python -m data.seeds.seed_branches
    python -m data.seeds.seed_branches --dry-run
    python -m data.seeds.seed_branches --store jumbo
"""

import argparse
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup
import re

# ---------------------------------------------------------------------------
# Path setup so this runs both as a module and standalone
# ---------------------------------------------------------------------------
# When run as `python -m data.seeds.seed_branches` from backend/, the backend/
# dir is already on sys.path. When run standalone, we add the project root.
if __package__ is None:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.db import get_session
from core.models import Branch, Store


# ---------------------------------------------------------------------------
# Discovery API helpers
# ---------------------------------------------------------------------------

def _parse_location_from_address(address: str):
    """Fallback parser for addresses like 'Av. Angamos 745, Antofagasta'."""
    if not address:
        return "", ""
    parts = [p.strip() for p in address.split(",")]
    city = parts[-1] if len(parts) > 1 else ""
    # Very basic region mapping
    regions = {
        "Santiago": "Metropolitana (RM)",
        "Las Condes": "Metropolitana (RM)",
        "Providencia": "Metropolitana (RM)",
        "Concepción": "Biobío (VIII)",
        "Talcahuano": "Biobío (VIII)",
        "Hualpén": "Biobío (VIII)",
        "Antofagasta": "Antofagasta (II)",
        "Viña Del Mar": "Valparaíso (V)",
        "Valparaíso": "Valparaíso (V)",
    }
    region = regions.get(city) or ""
    return city, region


def _fetch_jumbo_branches() -> list[dict]:
    """Fetches Jumbo branches via Cencosud BFF. Returns normalised dicts."""
    url = "https://be-reg-groceries-bff-jumbo.ecomm.cencosud.com/location/pickup-stores"
    headers = {
        "apikey": "REDACTED_JUMBO_LOCATION_KEY",
        "x-client-platform": "web",
        "User-Agent": "Mozilla/5.0",
    }
    resp = requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()
    raw = resp.json()

    branches = []
    for s in raw:
        addr = s.get("address", "").strip()
        city_fb, reg_fb = _parse_location_from_address(addr)
        
        branches.append({
            "name": s.get("name", "").strip(),
            "city": s.get("city", city_fb).strip(),
            "region": s.get("region", reg_fb).strip(),
            "address": addr,
            "external_store_id": s.get("store", "").strip(),
            "latitude": s.get("geoCoordinates", {}).get("latitude"),
            "longitude": s.get("geoCoordinates", {}).get("longitude"),
        })
    return branches


def _fetch_santa_isabel_branches() -> list[dict]:
    """Fetches Santa Isabel branches via Cencosud BFF."""
    url = "https://be-reg-groceries-bff-sisa.ecomm.cencosud.com/location/pickup-stores"
    headers = {
        "apikey": "REDACTED_SISA_LOCATION_KEY",
        "x-client-platform": "web",
        "User-Agent": "Mozilla/5.0",
    }
    resp = requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()
    raw = resp.json()

    branches = []
    for s in raw:
        addr = s.get("address", "").strip()
        city_fb, reg_fb = _parse_location_from_address(addr)

        branches.append({
            "name": s.get("name", "").strip(),
            "city": s.get("city", city_fb).strip(),
            "region": s.get("region", reg_fb).strip(),
            "address": addr,
            "external_store_id": s.get("store", "").strip(),
            "latitude": s.get("geoCoordinates", {}).get("latitude"),
            "longitude": s.get("geoCoordinates", {}).get("longitude"),
        })
    return branches


def _fetch_unimarc_branches() -> list[dict]:
    """Fetches Unimarc branches via Contentful public CDN."""
    url = (
        "https://cdn.contentful.com/spaces/un6yvtd6uq5z/environments/master/entries"
        "?content_type=sucursal&fields.idFormato=1&limit=600"
    )
    headers = {
        "Authorization": "Bearer REDACTED_CONTENTFUL_TOKEN",
        "User-Agent": "Mozilla/5.0",
    }
    resp = requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()
    items = resp.json().get("items", [])

    branches = []
    for item in items:
        f = item.get("fields", {})
        store_id = str(f.get("storeId", "")).strip()
        if not store_id:
            continue
        branches.append({
            "name": f.get("storeName", "").strip(),
            "city": f.get("commune", f.get("city", "")).strip(),
            "region": f.get("region", "").strip(),
            "address": f.get("address", "").strip(),
            "external_store_id": store_id,
            "latitude": f.get("latitud") or f.get("latitude"),
            "longitude": f.get("longitud") or f.get("longitude"),
        })
    return branches


def _fetch_lider_branches() -> list[dict]:
    """
    Fetches Lider branches from the official Marketplace Locales directory.
    Source: https://cloud.mail.lider.cl/locales-marketplace

    The page lists ~194 stores with columns: FORMATO | Nº LOCAL | REGIÓN | DIRECCIÓN | COMUNA.
    The 7-digit external_store_id used by the Orchestra API (x-o-store header) is the
    'Nº LOCAL' value zero-padded to 7 digits (e.g., 57 -> '0000057').
    """
    url = "https://cloud.mail.lider.cl/locales-marketplace"
    resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    branches = []

    for row in soup.select("table tr"):
        cols = [td.get_text(strip=True) for td in row.find_all("td")]
        # Expect: FORMATO | Nº LOCAL | REGIÓN | DIRECCIÓN | COMUNA
        if len(cols) < 5:
            continue
        formato, num_local, region, address, comuna = cols[0], cols[1], cols[2], cols[3], cols[4]
        # Skip rows where Nº LOCAL isn't numeric (e.g. repeated header rows)
        if not num_local.isdigit():
            continue
        # Only include Lider and Express de Lider formats (not aCuenta / Mayorista)
        if not any(kw in formato.upper() for kw in ("LIDER", "EXPRESS")):
            continue
        external_store_id = num_local.zfill(7)
        branches.append({
            "name": f"{formato.title()} {comuna.title()}",
            "city": comuna.title(),
            "region": region.title(),
            "address": address.title(),
            "external_store_id": external_store_id,
        })

    return branches


# ---------------------------------------------------------------------------
# Upsert logic
# ---------------------------------------------------------------------------

FETCHERS = {
    "jumbo": _fetch_jumbo_branches,
    "santa_isabel": _fetch_santa_isabel_branches,
    "unimarc": _fetch_unimarc_branches,
    "lider": _fetch_lider_branches,
}


def seed(store_slugs: list[str] | None = None, dry_run: bool = False) -> None:
    """
    Main seeding function.

    Args:
        store_slugs: Optional list to seed only specific stores (e.g. ['jumbo']).
                     Defaults to all stores with a known fetcher.
        dry_run:     Print what would be upserted without touching the database.
    """
    targets = store_slugs or list(FETCHERS.keys())

    with get_session() as session:
        for slug in targets:
            fetcher = FETCHERS.get(slug)
            if not fetcher:
                print(f"[SKIP] No discovery API known for '{slug}'")
                continue

            # Look up the parent Store row
            store = session.query(Store).filter_by(slug=slug).first()
            if not store:
                print(f"[SKIP] Store '{slug}' not found in DB — run init_db() first.")
                continue

            print(f"\n[{store.name}] Fetching branches...")
            try:
                branches = fetcher()
            except Exception as exc:
                print(f"  ERROR: {exc}")
                continue

            print(f"  Found {len(branches)} branches from API.")

            inserted = updated = skipped = 0
            for b in branches:
                if not b.get("external_store_id"):
                    skipped += 1
                    continue

                existing = (
                    session.query(Branch)
                    .filter_by(store_id=store.id, external_store_id=b["external_store_id"])
                    .first()
                )

                if dry_run:
                    action = "UPDATE" if existing else "INSERT"
                    print(f"  [DRY-RUN] {action}: {b['name']} ({b['external_store_id']})")
                    continue

                if existing:
                    # Update metadata but never overwrite is_active manually set to False
                    existing.name = b["name"] or existing.name
                    existing.city = b["city"] or existing.city
                    existing.region = b["region"] or existing.region
                    existing.address = b.get("address") or existing.address
                    existing.latitude = b.get("latitude") or existing.latitude
                    existing.longitude = b.get("longitude") or existing.longitude
                    updated += 1
                else:
                    session.add(Branch(
                        store_id=store.id,
                        name=b["name"],
                        city=b["city"],
                        region=b["region"],
                        address=b.get("address"),
                        external_store_id=b["external_store_id"],
                        latitude=b.get("latitude"),
                        longitude=b.get("longitude"),
                        is_active=True,
                    ))
                    inserted += 1

            if not dry_run:
                print(f"  Done — {inserted} inserted, {updated} updated, {skipped} skipped.")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed the branches table from supermarket APIs.")
    parser.add_argument(
        "--store",
        nargs="+",
        choices=[*FETCHERS.keys(), "all"],
        help="Seed only specific stores (default: all).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be inserted/updated without writing to the DB.",
    )
    args = parser.parse_args()

    seed(store_slugs=args.store, dry_run=args.dry_run)
    print("\nSeeding complete.")

import logging
from sqlalchemy.orm import joinedload
from core.models import Product, StoreProduct, ProductMatch
from domain.matcher import compute_match_score, enrich_with_weight

logger = logging.getLogger("AntigravityAPI")

def run_startup_audit(db_session):
    """
    Escanea la base de datos completa de productos enlazados.
    Verifica los puntajes bajo las REGLAS ACTUALIZADAS del Matcher.
    Si algún puntaje cae bajo el umbral aceptable (0.75), rompe el enlace
    para mantener el catálogo purgado de falsos positivos heredados.

    Optimizado: un solo JOIN en vez de N queries individuales de Product.
    """
    logger.info("[AUDIT] Iniciando revisión de emparejamientos de catálogo...")

    try:
        # Un solo query con JOIN eager a Product — elimina el N+1 anterior
        sps = (
            db_session.query(StoreProduct)
            .options(joinedload(StoreProduct.product))
            .filter(StoreProduct.product_id.isnot(None))
            .all()
        )

        invalid_ids: list[int] = []
        checked_count = 0

        for sp in sps:
            canonical = sp.product
            if not canonical:
                continue

            checked_count += 1

            prod_a = {
                "name": canonical.canonical_name,
                "brand": canonical.brand,
                "top_category": canonical.category,
                "weight_value": canonical.weight_value,
                "weight_unit": canonical.weight_unit,
            }

            prod_b = {
                "name": sp.name,
                "brand": sp.brand,
                "top_category": sp.top_category,
                "image_url": sp.image_url,
            }
            enrich_with_weight(prod_b)

            score = compute_match_score(prod_a, prod_b)

            if score < 0.75:
                invalid_ids.append(sp.id)
                logger.warning(
                    f"  [REMOVED] Enlace Roto: '{canonical.canonical_name}' =/=> '{sp.name}' (score: {score:.2f})"
                )

        if invalid_ids:
            # Batch delete de ProductMatch + clear de product_id en una sola pasada
            db_session.query(ProductMatch).filter(
                ProductMatch.store_product_id.in_(invalid_ids)
            ).delete(synchronize_session=False)

            db_session.query(StoreProduct).filter(
                StoreProduct.id.in_(invalid_ids)
            ).update({"product_id": None}, synchronize_session=False)

            db_session.commit()
            logger.info(
                f"[AUDIT] Completado. {len(invalid_ids)} falsos positivos eliminados de {checked_count} enlaces revisados."
            )
        else:
            logger.info(f"[AUDIT] Completado. {checked_count} enlaces saludables.")

    except Exception as e:
        logger.error(f"[AUDIT ERROR] Fallo durante la auto-limpieza heurística: {e}")
        db_session.rollback()

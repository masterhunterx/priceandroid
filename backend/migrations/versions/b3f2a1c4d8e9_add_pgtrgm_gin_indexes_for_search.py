"""add_pgtrgm_gin_indexes_for_search

Activa la extensión pg_trgm de PostgreSQL y crea índices GIN sobre los
campos de texto que se usan en búsquedas LIKE. Con estos índices, las
consultas LIKE '%término%' pasan de full-scan a búsqueda indexada.

También añade un índice compuesto (store_id, in_stock) para el filtro
más común: productos de una tienda que están en stock.

Revision ID: b3f2a1c4d8e9
Revises: 92cb1e57bc6c
Create Date: 2026-04-27

"""
from typing import Sequence, Union

from alembic import op


revision: str = 'b3f2a1c4d8e9'
down_revision: Union[str, Sequence[str], None] = '92cb1e57bc6c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name != 'postgresql':
        return  # pg_trgm solo existe en PostgreSQL; SQLite lo omite

    # Activar extensión de trigramas (requiere que Railway tenga pg_trgm disponible,
    # lo cual es estándar en todas las instancias de PostgreSQL >= 9.1)
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # Índices GIN para búsqueda LIKE sobre texto — permiten usar LIKE '%término%'
    # sin full-scan. Se aplica lower() para que coincida con func.lower() en el código.
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_sp_name_trgm
        ON store_products USING GIN (lower(name) gin_trgm_ops)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_sp_brand_trgm
        ON store_products USING GIN (lower(brand) gin_trgm_ops)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_sp_topcat_trgm
        ON store_products USING GIN (lower(top_category) gin_trgm_ops)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_sp_catpath_trgm
        ON store_products USING GIN (lower(category_path) gin_trgm_ops)
    """)

    # Índice compuesto para el filtro más común: tienda + en stock
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_sp_store_instock
        ON store_products (store_id, in_stock)
    """)


def downgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name != 'postgresql':
        return

    op.execute("DROP INDEX IF EXISTS idx_sp_store_instock")
    op.execute("DROP INDEX IF EXISTS idx_sp_catpath_trgm")
    op.execute("DROP INDEX IF EXISTS idx_sp_topcat_trgm")
    op.execute("DROP INDEX IF EXISTS idx_sp_brand_trgm")
    op.execute("DROP INDEX IF EXISTS idx_sp_name_trgm")
    # No se dropea pg_trgm — puede estar en uso por otras partes del sistema

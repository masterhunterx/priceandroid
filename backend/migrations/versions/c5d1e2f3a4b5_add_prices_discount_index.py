"""add_prices_discount_index

Índice compuesto (has_discount, scraped_at DESC) en la tabla prices para
acelerar la consulta de ofertas activas ordenadas por fecha más reciente.
Sin este índice cada petición a /api/deals hace un full-scan de prices.

Revision ID: c5d1e2f3a4b5
Revises: b3f2a1c4d8e9
Create Date: 2026-04-27

"""
from typing import Sequence, Union

from alembic import op


revision: str = 'c5d1e2f3a4b5'
down_revision: Union[str, Sequence[str], None] = 'b3f2a1c4d8e9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name != 'postgresql':
        return

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_prices_discount_scraped
        ON prices (has_discount, scraped_at DESC)
        WHERE has_discount = TRUE
    """)


def downgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name != 'postgresql':
        return

    op.execute("DROP INDEX IF EXISTS idx_prices_discount_scraped")

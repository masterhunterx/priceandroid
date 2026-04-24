"""
Database Connection & Session Management
=========================================
Handles SQLite (development) and PostgreSQL (production) connections.
"""

import os
from contextlib import contextmanager

from dotenv import load_dotenv
from sqlalchemy import create_engine, text as _sa_text
from sqlalchemy.orm import sessionmaker

from .models import Base, Store

# Load .env file from the backend directory (no-op if file doesn't exist)
load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Default: SQLite file in ./data/grocery.db
# Override with DATABASE_URL env var for PostgreSQL:
#   export DATABASE_URL="postgresql://user:pass@host:5432/grocery"
DEFAULT_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "grocery.db"
)
DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{DEFAULT_DB_PATH}")


# ---------------------------------------------------------------------------
# Engine & Session
# ---------------------------------------------------------------------------

_engine = None
_SessionFactory = None


def get_engine():
    """Get or create the database engine."""
    global _engine
    if _engine is None:
        os.makedirs(os.path.dirname(DEFAULT_DB_PATH), exist_ok=True)
        
        is_sqlite = "sqlite" in DATABASE_URL
        connect_args = {"check_same_thread": False} if is_sqlite else {}
        
        pg_kwargs = {}
        if not is_sqlite:
            pg_kwargs = {
                "pool_size":     int(os.getenv("DB_POOL_SIZE", "10")),
                "max_overflow":  int(os.getenv("DB_MAX_OVERFLOW", "20")),
                "pool_timeout":  30,
                "pool_pre_ping": True,  # descarta conexiones muertas antes de usarlas
            }

        _engine = create_engine(
            DATABASE_URL,
            echo=False,
            connect_args=connect_args,
            **pg_kwargs,
        )
        
        # Enable WAL mode for SQLite — allows concurrent reads + writes
        # without locking. Critical for CatalogBot + Sentry + API running together.
        if is_sqlite:
            from sqlalchemy import event, text
            @event.listens_for(_engine, "connect")
            def set_sqlite_wal(dbapi_connection, _connection_record):
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA journal_mode=WAL")      # Concurrent R/W
                cursor.execute("PRAGMA busy_timeout=30000")    # Wait 30s on lock
                cursor.execute("PRAGMA synchronous=NORMAL")    # Balanced durability
                cursor.execute("PRAGMA cache_size=-64000")     # 64MB cache
                cursor.close()
    return _engine



def get_session_factory():
    """Get or create the session factory."""
    global _SessionFactory
    if _SessionFactory is None:
        _SessionFactory = sessionmaker(bind=get_engine())
    return _SessionFactory


@contextmanager
def get_session():
    """Context manager for database sessions with auto-commit/rollback."""
    Session = get_session_factory()
    session = Session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------

# Default stores to seed
DEFAULT_STORES = [
    {
        "name": "Jumbo",
        "slug": "jumbo",
        "base_url": "https://www.jumbo.cl",
    },
    {
        "name": "Santa Isabel",
        "slug": "santa_isabel",
        "base_url": "https://www.santaisabel.cl",
    },
    {
        "name": "Lider",
        "slug": "lider",
        "base_url": "https://www.lider.cl",
    },
    {
        "name": "Unimarc",
        "slug": "unimarc",
        "base_url": "https://www.unimarc.cl",
    },
]


def _column_exists(conn, table: str, column: str, is_sqlite: bool) -> bool:
    """Comprueba si una columna existe en la tabla (compatible con SQLite y Postgres)."""
    if is_sqlite:
        rows = conn.execute(_sa_text(f"PRAGMA table_info({table})")).fetchall()
        return column in {row[1] for row in rows}
    rows = conn.execute(_sa_text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = :t AND column_name = :c"
    ), {"t": table, "c": column}).fetchall()
    return len(rows) > 0


def _apply_migrations(engine):
    """
    Migraciones incrementales idempotentes — única fuente de verdad para cambios de esquema.
    Reemplaza el uso de Alembic para este proyecto: más simple, sin archivos de versión,
    y compatible con Railway (sin acceso directo al shell para correr `alembic upgrade`).
    Cada entrada es (tabla, columna, tipo, default_sql). Seguro ejecutar varias veces.
    """
    import logging as _logging
    _mig_log = _logging.getLogger("AntigravityAPI")

    # (table, column, type, default_value_sql)
    migrations = [
        ("user_assistant_state", "chat_history_json", "TEXT",         None),
        ("user_preferences",     "user_id",           "VARCHAR(100)", "'default_user'"),
        ("notifications",        "user_id",           "VARCHAR(100)", "'default_user'"),
        ("pantry_items",         "user_id",           "VARCHAR(100)", "'default_user'"),
        ("branches",             "latitude",          "FLOAT",        None),
        ("branches",             "longitude",         "FLOAT",        None),
        ("branches",             "verified_at",       "TIMESTAMP",    None),
    ]
    is_sqlite = "sqlite" in DATABASE_URL
    for table, column, col_type, default in migrations:
        with engine.connect() as conn:
            try:
                if _column_exists(conn, table, column, is_sqlite):
                    continue
                default_clause = f" DEFAULT {default}" if default else ""
                sql = f"ALTER TABLE {table} ADD COLUMN {column} {col_type}{default_clause}"
                conn.execute(_sa_text(sql))
                conn.commit()
                _mig_log.info(f"[Migration] Columna añadida: {table}.{column}")
            except Exception as _e:
                conn.rollback()
                _mig_log.error(f"[Migration] Falló {table}.{column}: {_e}")

    # Índices de rendimiento — idempotentes via IF NOT EXISTS (Postgres y SQLite 3.3+)
    index_migrations = [
        ("idx_sp_store_id",       "store_products", "store_id"),
        ("idx_sp_in_stock",       "store_products", "in_stock"),
        ("idx_sp_last_sync",      "store_products", "last_sync"),
        ("idx_sp_stock_sync",     "store_products", "in_stock, last_sync"),
        ("idx_price_sp_id",       "prices",         "store_product_id"),
        ("idx_price_has_discount","prices",         "has_discount"),
    ]
    for idx_name, table, column in index_migrations:
        with engine.connect() as conn:
            try:
                conn.execute(_sa_text(
                    f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table} ({column})"
                ))
                conn.commit()
            except Exception:
                conn.rollback()


def init_db():
    """
    Create all tables and seed with default stores.
    Safe to call multiple times (idempotent).
    """
    engine = get_engine()
    Base.metadata.create_all(engine)
    _apply_migrations(engine)

    with get_session() as session:
        for store_data in DEFAULT_STORES:
            existing = session.query(Store).filter_by(slug=store_data["slug"]).first()
            if not existing:
                session.add(Store(**store_data))
                print(f"  Seeded store: {store_data['name']}")

    print(f"  Database ready at: {DATABASE_URL}")


if __name__ == "__main__":
    print("Initializing database...")
    init_db()
    print("Done!")

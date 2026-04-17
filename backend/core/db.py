"""
Database Connection & Session Management
=========================================
Handles SQLite (development) and PostgreSQL (production) connections.
"""

import os
from contextlib import contextmanager

from dotenv import load_dotenv
from sqlalchemy import create_engine
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
        
        _engine = create_engine(
            DATABASE_URL,
            echo=False,
            connect_args=connect_args,
            # SQLite: pool_size not supported; use StaticPool for single-file
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


def _apply_migrations(engine):
    """
    Aplica migraciones incrementales para columnas nuevas en tablas existentes.
    SQLAlchemy create_all no agrega columnas a tablas ya existentes, así que
    hacemos un ALTER TABLE manual idempotente.
    """
    migrations = [
        ("user_assistant_state", "chat_history_json", "TEXT"),
    ]
    with engine.connect() as conn:
        for table, column, col_type in migrations:
            try:
                conn.execute(
                    __import__("sqlalchemy").text(
                        f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"
                    )
                )
                conn.commit()
            except Exception:
                pass  # Columna ya existe — ignorar


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

"""
migrate_to_postgres.py — Fast version using psycopg2 execute_values (bulk insert)
"""
import os, sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

SQLITE_PATH = Path(__file__).parent / "data" / "grocery.db"
PG_URL      = os.environ.get("DATABASE_URL", "")

if not PG_URL.startswith("postgresql"):
    print("ERROR: DATABASE_URL debe ser postgresql://...")
    sys.exit(1)

if not SQLITE_PATH.exists():
    print(f"ERROR: No se encontro SQLite en {SQLITE_PATH}")
    sys.exit(1)

print(f"\n[1/4] Conectando...")
print(f"  SQLite  : {SQLITE_PATH}")
print(f"  Postgres: {PG_URL[:55]}...")

import sqlite3
import psycopg2
import psycopg2.extras
from urllib.parse import urlparse
from sqlalchemy import create_engine, text, inspect, Boolean
sys.path.insert(0, str(Path(__file__).parent))
from core.models import Base

# ── Parsear URL para psycopg2 ─────────────────────────────────────────────────
u = urlparse(PG_URL)
pg_conn = psycopg2.connect(
    host=u.hostname, port=u.port or 5432,
    dbname=u.path.lstrip("/"),
    user=u.username, password=u.password,
    connect_timeout=30,
    options="-c statement_timeout=0"
)
pg_conn.autocommit = False

# SQLite con row_factory
sqlite_conn = sqlite3.connect(str(SQLITE_PATH))
sqlite_conn.row_factory = sqlite3.Row

# ── Paso 1: Crear schema ──────────────────────────────────────────────────────
print("\n[2/4] Creando schema en PostgreSQL...")
pg_engine = create_engine(PG_URL, echo=False)
Base.metadata.create_all(pg_engine)
print("  Schema OK.")

# ── Detectar columnas booleanas ───────────────────────────────────────────────
def get_bool_cols(table_name):
    cols = set()
    for t in Base.metadata.tables.values():
        if t.name == table_name:
            for col in t.columns:
                if isinstance(col.type, Boolean):
                    cols.add(col.name)
    return cols

TABLES_ORDER = [
    "stores", "locations", "branches", "products", "store_products",
    "prices", "product_matches", "price_insights", "notifications",
    "user_preferences", "bot_state", "user_assistant_state",
    "blocked_ips", "rate_limit_state", "security_log", "pantry_items",
]

print(f"\n[3/4] Copiando datos SQLite -> PostgreSQL (modo rapido)...")

sqlite_cur = sqlite_conn.cursor()
pg_cur     = pg_conn.cursor()

# Obtener tablas existentes en Postgres
pg_cur.execute("""
    SELECT table_name FROM information_schema.tables
    WHERE table_schema = 'public'
""")
pg_tables = {r[0] for r in pg_cur.fetchall()}

# Obtener tablas SQLite
sqlite_cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
sqlite_tables = {r[0] for r in sqlite_cur.fetchall()}

total_rows = 0
BATCH = 5000  # 10x más grande que antes

for table in TABLES_ORDER:
    if table not in sqlite_tables:
        print(f"  [{table}] no existe en SQLite, saltando.")
        continue
    if table not in pg_tables:
        print(f"  [{table}] no existe en Postgres, saltando.")
        continue

    # Columnas comunes
    sqlite_cur.execute(f'PRAGMA table_info("{table}")')
    src_cols = [r[1] for r in sqlite_cur.fetchall()]

    pg_cur.execute(f"""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = %s AND table_schema = 'public'
    """, (table,))  # nosec B608 — table name from internal code, not user input
    dst_cols = {r[0] for r in pg_cur.fetchall()}
    common   = [c for c in src_cols if c in dst_cols]

    if not common:
        print(f"  [{table}] sin columnas comunes, saltando.")
        continue

    # Contar filas
    sqlite_cur.execute(f'SELECT COUNT(*) FROM "{table}"')  # nosec B608
    count = sqlite_cur.fetchone()[0]
    if count == 0:
        print(f"  [{table}] vacia, saltando.")
        continue

    bool_cols = get_bool_cols(table)

    # Truncar destino
    try:
        pg_cur.execute(f'TRUNCATE TABLE "{table}" CASCADE')
        pg_conn.commit()
    except Exception:
        pg_conn.rollback()

    # Leer y bulk-insert
    col_list = ", ".join(f'"{c}"' for c in common)
    sqlite_cur.execute(f'SELECT {col_list} FROM "{table}"')  # nosec B608

    inserted = 0
    while True:
        rows = sqlite_cur.fetchmany(BATCH)
        if not rows:
            break

        # Convertir booleanos
        batch = []
        for row in rows:
            r = list(row)
            for i, col in enumerate(common):
                if col in bool_cols and r[i] is not None:
                    r[i] = bool(r[i])
            batch.append(tuple(r))

        placeholders = "(" + ", ".join(["%s"] * len(common)) + ")"
        insert_sql   = f'INSERT INTO "{table}" ({col_list}) VALUES %s'  # nosec B608
        try:
            psycopg2.extras.execute_values(
                pg_cur, insert_sql, batch,
                template=placeholders, page_size=BATCH
            )
            pg_conn.commit()
            inserted += len(batch)
            if count > BATCH:
                print(f"  [{table}] {inserted}/{count}...", flush=True)
        except Exception as e:
            pg_conn.rollback()
            print(f"  [{table}] ERROR en lote: {e}")
            break

    print(f"  [{table}] {inserted}/{count} filas OK.")
    total_rows += inserted

print(f"\n  Total: {total_rows:,} filas copiadas.")

# ── Paso 4: Resetear secuencias ───────────────────────────────────────────────
print("\n[4/4] Reseteando secuencias...")
for table in TABLES_ORDER:
    try:
        pg_cur.execute(f"""  # nosec B608 — table from TABLES_ORDER constant, not user input
            SELECT setval(
                pg_get_serial_sequence('{table}', 'id'),
                COALESCE((SELECT MAX(id) FROM "{table}"), 1)
            )
        """)
        pg_conn.commit()
    except Exception:
        pg_conn.rollback()

pg_cur.close()
pg_conn.close()
sqlite_conn.close()
print("\nMigracion completada exitosamente.")

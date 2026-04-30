"""
Migración: crear tabla users y seedear usuarios existentes desde env vars.
Ejecutar una sola vez contra Railway:
  DATABASE_URL=... python scripts/migrate_users.py
"""
import os
import sys
import logging

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from core.db import get_engine, get_session
from core.models import Base, User

try:
    import bcrypt
    def hash_pw(plain: str) -> str:
        return bcrypt.hashpw(plain.encode(), bcrypt.gensalt(rounds=12)).decode()
except ImportError:
    import hashlib, secrets
    def hash_pw(plain: str) -> str:
        salt = secrets.token_hex(16)
        return f"sha256:{salt}:{hashlib.sha256((salt + plain).encode()).hexdigest()}"


def run():
    engine = get_engine()

    # Crear tabla users si no existe
    log.info("Creando tabla 'users' si no existe...")
    Base.metadata.create_all(engine, tables=[User.__table__])
    log.info("✓ Tabla users lista.")

    admin_username = os.getenv("ADMIN_USERNAME", "admin")
    admin_password = os.getenv("ADMIN_PASSWORD", "")

    # Usuarios a seedear: (username, password_raw_o_hash, email, role, approved)
    seed_users = [
        (admin_username, admin_password, None, "admin", True),
        ("test1", os.getenv("TEST1_PASSWORD", ""), "test1@freshcart.cl", "user", True),
        ("test2", os.getenv("TEST2_PASSWORD", ""), "test2@freshcart.cl", "user", True),
        ("test3", os.getenv("TEST3_PASSWORD", ""), "test3@freshcart.cl", "user", True),
    ]

    with get_session() as db:
        for username, password, email, role, approved in seed_users:
            if not password:
                log.warning(f"  ⚠ Sin contraseña para '{username}', omitiendo.")
                continue

            existing = db.query(User).filter(User.username == username.lower()).first()
            if existing:
                log.info(f"  · '{username}' ya existe, actualizando hash si cambió...")
                # Si la contraseña almacenada NO es bcrypt, actualizarla
                if not existing.password_hash.startswith("$2"):
                    existing.password_hash = (
                        password if password.startswith("$2") else hash_pw(password)
                    )
                existing.role = role
                existing.is_approved = approved
                existing.email = email or existing.email
            else:
                pw_hash = password if password.startswith(("$2b$", "$2a$", "$2y$")) else hash_pw(password)
                db.add(User(
                    username=username.lower(),
                    email=email,
                    password_hash=pw_hash,
                    role=role,
                    is_active=True,
                    is_approved=approved,
                ))
                log.info(f"  ✓ Usuario '{username}' creado (role={role}, approved={approved}).")

    log.info("\nMigración completada.")

    # Listar usuarios resultantes
    with get_session() as db:
        users = db.query(User).order_by(User.id).all()
        log.info(f"\nUsuarios en BD ({len(users)} total):")
        for u in users:
            log.info(f"  [{u.id}] {u.username} | role={u.role} | approved={u.is_approved} | email={u.email}")


if __name__ == "__main__":
    run()

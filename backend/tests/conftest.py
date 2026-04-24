"""
Configuración compartida para tests de integración.
Parchea agentes de fondo y usa SQLite en memoria.
"""
import os
import sys
from unittest.mock import patch, MagicMock

# Variables de entorno ANTES de cualquier import del proyecto
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_ci.db")
os.environ.setdefault("API_KEY", "test-key-ci")
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("DISCORD_WEBHOOK_URL", "")
os.environ.setdefault("DISCORD_BOT_TOKEN", "")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest


@pytest.fixture(scope="session")
def api_client():
    """TestClient con DB SQLite y agentes de fondo desactivados."""
    with patch("api.main.start_background_agents", return_value=None), \
         patch("core.discord_bot.bot", MagicMock()), \
         patch("core.discord_bot.DISCORD_BOT_TOKEN", ""):
        from fastapi.testclient import TestClient
        from api.main import app
        with TestClient(app, raise_server_exceptions=True) as client:
            yield client


@pytest.fixture
def headers():
    return {"X-API-Key": os.environ["API_KEY"]}

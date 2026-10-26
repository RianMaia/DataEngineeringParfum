import pytest
from fastapi.testclient import TestClient
from test_carga.conftest import banco, conexoes, modelo, servidor  # noqa: F401 - fixtures de banco reaproveitadas

from app.main import app


@pytest.fixture
def cliente_api(monkeypatch, servidor, banco):  # noqa: F811
    """A API apontada para um banco de teste novo (o perfil somente leitura em si foi provado na C5)."""
    monkeypatch.setenv("POSTGRES_HOST", servidor["host"])
    monkeypatch.setenv("POSTGRES_PORTA", str(servidor["port"]))
    monkeypatch.setenv("POSTGRES_DB", banco)
    monkeypatch.setenv("POSTGRES_API_USUARIO", servidor["user"])
    monkeypatch.setenv("POSTGRES_API_SENHA", servidor["password"])
    with TestClient(app) as cliente:
        yield cliente

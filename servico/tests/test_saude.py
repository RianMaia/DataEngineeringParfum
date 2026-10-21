"""Teste do endpoint de saúde, sem rede, sem banco e sem Databricks."""

from fastapi.testclient import TestClient

from app.main import app

cliente = TestClient(app)


def test_saude_responde_ok():
    resposta = cliente.get("/saude")

    assert resposta.status_code == 200
    assert resposta.json() == {"status": "ok"}

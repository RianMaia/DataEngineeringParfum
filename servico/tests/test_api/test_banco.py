import psycopg
import pytest
from fastapi.testclient import TestClient
from test_carga.dados_falsos import FonteFalsa, gerar

from app import banco as modulo_banco
from app.banco import ler_meta, parametros_de_conexao
from app.main import app
from carga.executar import executar


def test_pronto_responde_ok_com_o_banco_no_ar(cliente_api):
    resposta = cliente_api.get("/pronto")
    assert resposta.status_code == 200 and resposta.json() == {"status": "ok"}


def test_sem_banco_o_pronto_da_503_sem_detalhes_e_o_saude_continua_ok(monkeypatch):
    monkeypatch.setenv("POSTGRES_PORTA", "1")  # porta onde ninguém escuta
    monkeypatch.setenv("POSTGRES_API_USUARIO", "usuario_x")
    monkeypatch.setenv("POSTGRES_API_SENHA", "SENHA_SECRETA_XYZ")
    monkeypatch.setattr(modulo_banco, "TEMPO_LIMITE_SEGUNDOS", 1)
    with TestClient(app) as cliente:
        pronto = cliente.get("/pronto")
        assert pronto.status_code == 503
        assert pronto.json() == {"detalhe": "banco de dados indisponível"}
        for segredo in ("SENHA_SECRETA_XYZ", "usuario_x", "127.0.0.1"):
            assert segredo not in pronto.text
        assert cliente.get("/saude").json() == {"status": "ok"}


def test_variavel_obrigatoria_ausente_e_nomeada_sem_mostrar_valores(monkeypatch):
    monkeypatch.setenv("POSTGRES_API_USUARIO", "usuario_x")
    monkeypatch.delenv("POSTGRES_API_SENHA", raising=False)
    with pytest.raises(RuntimeError, match="POSTGRES_API_SENHA") as erro:
        parametros_de_conexao()
    assert "usuario_x" not in str(erro.value)


def test_as_conexoes_da_api_sao_somente_leitura(cliente_api):
    with app.state.pool.connection() as conexao, pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
        conexao.execute("INSERT INTO clientes VALUES (1)")


def test_meta_vazio_antes_da_carga_e_preenchido_depois(cliente_api, conexoes):
    with app.state.pool.connection() as conexao:
        assert ler_meta(conexao) is None
    dados, meta = gerar()
    assert executar(FonteFalsa(dados, meta), *conexoes) == 0
    with app.state.pool.connection() as conexao:
        lido = ler_meta(conexao)
    assert lido["carga_id"] == 1 and lido["concluida_em"] is not None
    assert lido["data_referencia_score"] == meta["data_referencia_score"]
    assert lido["snapshot_estoque_global"] == meta["snapshot_estoque_global"]


def test_o_pool_e_fechado_quando_a_aplicacao_encerra(cliente_api):
    pool = app.state.pool
    assert pool.closed is False
    cliente_api.__exit__(None, None, None)
    assert pool.closed is True


def test_meta_ignora_cargas_que_falharam(cliente_api, conexoes):
    dados, meta = gerar()
    assert executar(FonteFalsa(dados, meta), *conexoes) == 0
    sem_clientes = dict(dados)
    sem_clientes["clientes"] = []
    assert executar(FonteFalsa(sem_clientes, meta), *conexoes) == 1  # a 2ª carga falha e fica registrada como falha
    with app.state.pool.connection() as conexao:
        assert ler_meta(conexao)["carga_id"] == 1  # o meta continua sendo o da última carga CONCLUÍDA

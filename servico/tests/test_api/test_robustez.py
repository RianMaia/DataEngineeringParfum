"""Robustez da API: conexão morta, locks, fotografia única, erros inesperados, cabeçalhos e logs."""

import logging
import threading
import time

import psycopg
import pytest
from fastapi.testclient import TestClient
from test_carga.dados_falsos import FonteFalsa, gerar

from app import banco as modulo_banco
from app import contexto as modulo_contexto
from app.banco import ler_meta
from app.leitura import obter_leitura_consistente
from app.main import app
from carga.esquema import ORDEM_APAGAR
from carga.executar import executar


@pytest.fixture
def lock_curto(monkeypatch):
    """Vale para o pool que o cliente_api abrir: este fixture precisa vir ANTES dele nos argumentos."""
    monkeypatch.setattr(modulo_banco, "TEMPO_MAXIMO_LOCK_MS", 500, raising=False)


@pytest.fixture
def cliente_sem_relancar(monkeypatch, servidor, banco):
    """Como o cliente_api, mas devolve a resposta 500 em vez de relançar o erro dentro do teste."""
    monkeypatch.setenv("POSTGRES_HOST", servidor["host"])
    monkeypatch.setenv("POSTGRES_PORTA", str(servidor["port"]))
    monkeypatch.setenv("POSTGRES_DB", banco)
    monkeypatch.setenv("POSTGRES_API_USUARIO", servidor["user"])
    monkeypatch.setenv("POSTGRES_API_SENHA", servidor["password"])
    with TestClient(app, raise_server_exceptions=False) as cliente:
        yield cliente


def carregar(conexoes, **opcoes):
    dados, meta = gerar(**opcoes)
    assert executar(FonteFalsa(dados, meta), *conexoes) == 0
    return dados, meta


def test_uma_conexao_morta_no_pool_nao_derruba_a_requisicao(cliente_api, banco, servidor):
    assert cliente_api.get("/pronto").status_code == 200  # o pool agora tem uma conexão aberta
    with psycopg.connect(dbname="postgres", autocommit=True, **servidor) as admin:  # simula o banco reiniciando
        admin.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s AND pid <> pg_backend_pid()",
            (banco,),
        )
    time.sleep(0.3)
    assert [cliente_api.get("/pronto").status_code for _ in range(3)] == [200, 200, 200]


def test_um_lock_forte_nao_prende_a_leitura_para_sempre(lock_curto, cliente_api, conexoes, banco, servidor):
    carregar(conexoes)
    resultado = {}
    with psycopg.connect(dbname=banco, **servidor) as trava:
        trava.execute("LOCK TABLE fila_semanal IN ACCESS EXCLUSIVE MODE")  # como um TRUNCATE ou ALTER esquecido
        fio = threading.Thread(target=lambda: resultado.update(resposta=cliente_api.get("/fila/1")), daemon=True)
        fio.start()
        fio.join(timeout=8)
        preso = fio.is_alive()
        trava.rollback()  # libera o lock; se a requisição estava presa, ela termina agora
    fio.join(timeout=5)
    assert not preso, "a requisição ficou presa esperando o lock"
    assert resultado["resposta"].status_code == 503


def test_os_limites_de_tempo_estao_na_sessao_da_api(cliente_api):
    with app.state.pool.connection() as conexao:
        valores = {
            nome: conexao.execute(f"SHOW {nome}").fetchone()[0]
            for nome in ("statement_timeout", "lock_timeout", "idle_in_transaction_session_timeout")
        }
    assert valores == {"statement_timeout": "10s", "lock_timeout": "3s", "idle_in_transaction_session_timeout": "30s"}


def test_uma_requisicao_ve_uma_so_fotografia_mesmo_se_uma_carga_conclui_no_meio(cliente_api, conexoes):
    carregar(conexoes, n_clientes=50, semente=1)
    with app.state.pool.connection() as conexao:
        obter_leitura_consistente(conexao)  # o que toda rota de dados faz primeiro
        assert ler_meta(conexao)["carga_id"] == 1
        antes = conexao.execute("SELECT count(*) FROM clientes").fetchone()[0]
        carregar(conexoes, n_clientes=40, semente=2)  # uma carga NOVA conclui enquanto a requisição está no meio
        assert conexao.execute("SELECT count(*) FROM clientes").fetchone()[0] == antes == 50
        assert ler_meta(conexao)["carga_id"] == 1
    with app.state.pool.connection() as nova:
        assert ler_meta(nova)["carga_id"] == 2
        assert nova.execute("SELECT count(*) FROM clientes").fetchone()[0] == 40


def test_uma_carga_em_andamento_nao_bloqueia_a_leitura(cliente_api, conexoes, banco, servidor):
    dados, _ = carregar(conexoes)
    cliente = dados["clientes"][0][0]
    total = cliente_api.get(f"/cliente/{cliente}/produtos-sugeridos").json()["total"]
    with psycopg.connect(dbname=banco, **servidor) as escritor:  # a transação de uma carga, ainda sem COMMIT
        for tabela in ORDEM_APAGAR:
            escritor.execute(f"DELETE FROM {tabela}")
        inicio = time.time()
        resposta = cliente_api.get(f"/cliente/{cliente}/produtos-sugeridos")
        assert resposta.status_code == 200 and resposta.json()["total"] == total  # ainda vê os dados antigos
        assert time.time() - inicio < 2
        escritor.rollback()


def test_erro_interno_sai_no_formato_padrao_e_sem_detalhes(cliente_sem_relancar, monkeypatch):
    def explode(*argumentos, **opcoes):
        raise RuntimeError("SEGREDO_CANARIO")

    monkeypatch.setattr(modulo_contexto, "exigir_meta", explode)
    resposta = cliente_sem_relancar.get("/cliente/1/contexto")
    assert resposta.status_code == 500 and resposta.json() == {"detalhe": "erro interno"}
    assert "SEGREDO" not in resposta.text


def test_o_405_mantem_o_cabecalho_allow(cliente_api):
    resposta = cliente_api.post("/saude")
    assert resposta.status_code == 405 and "GET" in resposta.headers.get("allow", "")


def test_a_senha_nao_aparece_nos_logs_com_o_banco_fora_do_ar(monkeypatch, caplog):
    monkeypatch.setenv("POSTGRES_PORTA", "1")
    monkeypatch.setenv("POSTGRES_API_USUARIO", "usuario_x")
    monkeypatch.setenv("POSTGRES_API_SENHA", "SENHA_CANARIO_LOG")
    monkeypatch.setattr(modulo_banco, "TEMPO_LIMITE_SEGUNDOS", 1)
    caplog.set_level(logging.DEBUG)
    with TestClient(app) as cliente:
        cliente.get("/pronto")
    assert "SENHA_CANARIO_LOG" not in caplog.text


@pytest.mark.parametrize("rota", ["/fila/{n}", "/cliente/{n}/contexto", "/cliente/{n}/produtos-sugeridos"])
def test_identificador_maior_que_um_bigint_da_404_e_nao_500(cliente_api, conexoes, rota):
    carregar(conexoes)  # sem nenhuma carga a resposta seria 503, e não é isso que está em teste
    resposta = cliente_api.get(rota.format(n="99999999999999999999999"))
    assert resposta.status_code == 404  # não existe: nem erro do servidor, nem validação

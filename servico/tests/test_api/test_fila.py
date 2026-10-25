from typing import Annotated

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from psycopg import Connection, sql
from test_carga.dados_falsos import FonteFalsa, gerar

from app.leitura import obter_leitura_consistente
from app.main import app
from carga.executar import executar


@pytest.fixture
def carga_pronta(conexoes, banco):
    """Uma carga concluída. A fila entra no banco em ordem INVERSA, para o teste provar que a API ordena.

    Sem índices, o PostgreSQL devolve as linhas na ordem física (a inversa): só o ORDER BY da consulta as ordena.
    Este fixture precisa vir ANTES de cliente_api, para valer nas conexões que o pool da API abrir.
    """
    for opcao in ("enable_indexscan", "enable_bitmapscan", "enable_indexonlyscan"):
        conexoes[0].execute(
            sql.SQL("ALTER DATABASE {} SET {} = off").format(sql.Identifier(banco), sql.Identifier(opcao))
        )
    dados, meta = gerar()
    dados["fila_semanal"] = list(reversed(dados["fila_semanal"]))
    assert executar(FonteFalsa(dados, meta), *conexoes) == 0
    return dados, meta


def esperados(dados, vendedor_id):
    return sorted((linha for linha in dados["fila_semanal"] if linha[1] == vendedor_id), key=lambda linha: linha[4])


def test_fila_do_vendedor_vem_ordenada_e_com_o_meta_da_carga(carga_pronta, cliente_api):
    dados, meta = carga_pronta
    certos = esperados(dados, 1)
    resposta = cliente_api.get("/fila/1")
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["vendedor"] == {"id": 1, "nome": "VENDEDOR_SECRETO_1", "regiao": "Regiao", "uf": "CE", "ativo": True}
    assert corpo["total"] == len(corpo["itens"]) == len(certos) > 1
    assert [item["posicao"] for item in corpo["itens"]] == [linha[4] for linha in certos]
    assert [item["cliente_id"] for item in corpo["itens"]] == [linha[0] for linha in certos]
    primeiro = corpo["itens"][0]
    assert primeiro["score"] == certos[0][8] and primeiro["motivo"] == "motivo" and primeiro["faixa"] == "alta"
    assert corpo["meta"]["carga_id"] == 1
    assert corpo["meta"]["data_referencia_score"] == meta["data_referencia_score"].isoformat()
    assert corpo["meta"]["snapshot_estoque_global"] == meta["snapshot_estoque_global"].isoformat()


def test_vendedores_homonimos_recebem_cada_um_a_sua_fila(carga_pronta, cliente_api):
    dados, _ = carga_pronta
    quinto, sexto = cliente_api.get("/fila/5").json(), cliente_api.get("/fila/6").json()
    assert quinto["vendedor"]["nome"] == sexto["vendedor"]["nome"]  # mesmo nome, ids diferentes
    assert [i["cliente_id"] for i in quinto["itens"]] == [linha[0] for linha in esperados(dados, 5)]
    assert [i["cliente_id"] for i in sexto["itens"]] == [linha[0] for linha in esperados(dados, 6)]
    assert not {i["cliente_id"] for i in quinto["itens"]} & {i["cliente_id"] for i in sexto["itens"]}


def test_vendedor_inexistente_da_404(carga_pronta, cliente_api):
    resposta = cliente_api.get("/fila/999")
    assert resposta.status_code == 404 and resposta.json() == {"detalhe": "vendedor não encontrado"}


def test_vendedor_sem_clientes_na_fila_da_lista_vazia(cliente_api, conexoes):
    dados, meta = gerar(n_fila=2)  # só os vendedores 1 e 2 têm fila
    assert executar(FonteFalsa(dados, meta), *conexoes) == 0
    corpo = cliente_api.get("/fila/3").json()
    assert corpo["total"] == 0 and corpo["itens"] == [] and corpo["vendedor"]["id"] == 3


@pytest.mark.parametrize("valor", ["0", "-1", "abc"])
def test_identificador_invalido_da_422(cliente_api, valor):
    assert cliente_api.get(f"/fila/{valor}").status_code == 422


def test_sem_nenhuma_carga_concluida_da_503(cliente_api):
    resposta = cliente_api.get("/fila/1")
    assert resposta.status_code == 503 and resposta.json() == {"detalhe": "nenhuma carga concluída"}


def test_rota_inexistente_usa_o_mesmo_formato_de_erro(cliente_api):
    resposta = cliente_api.get("/nao-existe")
    assert resposta.status_code == 404 and resposta.json() == {"detalhe": "Not Found"}


def test_a_leitura_consistente_usa_uma_unica_fotografia_do_banco(cliente_api):
    pequena = FastAPI()
    pequena.state.pool = app.state.pool

    @pequena.get("/isolamento")
    def isolamento(conexao: Annotated[Connection, Depends(obter_leitura_consistente)]):
        return conexao.execute("SHOW transaction_isolation").fetchone()[0]

    assert TestClient(pequena).get("/isolamento").json() == "repeatable read"

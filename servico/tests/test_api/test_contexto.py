from test_carga.dados_falsos import FonteFalsa, gerar

from carga.executar import executar

from .comum import banco_sem_indices  # noqa: F401


def cliente_com(dados, quantas_marcas):
    contagem = {}
    for linha in dados["contexto_cliente"]:
        contagem[linha[0]] = contagem.get(linha[0], 0) + 1
    return next(cliente for cliente, total in contagem.items() if total == quantas_marcas)


def test_contexto_traz_resumo_marcas_em_ordem_e_meta(banco_sem_indices, cliente_api, conexoes):  # noqa: F811
    dados, meta = gerar()
    dados["contexto_cliente"] = list(reversed(dados["contexto_cliente"]))  # entra no banco em ordem inversa
    assert executar(FonteFalsa(dados, meta), *conexoes) == 0
    cliente = cliente_com(dados, 3)
    corpo = cliente_api.get(f"/cliente/{cliente}/contexto").json()
    assert corpo["cliente"] == {
        "id": cliente,
        "razao_social": f"RAZAO_SECRETA_{cliente}",
        "data_primeira_compra": "2026-08-01",
        "data_ultima_compra": "2026-08-01",
        "pedidos": 5,
        "ticket_medio": 99.9,
    }
    assert [m["ranking"] for m in corpo["marcas"]] == [1, 2, 3]
    assert [m["receita"] for m in corpo["marcas"]] == [10.25, 20.5, 30.75]
    assert corpo["marcas"][0]["marca"] == "marca"
    assert corpo["meta"]["carga_id"] == 1 and corpo["meta"]["data_referencia_score"] == "2026-08-31"


def test_cliente_com_menos_de_3_marcas_recebe_so_as_que_tem(cliente_api, conexoes):
    dados, meta = gerar()
    assert executar(FonteFalsa(dados, meta), *conexoes) == 0
    cliente = cliente_com(dados, 1)
    assert [m["ranking"] for m in cliente_api.get(f"/cliente/{cliente}/contexto").json()["marcas"]] == [1]


def test_cliente_sem_historico_da_200_com_campos_vazios(cliente_api, conexoes):
    dados, meta = gerar()
    cliente = dados["clientes"][0][0]
    dados["contexto_cliente"] = [linha for linha in dados["contexto_cliente"] if linha[0] != cliente]
    assert executar(FonteFalsa(dados, meta), *conexoes) == 0
    corpo = cliente_api.get(f"/cliente/{cliente}/contexto").json()
    assert corpo["marcas"] == []
    assert corpo["cliente"] == {
        "id": cliente,
        "razao_social": None,
        "data_primeira_compra": None,
        "data_ultima_compra": None,
        "pedidos": None,
        "ticket_medio": None,
    }


def test_cliente_inexistente_da_404(cliente_api, conexoes):
    dados, meta = gerar()
    assert executar(FonteFalsa(dados, meta), *conexoes) == 0
    resposta = cliente_api.get("/cliente/1/contexto")
    assert resposta.status_code == 404 and resposta.json() == {"detalhe": "cliente não encontrado"}


def test_identificador_invalido_da_422(cliente_api):
    assert cliente_api.get("/cliente/0/contexto").status_code == 422
    assert cliente_api.get("/cliente/abc/contexto").status_code == 422


def test_sem_nenhuma_carga_concluida_da_503(cliente_api):
    resposta = cliente_api.get("/cliente/1/contexto")
    assert resposta.status_code == 503 and resposta.json() == {"detalhe": "nenhuma carga concluída"}

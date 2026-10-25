import pytest
from test_carga.dados_falsos import FonteFalsa, gerar

from carga.executar import executar

from .comum import banco_sem_indices  # noqa: F401


def produtos_por_sku(dados):
    return {linha[0]: linha for linha in dados["produtos"]}


def sugestoes_do(dados, cliente):
    return sorted((linha for linha in dados["sugestoes_cliente"] if linha[0] == cliente), key=lambda linha: linha[2])


def cliente_com_ruptura_e_estoque(dados):
    """Um cliente cujas sugestões incluem produtos em ruptura E produtos com estoque, e que tem 4 ou mais."""
    produtos = produtos_por_sku(dados)
    for (cliente,) in dados["clientes"]:
        ruptura = [produtos[linha[1]][5] for linha in sugestoes_do(dados, cliente)]
        if len(ruptura) >= 4 and True in ruptura and False in ruptura:
            return cliente
    raise AssertionError("os dados de teste não têm um cliente assim")


def carregar(conexoes, dados, meta):
    assert executar(FonteFalsa(dados, meta), *conexoes) == 0


def test_sugestoes_vem_em_ordem_com_dados_do_produto_e_meta(banco_sem_indices, cliente_api, conexoes):  # noqa: F811
    dados, meta = gerar()
    dados["sugestoes_cliente"] = list(reversed(dados["sugestoes_cliente"]))
    carregar(conexoes, dados, meta)
    cliente = cliente_com_ruptura_e_estoque(dados)
    certas = sugestoes_do(dados, cliente)
    corpo = cliente_api.get(f"/cliente/{cliente}/produtos-sugeridos").json()
    assert corpo["cliente_id"] == cliente and corpo["total"] == len(corpo["itens"]) == len(certas)
    assert [i["ordem"] for i in corpo["itens"]] == [linha[2] for linha in certas]
    assert [i["sku"] for i in corpo["itens"]] == [linha[1] for linha in certas]
    primeiro, produto = corpo["itens"][0], produtos_por_sku(dados)[certas[0][1]]
    assert primeiro["saldo"] == produto[4] and primeiro["ruptura"] == produto[5] and primeiro["descontinuado"] is False
    assert primeiro["unidades_compradas"] == certas[0][3] and primeiro["ultima_compra"] == "2026-08-01"
    assert corpo["meta"]["carga_id"] == 1


def test_limit_corta_a_lista_mas_o_total_continua_inteiro(cliente_api, conexoes):
    dados, meta = gerar()
    carregar(conexoes, dados, meta)
    cliente = cliente_com_ruptura_e_estoque(dados)
    certas = sugestoes_do(dados, cliente)
    corpo = cliente_api.get(f"/cliente/{cliente}/produtos-sugeridos?limit=2").json()
    assert len(corpo["itens"]) == 2 and corpo["total"] == len(certas)
    assert [i["sku"] for i in corpo["itens"]] == [linha[1] for linha in certas[:2]]


def test_sem_ruptura_mantem_so_produtos_com_estoque_confirmado(cliente_api, conexoes):
    dados, meta = gerar()
    carregar(conexoes, dados, meta)
    cliente = cliente_com_ruptura_e_estoque(dados)
    produtos = produtos_por_sku(dados)
    com_estoque = [linha for linha in sugestoes_do(dados, cliente) if produtos[linha[1]][5] is False]
    corpo = cliente_api.get(f"/cliente/{cliente}/produtos-sugeridos?sem_ruptura=true").json()
    assert corpo["total"] == len(corpo["itens"]) == len(com_estoque) < len(sugestoes_do(dados, cliente))
    assert [i["sku"] for i in corpo["itens"]] == [linha[1] for linha in com_estoque]
    assert all(i["ruptura"] is False for i in corpo["itens"])


def test_produto_sem_informacao_de_estoque_sai_do_sem_ruptura(cliente_api, conexoes):
    dados, meta = gerar()
    cliente = cliente_com_ruptura_e_estoque(dados)
    sku = sugestoes_do(dados, cliente)[0][1]
    dados["produtos"] = [(*p[:4], None, None, None) if p[0] == sku else p for p in dados["produtos"]]
    carregar(conexoes, dados, meta)
    todos = cliente_api.get(f"/cliente/{cliente}/produtos-sugeridos").json()
    confirmados = cliente_api.get(f"/cliente/{cliente}/produtos-sugeridos?sem_ruptura=true").json()
    assert sku in [i["sku"] for i in todos["itens"]] and sku not in [i["sku"] for i in confirmados["itens"]]


@pytest.mark.parametrize("consulta", ["limit=0", "limit=101", "limit=abc", "sem_ruptura=talvez"])
def test_parametros_invalidos_dao_422(cliente_api, consulta):
    assert cliente_api.get(f"/cliente/1/produtos-sugeridos?{consulta}").status_code == 422


def test_limit_100_e_aceito(cliente_api, conexoes):
    dados, meta = gerar()
    carregar(conexoes, dados, meta)
    assert cliente_api.get(f"/cliente/{dados['clientes'][0][0]}/produtos-sugeridos?limit=100").status_code == 200


def test_cliente_sem_sugestoes_da_lista_vazia(cliente_api, conexoes):
    dados, meta = gerar()
    cliente = dados["clientes"][0][0]
    dados["sugestoes_cliente"] = [linha for linha in dados["sugestoes_cliente"] if linha[0] != cliente]
    carregar(conexoes, dados, meta)
    corpo = cliente_api.get(f"/cliente/{cliente}/produtos-sugeridos").json()
    assert corpo["total"] == 0 and corpo["itens"] == []


def test_cliente_inexistente_da_404_e_sem_carga_da_503(cliente_api, conexoes):
    sem_carga = cliente_api.get("/cliente/1/produtos-sugeridos")
    assert sem_carga.status_code == 503 and sem_carga.json() == {"detalhe": "nenhuma carga concluída"}
    carregar(conexoes, *gerar())
    inexistente = cliente_api.get("/cliente/1/produtos-sugeridos")
    assert inexistente.status_code == 404 and inexistente.json() == {"detalhe": "cliente não encontrado"}

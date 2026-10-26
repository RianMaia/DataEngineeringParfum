"""O contrato dos campos das respostas e do parâmetro sku, e um ramo de lógica sem teste."""

import pytest
from test_carga.dados_falsos import FonteFalsa, gerar

from app.main import app
from carga.executar import executar

CAMPOS = {
    "RespostaFila": {"vendedor", "total", "itens", "meta"},
    "RespostaContexto": {"cliente", "marcas", "meta"},
    "RespostaSugestoes": {"cliente_id", "total", "itens", "meta"},
    "RespostaDisponibilidade": {"produto", "estoque", "meta"},
    "ItemFila": {"posicao", "cliente_id", "razao_social", "cidade", "uf", "score", "faixa", "ticket_medio", "motivo"},
    "ProdutoSugerido": {"ordem", "sku", "descricao", "marca", "descontinuado", "saldo", "ruptura", "ultima_compra"},
    "Estoque": {"saldo", "ruptura", "data_snapshot", "defasado"},
    "Meta": {"carga_id", "concluida_em", "data_referencia_score", "snapshot_estoque_global"},
}


@pytest.mark.parametrize("modelo", sorted(CAMPOS))
def test_os_campos_de_cada_resposta_sao_os_documentados(modelo):
    propriedades = set(app.openapi()["components"]["schemas"][modelo]["properties"])
    assert CAMPOS[modelo] <= propriedades, f"{modelo}: faltam {sorted(CAMPOS[modelo] - propriedades)}"


def test_o_sku_e_obrigatorio_e_tem_de_1_a_64_caracteres():
    parametros = {p["name"]: p for p in app.openapi()["paths"]["/produto/{sku}/disponibilidade"]["get"]["parameters"]}
    sku = parametros["sku"]
    assert sku["required"] is True and sku["schema"]["minLength"] == 1 and sku["schema"]["maxLength"] == 64


def test_sem_snapshot_global_o_defasado_fica_vazio(cliente_api, conexoes):
    dados, meta = gerar()
    meta = {**meta, "snapshot_estoque_global": None}
    assert executar(FonteFalsa(dados, meta), *conexoes) == 0
    corpo = cliente_api.get(f"/produto/{dados['produtos'][0][0]}/disponibilidade").json()
    assert corpo["meta"]["snapshot_estoque_global"] is None and corpo["estoque"]["defasado"] is None

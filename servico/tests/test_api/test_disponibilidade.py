from test_carga.dados_falsos import FonteFalsa, gerar

from carga.executar import executar


def carregar(conexoes, dados, meta):
    assert executar(FonteFalsa(dados, meta), *conexoes) == 0


def com_snapshot(dados, sku, snapshot):
    return [(*p[:6], snapshot) if p[0] == sku else p for p in dados["produtos"]]


def test_produto_com_estoque_atual_nao_esta_defasado(cliente_api, conexoes):
    dados, meta = gerar()
    sku = next(p[0] for p in dados["produtos"] if p[4] and p[4] > 0)
    dados["produtos"] = com_snapshot(dados, sku, meta["snapshot_estoque_global"])
    carregar(conexoes, dados, meta)
    corpo = cliente_api.get(f"/produto/{sku}/disponibilidade").json()
    assert corpo["produto"] == {"sku": sku, "descricao": "descricao", "marca": "marca", "descontinuado": False}
    assert corpo["estoque"]["ruptura"] is False and corpo["estoque"]["saldo"] > 0
    assert corpo["estoque"]["data_snapshot"] == "2026-08-30" and corpo["estoque"]["defasado"] is False
    assert corpo["meta"]["carga_id"] == 1 and corpo["meta"]["snapshot_estoque_global"] == "2026-08-30"


def test_produto_com_snapshot_antigo_vem_marcado_como_defasado(cliente_api, conexoes):
    dados, meta = gerar()  # no gerador, todos os produtos têm snapshot 2026-08-01 e o global é 2026-08-30
    carregar(conexoes, dados, meta)
    corpo = cliente_api.get(f"/produto/{dados['produtos'][0][0]}/disponibilidade").json()
    assert corpo["estoque"]["data_snapshot"] == "2026-08-01" and corpo["estoque"]["defasado"] is True


def test_saldo_zero_e_ruptura(cliente_api, conexoes):
    dados, meta = gerar()
    sku = next(p[0] for p in dados["produtos"] if p[4] == 0)
    carregar(conexoes, dados, meta)
    estoque = cliente_api.get(f"/produto/{sku}/disponibilidade").json()["estoque"]
    assert estoque["saldo"] == 0 and estoque["ruptura"] is True


def test_produto_sem_informacao_de_estoque_vem_com_campos_vazios(cliente_api, conexoes):
    dados, meta = gerar()
    sku = dados["produtos"][0][0]
    dados["produtos"] = [(*p[:4], None, None, None) if p[0] == sku else p for p in dados["produtos"]]
    carregar(conexoes, dados, meta)
    estoque = cliente_api.get(f"/produto/{sku}/disponibilidade").json()["estoque"]
    assert estoque == {"saldo": None, "ruptura": None, "data_snapshot": None, "defasado": None}


def test_produto_inexistente_da_404(cliente_api, conexoes):
    carregar(conexoes, *gerar())
    resposta = cliente_api.get("/produto/NAO_EXISTE/disponibilidade")
    assert resposta.status_code == 404 and resposta.json() == {"detalhe": "produto não encontrado"}


def test_codigo_longo_demais_da_422(cliente_api):
    assert cliente_api.get(f"/produto/{'X' * 65}/disponibilidade").status_code == 422


def test_sem_nenhuma_carga_concluida_da_503(cliente_api):
    resposta = cliente_api.get("/produto/QUALQUER/disponibilidade")
    assert resposta.status_code == 503 and resposta.json() == {"detalhe": "nenhuma carga concluída"}

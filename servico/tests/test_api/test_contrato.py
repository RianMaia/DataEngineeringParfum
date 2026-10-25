"""O contrato público da API: quais rotas existem e o que cada uma aceita. Quebrar isto sem querer é um bug."""

from app.main import app

ROTAS_PUBLICAS = {
    ("/saude", "get"),
    ("/pronto", "get"),
    ("/fila/{vendedor_id}", "get"),
    ("/cliente/{cliente_id}/contexto", "get"),
    ("/cliente/{cliente_id}/produtos-sugeridos", "get"),
    ("/produto/{sku}/disponibilidade", "get"),
}
ROTAS_DE_DADOS = [caminho for caminho, _ in ROTAS_PUBLICAS if caminho not in ("/saude", "/pronto")]


def esquema():
    return app.openapi()


def parametros(caminho):
    return {p["name"]: p for p in esquema()["paths"][caminho]["get"]["parameters"]}


def test_as_rotas_publicas_sao_exatamente_estas():
    encontradas = {(caminho, metodo) for caminho, operacoes in esquema()["paths"].items() for metodo in operacoes}
    assert encontradas == ROTAS_PUBLICAS


def test_toda_rota_de_dados_responde_com_o_meta_da_carga():
    for caminho in ROTAS_DE_DADOS:
        referencia = esquema()["paths"][caminho]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
        nome = referencia["$ref"].rsplit("/", 1)[1]
        assert "meta" in esquema()["components"]["schemas"][nome]["properties"], caminho


def test_toda_rota_de_dados_documenta_404_e_503():
    for caminho in ROTAS_DE_DADOS:
        respostas = esquema()["paths"][caminho]["get"]["responses"]
        assert "503" in respostas, caminho
        assert "404" in respostas, caminho


def test_produtos_sugeridos_aceita_limit_de_1_a_100_com_padrao_20_e_sem_ruptura():
    p = parametros("/cliente/{cliente_id}/produtos-sugeridos")
    limit = p["limit"]["schema"]
    assert (limit["type"], limit["minimum"], limit["maximum"], limit["default"]) == ("integer", 1, 100, 20)
    assert p["limit"]["required"] is False
    assert p["sem_ruptura"]["schema"]["default"] is False and p["sem_ruptura"]["required"] is False


def test_identificadores_de_caminho_sao_obrigatorios_e_inteiros_a_partir_de_1():
    for caminho, nome in (("/fila/{vendedor_id}", "vendedor_id"), ("/cliente/{cliente_id}/contexto", "cliente_id")):
        p = parametros(caminho)[nome]
        assert p["required"] is True and p["schema"]["type"] == "integer" and p["schema"]["minimum"] == 1

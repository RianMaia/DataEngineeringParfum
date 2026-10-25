from carga.esquema import ORDEM_INSERCAO
from carga.validacao import validar

from .dados_falsos import gerar

ISCAS = ("SECRETO", "SECRETA", "987654")


def sem_iscas(problemas):
    return not any(isca in texto for texto in problemas for isca in ISCAS)


def test_dados_consistentes_passam():
    dados, _ = gerar()
    assert validar(dados, {}) == []


def test_primeira_carga_com_dados_passa_mesmo_sem_carga_anterior():
    dados, _ = gerar()
    assert validar(dados, {nome: 0 for nome in ORDEM_INSERCAO}) == []


def test_tabela_vazia_e_recusada():
    dados, _ = gerar()
    dados["clientes"] = []
    problemas = validar(dados, {})
    assert "clientes: extração vazia (0 linhas)" in problemas


def test_menos_de_50_por_cento_da_carga_anterior_e_recusado():
    dados, _ = gerar(n_clientes=20, n_fila=10)
    problemas = validar(dados, {"clientes": 50})
    assert any(p.startswith("clientes: 20 linhas, menos de 50% das 50") for p in problemas)


def test_exatamente_a_metade_ou_mais_passa():
    dados, _ = gerar(n_clientes=25, n_fila=10)
    problemas = validar(dados, {"clientes": 50})
    assert not any(p.startswith("clientes:") for p in problemas)


def test_limite_e_ajustavel():
    dados, _ = gerar(n_clientes=40, n_fila=10)
    assert any(p.startswith("clientes:") for p in validar(dados, {"clientes": 50}, minimo_relativo=0.9))
    assert not any(p.startswith("clientes:") for p in validar(dados, {"clientes": 50}, minimo_relativo=0.5))


def test_chave_repetida_e_contada_sem_mostrar_valores():
    dados, _ = gerar()
    dados["clientes"] = dados["clientes"] + [dados["clientes"][0]]
    problemas = validar(dados, {})
    assert "clientes: 1 linhas repetem a chave (cliente_id)" in problemas
    assert sem_iscas(problemas)


def test_unicidades_compostas_da_fila_sao_conferidas():
    dados, _ = gerar()
    repetida = list(dados["fila_semanal"][0])
    repetida[0] = dados["clientes"][-1][0]  # outro cliente, mesma (vendedor_id, posicao)
    dados["fila_semanal"] = dados["fila_semanal"] + [tuple(repetida)]
    problemas = validar(dados, {})
    assert any("fila_semanal" in p and "vendedor_nome, ordem_fila" in p for p in problemas)
    assert any("fila_semanal" in p and "vendedor_id, posicao" in p for p in problemas)
    assert sem_iscas(problemas)


def test_filho_sem_pai_e_contado_sem_mostrar_valores():
    dados, _ = gerar()
    fila = list(dados["fila_semanal"][0])
    fila[0] = 555555555  # cliente que não existe em "clientes"
    dados["fila_semanal"] = [tuple(fila)] + dados["fila_semanal"][1:]
    suges = list(dados["sugestoes_cliente"][0])
    suges[1] = "SKU_INEXISTENTE_SECRETO"
    dados["sugestoes_cliente"] = [tuple(suges)] + dados["sugestoes_cliente"][1:]
    problemas = validar(dados, {})
    assert any(p.startswith("fila_semanal: 1 linhas sem correspondente em clientes") for p in problemas)
    assert any(p.startswith("sugestoes_cliente: 1 linhas sem correspondente em produtos") for p in problemas)
    assert sem_iscas(problemas) and not any("555555555" in p for p in problemas)


def test_vendedor_com_id_e_nome_que_nao_batem_e_detectado():
    dados, _ = gerar()
    fila = list(dados["fila_semanal"][0])
    fila[2] = "NOME_QUE_NAO_BATE_SECRETO"
    dados["fila_semanal"] = [tuple(fila)] + dados["fila_semanal"][1:]
    problemas = validar(dados, {})
    assert any("sem correspondente em vendedores (vendedor_id, vendedor_nome)" in p for p in problemas)
    assert sem_iscas(problemas)

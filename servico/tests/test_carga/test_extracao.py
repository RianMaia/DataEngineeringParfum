import re
import webbrowser
from pathlib import Path

import pytest

from carga import extracao
from carga.esquema import COLUNAS, ORDEM_INSERCAO
from carga.extracao import CONSULTAS, ErroDeExtracao, FonteDatabricks, extrair_tudo

from .dados_falsos import FonteFalsa, gerar


class CursorFalso:
    def __init__(self, linhas, nomes):
        self.linhas, self.pos, self.description = linhas, 0, [(n, "tipo") for n in nomes]
        self.executados, self.pedidos = [], []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, consulta):
        self.executados.append(consulta)

    def fetchmany(self, n):
        self.pedidos.append(n)
        lote = self.linhas[self.pos : self.pos + n]
        self.pos += n
        return lote


class ConexaoFalsa:
    def __init__(self, linhas, nomes):
        self.linhas, self.nomes, self.cursores, self.fechada = linhas, nomes, [], False

    def cursor(self):
        cursor = CursorFalso(self.linhas, self.nomes)
        self.cursores.append(cursor)
        return cursor

    def close(self):
        self.fechada = True


def test_le_em_lotes_de_20000_e_devolve_tuplas():
    linhas = [[i] for i in range(45_000)]  # listas, como um Row faria: viram tuplas
    conexao = ConexaoFalsa(linhas, COLUNAS["clientes"])
    colunas, lidas = FonteDatabricks(conexao).ler("clientes")
    cursor = conexao.cursores[0]
    assert colunas == COLUNAS["clientes"] and len(lidas) == 45_000
    assert all(isinstance(linha, tuple) for linha in lidas)
    assert cursor.pedidos == [20_000, 20_000, 20_000, 20_000]  # 3 lotes com dados e 1 vazio


def test_executa_exatamente_a_consulta_fixa_do_nome():
    for nome in CONSULTAS:
        conexao = ConexaoFalsa([], COLUNAS.get(nome, (nome,)))
        FonteDatabricks(conexao).ler(nome)
        assert conexao.cursores[0].executados == [CONSULTAS[nome]]


def test_nome_desconhecido_da_erro_e_nao_executa_nada():
    conexao = ConexaoFalsa([], ())
    with pytest.raises(KeyError):
        FonteDatabricks(conexao).ler("select 1")
    assert conexao.cursores == []


def test_extrair_tudo_devolve_tabelas_e_datas():
    dados, meta = gerar()
    lidos, meta_lida = extrair_tudo(FonteFalsa(dados, meta))
    assert lidos == dados and meta_lida == meta


def test_extrair_tudo_le_na_ordem_dos_pais_primeiro():
    dados, meta = gerar()
    fonte = FonteFalsa(dados, meta)
    extrair_tudo(fonte)
    assert fonte.lidos == list(ORDEM_INSERCAO) + ["data_referencia_score", "snapshot_estoque_global"]


def test_colunas_diferentes_das_esperadas_sao_recusadas_so_com_nomes():
    class FonteComColunaErrada(FonteFalsa):
        def ler(self, nome):
            colunas, linhas = super().ler(nome)
            return (colunas[:-1] + ("coluna_nova",), linhas) if nome == "clientes" else (colunas, linhas)

    dados, meta = gerar()
    with pytest.raises(ErroDeExtracao) as erro:
        extrair_tudo(FonteComColunaErrada(dados, meta))
    assert "clientes" in str(erro.value) and "coluna_nova" in str(erro.value)
    assert "987654" not in str(erro.value)


def test_data_de_contexto_sem_linhas_vira_none():
    class FonteSemDatas(FonteFalsa):
        def ler(self, nome):
            return ((nome,), []) if nome in extracao.NOMES_META else super().ler(nome)

    dados, meta = gerar()
    _, meta_lida = extrair_tudo(FonteSemDatas(dados, meta))
    assert meta_lida == {"data_referencia_score": None, "snapshot_estoque_global": None}


def test_ha_8_consultas_fixas_e_todas_sao_de_leitura():
    assert len(CONSULTAS) == 8 and set(CONSULTAS) == set(ORDEM_INSERCAO) | set(extracao.NOMES_META)
    for nome, consulta in CONSULTAS.items():
        texto = " ".join(consulta.split()).upper()
        assert texto.startswith(("SELECT", "WITH")), nome
        assert ";" not in consulta, nome
        assert not re.search(r"\b(INSERT|UPDATE|DELETE|MERGE|CREATE|DROP|ALTER|TRUNCATE|GRANT|COPY)\b", texto), nome


def test_codigo_de_extracao_nao_le_argumentos_nem_ambiente_nem_arquivos():
    fonte = Path(extracao.__file__).read_text(encoding="utf-8")
    for proibido in (
        "sys.argv",
        "os.environ",
        "getenv",
        "input(",
        "open(",
        "eval(",
        "exec(",
        "subprocess",
        "import os",
    ):
        assert proibido not in fonte, proibido


def test_abrir_databricks_usa_o_perfil_sem_token_e_bloqueia_o_navegador(monkeypatch):
    import databricks.sdk.core as nucleo
    import databricks.sql as ds

    for nome in ("open", "open_new", "open_new_tab", "get"):
        monkeypatch.setattr(webbrowser, nome, getattr(webbrowser, nome))  # para restaurar no fim do teste
    chamadas = {}

    class ConfigFalsa:
        host = "https://exemplo.invalid/"

        def __init__(self, **opcoes):
            chamadas["config"] = opcoes

        def authenticate(self):
            return {"Authorization": "Bearer TOKEN_FALSO"}

    def conectar_falso(**opcoes):
        chamadas["connect"] = opcoes
        return ConexaoFalsa([], ())

    monkeypatch.setattr(nucleo, "Config", ConfigFalsa)
    monkeypatch.setattr(ds, "connect", conectar_falso)
    fonte = extracao.abrir_databricks()
    assert isinstance(fonte, FonteDatabricks)
    assert chamadas["config"] == {"profile": "DataJourney"}
    opcoes = chamadas["connect"]
    assert opcoes["server_hostname"] == "exemplo.invalid"
    assert opcoes["http_path"] == "/sql/1.0/warehouses/107dd2f1b9c84d4d"
    assert set(opcoes) == {"server_hostname", "http_path", "credentials_provider"}  # sem access_token
    assert callable(opcoes["credentials_provider"]()) is True  # devolve a função que gera os cabeçalhos
    with pytest.raises(RuntimeError, match="navegador"):
        webbrowser.open_new("http://exemplo.invalid")

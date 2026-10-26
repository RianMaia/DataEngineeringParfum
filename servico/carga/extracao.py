"""Leitura dos dados no Databricks. SOMENTE SELECT, com consultas fixas escritas neste arquivo.

Nenhuma consulta é montada com texto vindo de fora. O resultado vem em lotes e vira uma lista de tuplas.
Autentica com o profile do Databricks CLI (sem token em arquivo), como no spike C2.
"""

import webbrowser
from types import MappingProxyType

from carga.esquema import COLUNAS, ORDEM_INSERCAO

PERFIL = "DataJourney"
ID_WAREHOUSE = "107dd2f1b9c84d4d"
TAMANHO_LOTE = 20_000

# Cada consulta devolve as colunas de COLUNAS[nome], na mesma ordem. O MappingProxyType impede alterá-las.
CONSULTAS = MappingProxyType(
    {
        "vendedores": """
            SELECT vendedor_id, nome, regiao, uf, data_admissao, data_desligamento, meta_mensal, ativo
            FROM lakehouse_rotaperfume.gold.dim_vendedor
        """,
        "clientes": """
            SELECT cliente_id
            FROM lakehouse_rotaperfume.gold.dim_cliente
        """,
        # Estoque mais recente por SKU: a mesma regra que as funções do pipeline usam.
        "produtos": """
            WITH estoque_recente AS (
                SELECT sku, saldo, ruptura, data_snapshot
                FROM (
                    SELECT sku, saldo, ruptura, data_snapshot,
                           ROW_NUMBER() OVER (PARTITION BY sku ORDER BY data_snapshot DESC) AS snapshot
                    FROM lakehouse_rotaperfume.silver.estoque
                )
                WHERE snapshot = 1
            )
            SELECT p.sku, p.descricao, p.marca, p.descontinuado, e.saldo, e.ruptura, e.data_snapshot
            FROM lakehouse_rotaperfume.gold.dim_produto p
            LEFT JOIN estoque_recente e ON e.sku = p.sku
        """,
        # vendedor_id vem da carteira vigente (a mesma regra de 13-fila.sql).
        # posicao conta 1, 2, 3... por vendedor_id.
        "fila_semanal": """
            WITH carteira_vigente AS (
                SELECT cliente_id, vendedor_id
                FROM (
                    SELECT cliente_id, vendedor_id,
                           ROW_NUMBER() OVER (
                               PARTITION BY cliente_id ORDER BY data_inicio DESC, carteira_id DESC
                           ) AS atribuicao
                    FROM lakehouse_rotaperfume.silver.carteira
                    WHERE vigente = TRUE AND orfao_vendedor_desligado = FALSE
                )
                WHERE atribuicao = 1
            )
            SELECT f.cliente_id, c.vendedor_id, f.vendedor AS vendedor_nome, f.ordem AS ordem_fila,
                   ROW_NUMBER() OVER (PARTITION BY c.vendedor_id ORDER BY f.ordem, f.cliente_id) AS posicao,
                   f.razao_social, f.cidade, f.uf, f.score, f.faixa, f.ticket_medio, f.motivo, f.sugestao
            FROM lakehouse_rotaperfume.gold.fila_semanal f
            INNER JOIN carteira_vigente c ON c.cliente_id = f.cliente_id
        """,
        "contexto_cliente": """
            SELECT c.cliente_id, x.ranking_marca, x.razao_social, x.data_primeira_compra, x.data_ultima_compra,
                   x.pedidos, x.ticket_medio, x.marca_preferida, x.receita_marca
            FROM lakehouse_rotaperfume.gold.dim_cliente c,
                 LATERAL lakehouse_rotaperfume.gold.contexto_cliente(c.cliente_id) x
        """,
        # A função não devolve a coluna "ordem": ela é calculada com a MESMA ordenação
        # que a função usa por dentro.
        "sugestoes_cliente": """
            SELECT c.cliente_id, s.sku,
                   ROW_NUMBER() OVER (
                       PARTITION BY c.cliente_id ORDER BY s.unidades_compradas DESC, s.ultima_compra DESC, s.sku
                   ) AS ordem,
                   s.unidades_compradas, s.ultima_compra
            FROM lakehouse_rotaperfume.gold.dim_cliente c,
                 LATERAL lakehouse_rotaperfume.gold.sugerir_produtos(c.cliente_id) s
        """,
        "data_referencia_score": """
            SELECT MAX(_referencia) AS data_referencia_score
            FROM lakehouse_rotaperfume.gold.score_propensao
        """,
        "snapshot_estoque_global": """
            SELECT MAX(data_snapshot) AS snapshot_estoque_global
            FROM lakehouse_rotaperfume.silver.estoque
        """,
    }
)
NOMES_META = ("data_referencia_score", "snapshot_estoque_global")


class ErroDeExtracao(Exception):
    """Falha ao ler o Databricks. A mensagem só traz nomes de tabelas e de colunas, nunca valores."""


def _bloquear_navegador():
    """Se alguma biblioteca tentar abrir o navegador para login interativo, falha em vez de abrir."""

    def recusar(*argumentos, **opcoes):
        raise RuntimeError("tentativa de abrir o navegador para login interativo: bloqueada")

    for nome in ("open", "open_new", "open_new_tab", "get"):
        setattr(webbrowser, nome, recusar)


def abrir_databricks():
    """Conecta com o profile do Databricks CLI e devolve uma FonteDatabricks (importa as bibliotecas só aqui)."""
    from databricks import sql
    from databricks.sdk.core import Config

    _bloquear_navegador()
    cfg = Config(profile=PERFIL)
    conexao = sql.connect(
        server_hostname=cfg.host.replace("https://", "").rstrip("/"),
        http_path=f"/sql/1.0/warehouses/{ID_WAREHOUSE}",
        credentials_provider=lambda: cfg.authenticate,
    )
    return FonteDatabricks(conexao)


class FonteDatabricks:
    """Lê as consultas fixas de CONSULTAS por nome. Não aceita SQL de fora."""

    def __init__(self, conexao):
        self._conexao = conexao

    def ler(self, nome):
        """Devolve (nomes das colunas, lista de tuplas). KeyError se o nome não for uma das consultas fixas."""
        consulta = CONSULTAS[nome]
        with self._conexao.cursor() as cursor:
            cursor.execute(consulta)
            colunas = tuple(descricao[0] for descricao in cursor.description)
            linhas = []
            while True:
                lote = cursor.fetchmany(TAMANHO_LOTE)
                if not lote:
                    break
                linhas.extend(tuple(linha) for linha in lote)
        return colunas, linhas

    def fechar(self):
        self._conexao.close()


def extrair_tudo(fonte):
    """Lê as 6 tabelas e as 2 datas de contexto. Devolve (dados, meta)."""
    dados = {}
    for nome in ORDEM_INSERCAO:
        colunas, linhas = fonte.ler(nome)
        if colunas != COLUNAS[nome]:
            raise ErroDeExtracao(f"{nome}: colunas recebidas {colunas} diferem das esperadas {COLUNAS[nome]}")
        dados[nome] = linhas
    meta = {}
    for nome in NOMES_META:
        _, linhas = fonte.ler(nome)
        meta[nome] = linhas[0][0] if linhas else None
    return dados, meta

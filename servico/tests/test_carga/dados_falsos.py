"""Dados INVENTADOS para os testes, com valores-isca (…_SECRETO_…) para provar que nada vaza."""

import datetime
import random
import time
from decimal import Decimal

from psycopg import sql

from carga.esquema import COLUNAS, ORDEM_INSERCAO

DIA = datetime.date(2026, 8, 1)


def gerar(n_clientes=50, n_skus=20, n_vendedores=6, n_fila=20, semente=1, max_sugestoes=8):
    """Devolve (dados, meta) consistentes com o esquema: chaves únicas e chaves estrangeiras fechadas."""
    sorteio = random.Random(semente)
    vendedores = []
    for i in range(1, n_vendedores + 1):
        # Os dois últimos vendedores são homônimos (mesmo nome, ids diferentes), como acontece nos dados reais.
        nome = f"VENDEDOR_SECRETO_{i if i != n_vendedores else i - 1}"
        vendedores.append((i, nome, "Regiao", "CE", DIA, None, Decimal("1234.50"), True))
    ids_clientes = list(range(987654000, 987654000 + n_clientes))
    clientes = [(c,) for c in ids_clientes]
    produtos = []
    for s in range(n_skus):
        saldo = sorteio.choice([0, 3, 10, 50])
        produtos.append((f"SKU_SECRETO_{s:04d}", "descricao", "marca", False, saldo, saldo == 0, DIA))
    fila, por_nome, por_id = [], {}, {}
    for k, cliente in enumerate(ids_clientes[:n_fila]):
        vendedor = vendedores[k % n_vendedores]
        por_nome[vendedor[1]] = por_nome.get(vendedor[1], 0) + 1
        por_id[vendedor[0]] = por_id.get(vendedor[0], 0) + 1
        fila.append(
            (
                cliente,
                vendedor[0],
                vendedor[1],
                por_nome[vendedor[1]],
                por_id[vendedor[0]],
                f"RAZAO_SECRETA_{cliente}",
                "Fortaleza",
                "CE",
                round(sorteio.random(), 6),
                "alta",
                100.5,
                "motivo",
                "sugestao",
            )
        )
    contexto = []
    for cliente in ids_clientes:
        for ranking in range(1, sorteio.randint(1, 3) + 1):
            contexto.append((cliente, ranking, f"RAZAO_SECRETA_{cliente}", DIA, DIA, 5, 99.9, "marca", 10.25 * ranking))
    sugestoes = []
    for cliente in ids_clientes:
        escolhidos = sorteio.sample(range(n_skus), min(n_skus, sorteio.randint(0, max_sugestoes)))
        for ordem, s in enumerate(escolhidos, start=1):
            sugestoes.append((cliente, f"SKU_SECRETO_{s:04d}", ordem, sorteio.randint(1, 500), DIA))
    dados = {
        "vendedores": vendedores,
        "clientes": clientes,
        "produtos": produtos,
        "fila_semanal": fila,
        "contexto_cliente": contexto,
        "sugestoes_cliente": sugestoes,
    }
    meta = {"data_referencia_score": datetime.date(2026, 8, 31), "snapshot_estoque_global": datetime.date(2026, 8, 30)}
    return dados, meta


class FonteFalsa:
    """Faz o papel do Databricks: devolve as tabelas prontas, sem rede."""

    def __init__(self, dados, meta, espera=0.0):
        self.dados, self.meta, self.espera = dados, meta, espera
        self.lidos, self.fechada = [], False

    def ler(self, nome):
        self.lidos.append(nome)
        if self.espera:
            time.sleep(self.espera)
        if nome in COLUNAS:
            return COLUNAS[nome], list(self.dados[nome])
        return (nome,), [(self.meta[nome],)]

    def fechar(self):
        self.fechada = True


def impressao(conn):
    """Uma 'impressão digital' do conteúdo de cada tabela, para comparar antes e depois."""
    return tuple(
        conn.execute(
            sql.SQL("SELECT md5(coalesce(string_agg(t::text, '|' ORDER BY t::text), '')) FROM {} t").format(
                sql.Identifier(nome)
            )
        ).fetchone()[0]
        for nome in ORDEM_INSERCAO
    )


def contagens(conn):
    return {
        nome: conn.execute(sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(nome))).fetchone()[0]
        for nome in ORDEM_INSERCAO
    }


def log(conn):
    return conn.execute(
        "SELECT carga_id, status, erro, contagens, data_referencia_score, snapshot_estoque_global, concluida_em"
        " FROM carga_log ORDER BY carga_id"
    ).fetchall()

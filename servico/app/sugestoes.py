"""Rota dos produtos sugeridos para um cliente."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from psycopg import Connection
from pydantic import BaseModel

from app.exigencias import exigir_cliente, exigir_meta
from app.leitura import obter_leitura_consistente
from app.modelos import Meta

roteador = APIRouter()

# "sem_ruptura" mantém só os produtos com estoque CONFIRMADO: quem não tem informação de estoque também sai.
SQL_ORIGEM = (
    " FROM sugestoes_cliente s JOIN produtos p ON p.sku = s.sku"
    " WHERE s.cliente_id = %s AND (NOT %s OR p.ruptura IS FALSE)"
)
SQL_TOTAL = "SELECT count(*)" + SQL_ORIGEM
SQL_ITENS = (
    "SELECT s.ordem, s.sku, p.descricao, p.marca, p.descontinuado, p.saldo, p.ruptura, p.data_snapshot,"
    " s.unidades_compradas, s.ultima_compra" + SQL_ORIGEM + " ORDER BY s.ordem LIMIT %s"
)
CAMPOS_ITEM = (
    "ordem",
    "sku",
    "descricao",
    "marca",
    "descontinuado",
    "saldo",
    "ruptura",
    "data_snapshot",
    "unidades_compradas",
    "ultima_compra",
)


class ProdutoSugerido(BaseModel):
    ordem: int
    sku: str
    descricao: str | None
    marca: str | None
    descontinuado: bool
    saldo: int | None
    ruptura: bool | None
    data_snapshot: date | None
    unidades_compradas: int | None
    ultima_compra: date


class RespostaSugestoes(BaseModel):
    cliente_id: int
    total: int
    itens: list[ProdutoSugerido]
    meta: Meta


@roteador.get(
    "/cliente/{cliente_id}/produtos-sugeridos",
    response_model=RespostaSugestoes,
    summary="Produtos sugeridos para um cliente, do mais para o menos recomendado",
    responses={404: {"description": "Cliente não encontrado"}, 503: {"description": "Banco indisponível"}},
)
def produtos_sugeridos(
    cliente_id: Annotated[int, Path(ge=1, description="Identificador do cliente")],
    conexao: Annotated[Connection, Depends(obter_leitura_consistente)],
    limit: Annotated[int, Query(ge=1, le=100, description="Quantos produtos devolver")] = 20,
    sem_ruptura: Annotated[bool, Query(description="Só produtos com estoque confirmado")] = False,
):
    meta = exigir_meta(conexao)
    exigir_cliente(conexao, cliente_id)
    total = conexao.execute(SQL_TOTAL, (cliente_id, sem_ruptura)).fetchone()[0]
    linhas = conexao.execute(SQL_ITENS, (cliente_id, sem_ruptura, limit)).fetchall()
    return {
        "cliente_id": cliente_id,
        "total": total,
        "itens": [dict(zip(CAMPOS_ITEM, linha, strict=True)) for linha in linhas],
        "meta": meta,
    }

"""Rota da disponibilidade (estoque) de um produto."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path
from psycopg import Connection
from pydantic import BaseModel

from app.exigencias import exigir_meta
from app.leitura import obter_leitura_consistente
from app.modelos import Meta

roteador = APIRouter()

SQL_PRODUTO = "SELECT sku, descricao, marca, descontinuado, saldo, ruptura, data_snapshot FROM produtos WHERE sku = %s"


class Produto(BaseModel):
    sku: str
    descricao: str | None
    marca: str | None
    descontinuado: bool


class Estoque(BaseModel):
    saldo: int | None
    ruptura: bool | None
    data_snapshot: date | None
    defasado: bool | None  # True se o snapshot deste produto é anterior ao snapshot global mais recente


class RespostaDisponibilidade(BaseModel):
    produto: Produto
    estoque: Estoque
    meta: Meta


@roteador.get(
    "/produto/{sku}/disponibilidade",
    response_model=RespostaDisponibilidade,
    summary="Saldo e ruptura de um produto, no snapshot de estoque mais recente que o produto tem",
    responses={404: {"description": "Produto não encontrado"}, 503: {"description": "Banco indisponível"}},
)
def disponibilidade_do_produto(
    sku: Annotated[str, Path(min_length=1, max_length=64, description="Código do produto")],
    conexao: Annotated[Connection, Depends(obter_leitura_consistente)],
):
    meta = exigir_meta(conexao)
    linha = conexao.execute(SQL_PRODUTO, (sku,)).fetchone()
    if linha is None:
        raise HTTPException(status_code=404, detail="produto não encontrado")
    codigo, descricao, marca, descontinuado, saldo, ruptura, data_snapshot = linha
    global_ = meta["snapshot_estoque_global"]
    defasado = None if data_snapshot is None or global_ is None else data_snapshot < global_
    return {
        "produto": {"sku": codigo, "descricao": descricao, "marca": marca, "descontinuado": descontinuado},
        "estoque": {"saldo": saldo, "ruptura": ruptura, "data_snapshot": data_snapshot, "defasado": defasado},
        "meta": meta,
    }

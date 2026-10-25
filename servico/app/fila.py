"""Rota da fila semanal de um vendedor."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path
from psycopg import Connection
from pydantic import BaseModel

from app.banco import ler_meta
from app.leitura import obter_leitura_consistente
from app.modelos import Meta

roteador = APIRouter()

SQL_VENDEDOR = "SELECT vendedor_id, nome, regiao, uf, ativo FROM vendedores WHERE vendedor_id = %s"
CAMPOS_VENDEDOR = ("id", "nome", "regiao", "uf", "ativo")
SQL_FILA = (
    "SELECT posicao, cliente_id, razao_social, cidade, uf, score, faixa, ticket_medio, motivo, sugestao"
    " FROM fila_semanal WHERE vendedor_id = %s ORDER BY posicao"
)
CAMPOS_ITEM = (
    "posicao",
    "cliente_id",
    "razao_social",
    "cidade",
    "uf",
    "score",
    "faixa",
    "ticket_medio",
    "motivo",
    "sugestao",
)


class Vendedor(BaseModel):
    id: int
    nome: str
    regiao: str | None
    uf: str | None
    ativo: bool


class ItemFila(BaseModel):
    posicao: int
    cliente_id: int
    razao_social: str | None
    cidade: str | None
    uf: str | None
    score: float
    faixa: str | None
    ticket_medio: float | None
    motivo: str
    sugestao: str


class RespostaFila(BaseModel):
    vendedor: Vendedor
    total: int
    itens: list[ItemFila]
    meta: Meta


@roteador.get(
    "/fila/{vendedor_id}",
    response_model=RespostaFila,
    summary="Fila semanal de um vendedor, na ordem em que ele deve atender",
    responses={404: {"description": "Vendedor não encontrado"}, 503: {"description": "Banco indisponível"}},
)
def fila_do_vendedor(
    vendedor_id: Annotated[int, Path(ge=1, description="Identificador do vendedor")],
    conexao: Annotated[Connection, Depends(obter_leitura_consistente)],
):
    meta = ler_meta(conexao)
    if meta is None:
        raise HTTPException(status_code=503, detail="nenhuma carga concluída")
    vendedor = conexao.execute(SQL_VENDEDOR, (vendedor_id,)).fetchone()
    if vendedor is None:
        raise HTTPException(status_code=404, detail="vendedor não encontrado")
    itens = [dict(zip(CAMPOS_ITEM, linha, strict=True)) for linha in conexao.execute(SQL_FILA, (vendedor_id,))]
    return {
        "vendedor": dict(zip(CAMPOS_VENDEDOR, vendedor, strict=True)),
        "total": len(itens),
        "itens": itens,
        "meta": meta,
    }

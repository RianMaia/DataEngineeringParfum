"""Rota do contexto comercial de um cliente: resumo do histórico e marcas preferidas."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Path
from psycopg import Connection
from pydantic import BaseModel

from app.exigencias import exigir_cliente, exigir_meta
from app.leitura import obter_leitura_consistente
from app.modelos import Meta

roteador = APIRouter()

SQL_CONTEXTO = (
    "SELECT ranking_marca, marca_preferida, receita_marca,"
    " razao_social, data_primeira_compra, data_ultima_compra, pedidos, ticket_medio"
    " FROM contexto_cliente WHERE cliente_id = %s ORDER BY ranking_marca"
)
CAMPOS_RESUMO = ("razao_social", "data_primeira_compra", "data_ultima_compra", "pedidos", "ticket_medio")


class Cliente(BaseModel):
    id: int
    razao_social: str | None
    data_primeira_compra: date | None
    data_ultima_compra: date | None
    pedidos: int | None
    ticket_medio: float | None


class MarcaPreferida(BaseModel):
    ranking: int
    marca: str | None
    receita: float | None


class RespostaContexto(BaseModel):
    cliente: Cliente
    marcas: list[MarcaPreferida]
    meta: Meta


@roteador.get(
    "/cliente/{cliente_id}/contexto",
    response_model=RespostaContexto,
    summary="Resumo do histórico de compras e as marcas preferidas de um cliente",
    responses={404: {"description": "Cliente não encontrado"}, 503: {"description": "Banco indisponível"}},
)
def contexto_do_cliente(
    cliente_id: Annotated[int, Path(ge=1, description="Identificador do cliente")],
    conexao: Annotated[Connection, Depends(obter_leitura_consistente)],
):
    meta = exigir_meta(conexao)
    exigir_cliente(conexao, cliente_id)
    linhas = conexao.execute(SQL_CONTEXTO, (cliente_id,)).fetchall()
    # O resumo do cliente se repete em todas as linhas (uma por marca): basta ler a primeira.
    resumo = linhas[0][3:] if linhas else (None,) * len(CAMPOS_RESUMO)
    return {
        "cliente": {"id": cliente_id, **dict(zip(CAMPOS_RESUMO, resumo, strict=True))},
        "marcas": [{"ranking": ranking, "marca": marca, "receita": receita} for ranking, marca, receita, *_ in linhas],
        "meta": meta,
    }

"""Dependência para rotas que fazem mais de uma consulta."""

from typing import Annotated

from fastapi import Depends
from psycopg import Connection

from app.banco import obter_conexao


def obter_leitura_consistente(conexao: Annotated[Connection, Depends(obter_conexao)]):
    """Como obter_conexao, mas todas as consultas da requisição enxergam a MESMA fotografia do banco.

    Sem isso, uma carga que terminasse no meio da requisição faria a resposta misturar dados antigos e novos.
    """
    conexao.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")  # tem de ser o primeiro comando
    return conexao

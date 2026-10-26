"""Verificações que várias rotas repetem: existe carga? existe o cliente?"""

from fastapi import HTTPException
from psycopg import Connection

from app.banco import ler_meta


def exigir_meta(conexao: Connection):
    """Devolve o meta da última carga concluída, ou responde 503 se ainda não houve nenhuma."""
    meta = ler_meta(conexao)
    if meta is None:
        raise HTTPException(status_code=503, detail="nenhuma carga concluída")
    return meta


def exigir_cliente(conexao: Connection, cliente_id: int):
    """Responde 404 se o cliente não existe."""
    if conexao.execute("SELECT 1 FROM clientes WHERE cliente_id = %s", (cliente_id,)).fetchone() is None:
        raise HTTPException(status_code=404, detail="cliente não encontrado")

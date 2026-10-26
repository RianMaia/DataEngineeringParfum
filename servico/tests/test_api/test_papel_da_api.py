"""O papel parfum_api (sql/002_perfis.sql) consegue ler tudo o que a API consulta, e só ler."""

from pathlib import Path

import psycopg
import pytest

from app.banco import ler_meta
from app.contexto import SQL_CONTEXTO
from app.disponibilidade import SQL_PRODUTO
from app.fila import SQL_FILA, SQL_VENDEDOR
from app.sugestoes import SQL_ITENS, SQL_TOTAL

PERFIS = Path(__file__).resolve().parents[2] / "sql" / "002_perfis.sql"


@pytest.fixture
def conexao_do_papel(banco, servidor):
    """Uma conexão ao banco de teste já com o papel da API (o esquema de teste recebe o 002_perfis.sql)."""
    with psycopg.connect(dbname=banco, autocommit=True, **servidor) as dono:
        dono.execute(PERFIS.read_text(encoding="utf-8"))
        dono.execute("SET ROLE parfum_api")
        yield dono


def test_o_papel_le_tudo_o_que_a_api_consulta(conexao_do_papel):
    ler_meta(conexao_do_papel)
    conexao_do_papel.execute("SELECT 1 FROM clientes WHERE cliente_id = %s", (1,))
    for consulta, parametros in (
        (SQL_VENDEDOR, (1,)),
        (SQL_FILA, (1,)),
        (SQL_CONTEXTO, (1,)),
        (SQL_TOTAL, (1, False)),
        (SQL_ITENS, (1, False, 20)),
        (SQL_PRODUTO, ("SKU",)),
    ):
        conexao_do_papel.execute(consulta, parametros)  # uma tabela sem GRANT levantaria InsufficientPrivilege


@pytest.mark.parametrize(
    "comando",
    [
        "INSERT INTO clientes VALUES (1)",
        "UPDATE carga_log SET erro = 'x'",
        "DELETE FROM clientes",
        "TRUNCATE clientes",
        "CREATE TABLE intruso (a int)",
        "DROP TABLE clientes",
    ],
)
def test_o_papel_nao_escreve_nem_altera_o_esquema(conexao_do_papel, comando):
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        conexao_do_papel.execute(comando)

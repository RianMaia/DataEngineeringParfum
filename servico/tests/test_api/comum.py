"""Apoio comum aos testes das rotas cujo resultado depende da ordem das linhas."""

import pytest
from psycopg import sql


@pytest.fixture
def banco_sem_indices(conexoes, banco):
    """Desliga os índices no banco de teste: as linhas voltam na ordem física, e só o ORDER BY as ordena.

    Precisa vir ANTES de cliente_api nos argumentos do teste (o pool da API abre as conexões depois).
    """
    for opcao in ("enable_indexscan", "enable_bitmapscan", "enable_indexonlyscan"):
        conexoes[0].execute(
            sql.SQL("ALTER DATABASE {} SET {} = off").format(sql.Identifier(banco), sql.Identifier(opcao))
        )

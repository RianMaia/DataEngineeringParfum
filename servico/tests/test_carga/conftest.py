import os
import uuid
from pathlib import Path

import psycopg
import pytest
from psycopg import sql

# O mesmo arquivo de esquema que está versionado: os testes usam o esquema REAL do repositório.
ESQUEMA = Path(__file__).resolve().parents[2] / "sql" / "001_esquema.sql"


@pytest.fixture(scope="session")
def servidor():
    """Onde está o PostgreSQL de teste, pelas variáveis padrão. Os testes só criam e apagam bancos PRÓPRIOS."""
    dados = {
        "host": os.environ.get("PGHOST", "127.0.0.1"),
        "port": int(os.environ.get("PGPORT", "5432")),
        "user": os.environ.get("PGUSER"),
        "password": os.environ.get("PGPASSWORD"),
    }
    if not dados["user"] or not dados["password"]:
        pytest.skip("defina PGUSER e PGPASSWORD (e PGHOST e PGPORT, se preciso) para rodar os testes com banco")
    return dados


@pytest.fixture(scope="session")
def modelo(servidor):
    """Um banco-modelo com o esquema aplicado, criado uma vez e apagado no fim da sessão."""
    nome = f"carga_modelo_{uuid.uuid4().hex[:10]}"
    with psycopg.connect(dbname="postgres", autocommit=True, **servidor) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(nome)))
    with psycopg.connect(dbname=nome, autocommit=True, **servidor) as conn:
        conn.execute(ESQUEMA.read_text(encoding="utf-8"))
    yield nome
    with psycopg.connect(dbname="postgres", autocommit=True, **servidor) as admin:
        admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(nome)))


@pytest.fixture
def banco(servidor, modelo):
    """Um banco NOVO para cada teste, copiado do modelo. Apagado no fim."""
    nome = f"carga_t_{uuid.uuid4().hex[:10]}"
    with psycopg.connect(dbname="postgres", autocommit=True, **servidor) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {} TEMPLATE {}").format(sql.Identifier(nome), sql.Identifier(modelo)))
    yield nome
    with psycopg.connect(dbname="postgres", autocommit=True, **servidor) as admin:
        admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(nome)))


@pytest.fixture
def conexoes(banco, servidor):
    """As duas conexões que a carga usa: a de controle (bloqueio e log) e a dos dados."""
    controle = psycopg.connect(dbname=banco, autocommit=True, **servidor)
    dados = psycopg.connect(dbname=banco, autocommit=True, **servidor)
    yield controle, dados
    controle.close()
    dados.close()

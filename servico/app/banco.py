"""Conexão da API com o PostgreSQL: um pool de conexões somente leitura, com o usuário parfum_api."""

import os

from fastapi import Request
from psycopg import Connection
from psycopg_pool import ConnectionPool

TEMPO_LIMITE_SEGUNDOS = 5  # quanto esperar por uma conexão antes de responder "banco indisponível"
TEMPO_MAXIMO_CONSULTA_MS = 10_000  # uma consulta que passe disso é cancelada
TEMPO_MAXIMO_LOCK_MS = 3_000  # esperar mais que isso por um lock de outra sessão: desiste
TEMPO_MAXIMO_OCIOSO_MS = 30_000  # uma transação parada sem fazer nada por tanto tempo é encerrada
VARIAVEIS_OBRIGATORIAS = ("POSTGRES_API_USUARIO", "POSTGRES_API_SENHA")


def parametros_de_conexao():
    """Lê a conexão do ambiente. A senha só existe aqui: nunca vai para log nem para mensagem de erro."""
    faltando = [nome for nome in VARIAVEIS_OBRIGATORIAS if not os.environ.get(nome)]
    if faltando:
        raise RuntimeError(f"variáveis de ambiente não definidas: {', '.join(faltando)}")
    return {
        "host": os.environ.get("POSTGRES_HOST", "127.0.0.1"),
        "port": int(os.environ.get("POSTGRES_PORTA", "5433")),
        "dbname": os.environ.get("POSTGRES_DB", "parfum"),
        "user": os.environ["POSTGRES_API_USUARIO"],
        "password": os.environ["POSTGRES_API_SENHA"],
        "connect_timeout": TEMPO_LIMITE_SEGUNDOS,
        # Mesmo que o usuário tivesse permissão de escrita, as sessões da API só leem. Os limites de tempo evitam
        # que um lock esquecido ou uma consulta travada prenda as conexões do pool.
        "options": (
            "-c default_transaction_read_only=on"
            f" -c statement_timeout={TEMPO_MAXIMO_CONSULTA_MS}"
            f" -c lock_timeout={TEMPO_MAXIMO_LOCK_MS}"
            f" -c idle_in_transaction_session_timeout={TEMPO_MAXIMO_OCIOSO_MS}"
        ),
    }


def criar_pool():
    """Cria o pool FECHADO: quem o cria decide quando abrir (a API abre ao iniciar, sem esperar o banco)."""
    return ConnectionPool(
        conninfo="",
        kwargs=parametros_de_conexao(),
        min_size=1,
        max_size=5,
        timeout=TEMPO_LIMITE_SEGUNDOS,
        check=ConnectionPool.check_connection,  # testa a conexão antes de emprestá-la (o banco pode ter reiniciado)
        open=False,
    )


def obter_conexao(request: Request):
    """Dependência do FastAPI: empresta uma conexão do pool durante a requisição e a devolve no fim."""
    with request.app.state.pool.connection() as conexao:
        yield conexao


def ler_meta(conexao: Connection):
    """Datas de referência da última carga concluída; None se nunca houve carga concluída."""
    linha = conexao.execute(
        "SELECT carga_id, concluida_em, data_referencia_score, snapshot_estoque_global FROM carga_log"
        " WHERE status = 'concluida' ORDER BY carga_id DESC LIMIT 1"
    ).fetchone()
    if linha is None:
        return None
    carga_id, concluida_em, data_referencia_score, snapshot_estoque_global = linha
    return {
        "carga_id": carga_id,
        "concluida_em": concluida_em,
        "data_referencia_score": data_referencia_score,
        "snapshot_estoque_global": snapshot_estoque_global,
    }

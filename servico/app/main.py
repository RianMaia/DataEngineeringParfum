"""Aplicação FastAPI da camada de serviço do DataEngineeringParfum."""

from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from psycopg import Connection, OperationalError

from app.banco import criar_pool, obter_conexao


@asynccontextmanager
async def ciclo_de_vida(aplicacao: FastAPI):
    """Abre o pool de conexões ao iniciar e o fecha ao encerrar."""
    aplicacao.state.pool = criar_pool()
    aplicacao.state.pool.open()  # não espera pelo banco: a API sobe mesmo com ele fora do ar
    try:
        yield
    finally:
        aplicacao.state.pool.close()


app = FastAPI(
    title="Rota Perfume — API de serviço",
    description="Disponibiliza resultados analíticos do pipeline Databricks.",
    version="0.1.0",
    lifespan=ciclo_de_vida,
)


@app.exception_handler(OperationalError)
def banco_indisponivel(request: Request, erro: OperationalError) -> JSONResponse:
    """Qualquer falha de conexão vira 503 sem detalhes: nada de host, usuário ou senha na resposta."""
    return JSONResponse(status_code=503, content={"detalhe": "banco de dados indisponível"})


@app.get("/saude")
def saude() -> dict[str, str]:
    """Verifica se a aplicação está no ar. Não consulta banco nem Databricks."""
    return {"status": "ok"}


@app.get("/pronto")
def pronto(conexao: Annotated[Connection, Depends(obter_conexao)]) -> dict[str, str]:
    """Verifica se o banco responde (para o healthcheck do Docker, mais adiante)."""
    conexao.execute("SELECT 1")
    return {"status": "ok"}

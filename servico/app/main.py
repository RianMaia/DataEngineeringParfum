"""Aplicação FastAPI da camada de serviço do DataEngineeringParfum."""

from fastapi import FastAPI

app = FastAPI(
    title="Rota Perfume — API de serviço",
    description="Disponibiliza resultados analíticos do pipeline Databricks.",
    version="0.1.0",
)


@app.get("/saude")
def saude() -> dict[str, str]:
    """Verifica se a aplicação está no ar. Não consulta banco nem Databricks."""
    return {"status": "ok"}

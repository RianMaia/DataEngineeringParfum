"""Formatos das respostas da API que são compartilhados entre as rotas."""

from datetime import date, datetime

from pydantic import BaseModel


class Meta(BaseModel):
    """De qual carga os dados vieram: quem consome a API vê quão atuais eles são."""

    carga_id: int
    concluida_em: datetime
    data_referencia_score: date | None
    snapshot_estoque_global: date | None

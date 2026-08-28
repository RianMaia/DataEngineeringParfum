# Databricks notebook source
import re
from datetime import datetime, timezone

from databricks.sdk.runtime import dbutils, display, spark
from pyspark.sql.types import LongType, StringType, StructField, StructType, TimestampType

EXPECTED_FILES = {
    "erp": ("produtos.csv", "pedidos.csv", "itens_pedido.csv", "pagamentos.csv", "estoque.csv"),
    "crm": ("clientes.csv", "vendedores.csv", "carteira.csv", "oportunidades.csv", "visitas.csv"),
}


dbutils.widgets.text("catalog", "lakehouse_rotaperfume", "Catalog")
catalog = dbutils.widgets.get("catalog")

if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", catalog):
    raise ValueError(f"Nome de catalogo invalido: {catalog!r}")

# COMMAND ----------

conferido_em = datetime.now(timezone.utc)
resultados = []
problemas = []

for sistema, arquivos_esperados in EXPECTED_FILES.items():
    diretorio = f"/Volumes/{catalog}/bronze/raw/{sistema}"
    try:
        arquivos_disponiveis = {item.name.rstrip("/"): item for item in dbutils.fs.ls(diretorio)}
    except Exception as exc:
        raise RuntimeError(f"Nao foi possivel listar o diretorio {diretorio}: {exc}") from exc

    for arquivo in arquivos_esperados:
        item = arquivos_disponiveis.get(arquivo)
        if item is None:
            problemas.append(f"arquivo ausente: {sistema}/{arquivo}")
            continue

        caminho = f"{diretorio}/{arquivo}"
        linhas = spark.read.option("header", True).csv(caminho).count()
        bytes_arquivo = int(item.size)
        resultados.append((sistema, arquivo, bytes_arquivo, linhas, conferido_em))

        if bytes_arquivo <= 0 or linhas <= 0:
            problemas.append(f"arquivo vazio: {sistema}/{arquivo}")

if problemas:
    detalhes = "\n- ".join(problemas)
    raise RuntimeError(f"Conferencia de chegada reprovada:\n- {detalhes}")

# COMMAND ----------

schema = StructType(
    [
        StructField("sistema", StringType(), nullable=False),
        StructField("arquivo", StringType(), nullable=False),
        StructField("bytes", LongType(), nullable=False),
        StructField("linhas", LongType(), nullable=False),
        StructField("conferido_em", TimestampType(), nullable=False),
    ]
)

resultado_df = spark.createDataFrame(resultados, schema=schema)
tabela_controle = f"`{catalog}`.`bronze`.`_raw_arquivos`"

spark.sql(
    f"""
    CREATE TABLE IF NOT EXISTS {tabela_controle} (
      sistema STRING NOT NULL,
      arquivo STRING NOT NULL,
      bytes BIGINT NOT NULL,
      linhas BIGINT NOT NULL,
      conferido_em TIMESTAMP NOT NULL
    )
    USING DELTA
    COMMENT 'Historico da conferencia de chegada dos arquivos brutos de ERP e CRM'
    """
)

resultado_df.write.mode("append").saveAsTable(tabela_controle)
display(resultado_df.orderBy("sistema", "arquivo"))

# Databricks notebook source
import re

from databricks.sdk.runtime import dbutils, display, spark
from pyspark.sql import DataFrame
from pyspark.sql.functions import col, current_timestamp, lit, row_number
from pyspark.sql.types import LongType, StringType, StructField, StructType
from pyspark.sql.window import Window

TABELAS = (
    ("erp", "produtos", 292),
    ("erp", "pedidos", 28_729),
    ("erp", "itens_pedido", 197_724),
    ("erp", "pagamentos", 27_772),
    ("erp", "estoque", 8_400),
    ("crm", "clientes", 3_040),
    ("crm", "vendedores", 42),
    ("crm", "carteira", 3_637),
    ("crm", "oportunidades", 5_979),
    ("crm", "visitas", 37_936),
)


dbutils.widgets.text("catalog", "lakehouse_rotaperfume", "Catalog")
catalog = dbutils.widgets.get("catalog")

if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", catalog):
    raise ValueError(f"Nome de catalogo invalido: {catalog!r}")

# COMMAND ----------


def ingerir_tabela(sistema: str, tabela: str) -> int:
    """Copia um CSV raw para uma tabela Delta Bronze sem transformar seu conteudo."""
    arquivo = f"{tabela}.csv"
    caminho = f"/Volumes/{catalog}/bronze/raw/{sistema}/{arquivo}"
    nome_tabela = f"`{catalog}`.`bronze`.`{tabela}`"

    dados = spark.read.format("csv").option("header", True).option("inferSchema", False).load(caminho)

    colunas_nao_string = [campo.name for campo in dados.schema.fields if campo.dataType.simpleString() != "string"]
    if colunas_nao_string:
        raise TypeError(f"Colunas nao STRING em {sistema}.{tabela}: {colunas_nao_string}")

    bronze = dados.withColumn("_ingerido_em", current_timestamp()).withColumn("_arquivo_origem", lit(caminho))
    bronze.write.format("delta").mode("overwrite").option("overwriteSchema", True).saveAsTable(nome_tabela)

    spark.sql(f"COMMENT ON TABLE {nome_tabela} IS 'Dados brutos recebidos do sistema {sistema.upper()}'")
    return spark.table(nome_tabela).count()


controle = spark.table(f"`{catalog}`.`bronze`.`_raw_arquivos`")
janela_mais_recente = Window.partitionBy("sistema", "arquivo").orderBy(col("conferido_em").desc())
controle_mais_recente = (
    controle.withColumn("_ordem", row_number().over(janela_mais_recente))
    .filter(col("_ordem") == 1)
    .select("sistema", "arquivo", "linhas")
)
linhas_controle = {(linha.sistema, linha.arquivo): int(linha.linhas) for linha in controle_mais_recente.collect()}

problemas_controle = []
for sistema, tabela, esperado in TABELAS:
    arquivo = f"{tabela}.csv"
    registrado = linhas_controle.get((sistema, arquivo))
    if registrado is None:
        problemas_controle.append(f"controle ausente: {sistema}/{arquivo}")
    elif registrado != esperado:
        problemas_controle.append(
            f"controle divergente: {sistema}/{arquivo} registrou {registrado}, esperado {esperado}"
        )

if problemas_controle:
    detalhes = "\n- ".join(problemas_controle)
    raise RuntimeError(f"Controle raw invalido:\n- {detalhes}")

# COMMAND ----------

resultados = []
divergencias = []

for sistema, tabela, esperado in TABELAS:
    arquivo = f"{tabela}.csv"
    registrado = linhas_controle[(sistema, arquivo)]
    linhas_tabela = ingerir_tabela(sistema, tabela)
    status = "OK" if linhas_tabela == registrado == esperado else "DIVERGENTE"
    resultados.append((sistema, tabela, linhas_tabela, registrado, esperado, status))

    if status != "OK":
        divergencias.append(f"{sistema}.{tabela}: tabela={linhas_tabela}, controle={registrado}, esperado={esperado}")

schema_resultado = StructType(
    [
        StructField("sistema", StringType(), nullable=False),
        StructField("tabela", StringType(), nullable=False),
        StructField("linhas_tabela", LongType(), nullable=False),
        StructField("linhas_controle", LongType(), nullable=False),
        StructField("linhas_esperadas", LongType(), nullable=False),
        StructField("status", StringType(), nullable=False),
    ]
)
resultado_df: DataFrame = spark.createDataFrame(resultados, schema=schema_resultado)
display(resultado_df.orderBy("sistema", "tabela"))

total = sum(resultado[2] for resultado in resultados)
print(f"Total de linhas ingeridas na Bronze: {total:,}".replace(",", "."))

if divergencias:
    detalhes = "\n- ".join(divergencias)
    raise RuntimeError(f"Contagens divergentes na Bronze:\n- {detalhes}")

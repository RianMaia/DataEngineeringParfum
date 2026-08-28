# Databricks notebook source
import re
from datetime import date

from databricks.sdk.runtime import dbutils, display, spark
from pyspark.sql import DataFrame
from pyspark.sql import functions as F
from pyspark.sql.window import Window

dbutils.widgets.text("catalog", "lakehouse_rotaperfume", "Catalog")
catalog = dbutils.widgets.get("catalog")

if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", catalog):
    raise ValueError(f"Nome de catalogo invalido: {catalog!r}")

fato_vendas = f"`{catalog}`.`gold`.`fato_vendas`"
dim_produto = f"`{catalog}`.`gold`.`dim_produto`"
oportunidades = f"`{catalog}`.`silver`.`oportunidades`"
visitas = f"`{catalog}`.`silver`.`visitas`"

FEATURES_NUMERICAS = (
    "recencia_dias",
    "frequencia_pedidos",
    "valor_total",
    "ticket_medio",
    "margem_total",
    "margem_percentual",
    "intervalo_medio_dias",
    "desvio_intervalo_dias",
    "atraso_relativo",
    "pedidos_ultimos_90d",
    "oportunidades_abertas",
    "oportunidades_ganhas",
    "taxa_ganho",
    "visitas_90d",
    "conversao_visita",
    "skus_distintos",
    "categorias_distintas",
    "marcas_distintas",
    "concentracao_marca_top",
    "comprou_lancamento",
)

# COMMAND ----------


def montar_features(referencia: date) -> DataFrame:
    """Monta uma linha por cliente usando somente eventos anteriores à referência."""
    referencia_col = F.lit(referencia).cast("date")

    vendas = spark.table(fato_vendas).filter(F.col("data_pedido") < referencia_col)
    oportunidades_cortadas = spark.table(oportunidades).filter(F.col("data_abertura") < referencia_col)
    visitas_cortadas = spark.table(visitas).filter(F.col("data_visita") < referencia_col)

    rfm = (
        vendas.groupBy("cliente_id")
        .agg(
            F.datediff(referencia_col, F.max("data_pedido")).cast("double").alias("recencia_dias"),
            F.countDistinct("pedido_id").cast("double").alias("frequencia_pedidos"),
            F.sum("receita").cast("double").alias("valor_total"),
            F.sum("margem").cast("double").alias("margem_total"),
            F.countDistinct(F.when(F.col("data_pedido") >= F.date_sub(referencia_col, 90), F.col("pedido_id")))
            .cast("double")
            .alias("pedidos_ultimos_90d"),
        )
        .withColumn(
            "ticket_medio",
            F.coalesce(
                F.col("valor_total") / F.when(F.col("frequencia_pedidos") != 0, F.col("frequencia_pedidos")),
                F.lit(0.0),
            ),
        )
        .withColumn(
            "margem_percentual",
            F.coalesce(
                F.col("margem_total") / F.when(F.col("valor_total") != 0, F.col("valor_total")),
                F.lit(0.0),
            ),
        )
    )

    datas_pedido = vendas.select("cliente_id", "data_pedido").distinct()
    janela_pedidos = Window.partitionBy("cliente_id").orderBy("data_pedido")
    gaps = datas_pedido.withColumn("data_pedido_anterior", F.lag("data_pedido").over(janela_pedidos)).withColumn(
        "intervalo_dias",
        F.datediff("data_pedido", "data_pedido_anterior").cast("double"),
    )
    ritmo = gaps.groupBy("cliente_id").agg(
        F.avg("intervalo_dias").cast("double").alias("intervalo_medio_dias"),
        F.stddev_pop("intervalo_dias").cast("double").alias("desvio_intervalo_dias"),
    )

    crm_oportunidades = (
        oportunidades_cortadas.groupBy("cliente_id")
        .agg(
            F.sum(F.when(F.col("resultado_oportunidade") == "ABERTA", 1).otherwise(0))
            .cast("double")
            .alias("oportunidades_abertas"),
            F.sum(F.when(F.col("resultado_oportunidade") == "GANHA", 1).otherwise(0))
            .cast("double")
            .alias("oportunidades_ganhas"),
            F.count("oportunidade_id").cast("double").alias("total_oportunidades"),
        )
        .withColumn(
            "taxa_ganho",
            F.col("oportunidades_ganhas") / F.when(F.col("total_oportunidades") != 0, F.col("total_oportunidades")),
        )
        .drop("total_oportunidades")
    )

    crm_visitas = (
        visitas_cortadas.groupBy("cliente_id")
        .agg(
            F.sum(F.when(F.col("data_visita") >= F.date_sub(referencia_col, 90), 1).otherwise(0))
            .cast("double")
            .alias("visitas_90d"),
            F.sum(F.when(F.col("resultado") == "Pedido realizado", 1).otherwise(0))
            .cast("double")
            .alias("visitas_com_pedido"),
            F.count("visita_id").cast("double").alias("total_visitas"),
        )
        .withColumn(
            "conversao_visita",
            F.col("visitas_com_pedido") / F.when(F.col("total_visitas") != 0, F.col("total_visitas")),
        )
        .drop("visitas_com_pedido", "total_visitas")
    )

    mix = vendas.groupBy("cliente_id").agg(
        F.countDistinct("sku").cast("double").alias("skus_distintos"),
        F.countDistinct("categoria").cast("double").alias("categorias_distintas"),
        F.countDistinct("marca").cast("double").alias("marcas_distintas"),
    )
    receita_por_marca = vendas.groupBy("cliente_id", "marca").agg(F.sum("receita").alias("receita_marca"))
    marca_top = receita_por_marca.groupBy("cliente_id").agg(
        F.max("receita_marca").cast("double").alias("receita_marca_top")
    )

    produtos = spark.table(dim_produto).select("sku", "data_lancamento")
    lancamentos = (
        vendas.select("cliente_id", "sku")
        .distinct()
        .join(produtos, on="sku", how="inner")
        .groupBy("cliente_id")
        .agg(
            F.max(
                F.when(
                    (F.col("data_lancamento") >= F.date_sub(referencia_col, 120))
                    & (F.col("data_lancamento") < referencia_col),
                    1,
                ).otherwise(0)
            )
            .cast("double")
            .alias("comprou_lancamento")
        )
    )

    features = (
        rfm.join(ritmo, on="cliente_id", how="left")
        .join(crm_oportunidades, on="cliente_id", how="left")
        .join(crm_visitas, on="cliente_id", how="left")
        .join(mix, on="cliente_id", how="left")
        .join(marca_top, on="cliente_id", how="left")
        .join(lancamentos, on="cliente_id", how="left")
        .fillna(
            0.0,
            subset=[
                "oportunidades_abertas",
                "oportunidades_ganhas",
                "taxa_ganho",
                "visitas_90d",
                "conversao_visita",
                "comprou_lancamento",
            ],
        )
        .withColumn(
            "atraso_relativo",
            F.when(
                F.col("intervalo_medio_dias").isNotNull() & (F.col("intervalo_medio_dias") > 0),
                F.least(F.col("recencia_dias") / F.col("intervalo_medio_dias"), F.lit(10.0)),
            ).cast("double"),
        )
        .withColumn(
            "concentracao_marca_top",
            F.coalesce(
                F.col("receita_marca_top") / F.when(F.col("valor_total") != 0, F.col("valor_total")),
                F.lit(0.0),
            ).cast("double"),
        )
        .drop("receita_marca_top")
        .withColumn("_referencia", referencia_col)
    )

    for feature in FEATURES_NUMERICAS:
        features = features.withColumn(feature, F.col(feature).cast("double"))

    return features.select("cliente_id", *FEATURES_NUMERICAS, "_referencia")


# COMMAND ----------

referencia_treino = date(2026, 8, 1)
referencia_cliente = date(2026, 8, 31)

features_treino_base = montar_features(referencia_treino)
compradores_7d = (
    spark.table(fato_vendas)
    .filter(
        (F.col("data_pedido") >= F.lit(referencia_treino))
        & (F.col("data_pedido") <= F.date_add(F.lit(referencia_treino), 6))
    )
    .select("cliente_id")
    .distinct()
    .withColumn("comprou_em_7d", F.lit(1.0))
)
features_treino = features_treino_base.join(compradores_7d, on="cliente_id", how="left").fillna(
    0.0, subset=["comprou_em_7d"]
)
features_cliente = montar_features(referencia_cliente)

tabela_treino = f"`{catalog}`.`gold`.`features_treino`"
tabela_cliente = f"`{catalog}`.`gold`.`features_cliente`"

features_treino.write.format("delta").mode("overwrite").option("overwriteSchema", True).saveAsTable(tabela_treino)
spark.sql(
    f"COMMENT ON TABLE {tabela_treino} IS "
    "'Features históricas por cliente no corte de 2026-08-01, com alvo de compra nos sete dias seguintes'"
)

features_cliente.write.format("delta").mode("overwrite").option("overwriteSchema", True).saveAsTable(tabela_cliente)
spark.sql(
    f"COMMENT ON TABLE {tabela_cliente} IS "
    "'Features por cliente no corte de 2026-08-31 para pontuação de propensão comercial'"
)

# COMMAND ----------

validacao_treino = spark.sql(
    f"""
    SELECT
      COUNT(*) AS clientes,
      ROUND(AVG(comprou_em_7d) * 100, 2) AS taxa_base_pct,
      MIN(_referencia) AS referencia_min,
      MAX(_referencia) AS referencia_max,
      COUNT_IF(recencia_dias < 0) AS recencias_negativas
    FROM {tabela_treino}
    """
).first()
validacao_cliente = spark.sql(
    f"""
    SELECT
      COUNT(*) AS clientes,
      MIN(_referencia) AS referencia_min,
      MAX(_referencia) AS referencia_max,
      COUNT_IF(recencia_dias < 0) AS recencias_negativas
    FROM {tabela_cliente}
    """
).first()

problemas = []
if validacao_treino.clientes != 2_815:
    problemas.append(f"features_treino: {validacao_treino.clientes} clientes; esperado 2815")
if float(validacao_treino.taxa_base_pct) != 10.12:
    problemas.append(f"features_treino: taxa base {validacao_treino.taxa_base_pct}%; esperado 10.12%")
if validacao_treino.referencia_min != referencia_treino or validacao_treino.referencia_max != referencia_treino:
    problemas.append("features_treino: referência divergente de 2026-08-01")
if validacao_treino.recencias_negativas != 0:
    problemas.append(f"features_treino: {validacao_treino.recencias_negativas} recências negativas")

if validacao_cliente.clientes != 2_816:
    problemas.append(f"features_cliente: {validacao_cliente.clientes} clientes; esperado 2816")
if validacao_cliente.referencia_min != referencia_cliente or validacao_cliente.referencia_max != referencia_cliente:
    problemas.append("features_cliente: referência divergente de 2026-08-31")
if validacao_cliente.recencias_negativas != 0:
    problemas.append(f"features_cliente: {validacao_cliente.recencias_negativas} recências negativas")

display(spark.table(tabela_treino).limit(10))
display(spark.table(tabela_cliente).limit(10))

if problemas:
    raise RuntimeError("Validação das features reprovada:\n- " + "\n- ".join(problemas))

print("Features de ML criadas e validadas com sucesso.")

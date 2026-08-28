# Databricks notebook source
import re
from datetime import datetime, timezone

import mlflow
import mlflow.sklearn
import numpy as np
import pandas as pd
from databricks.sdk import WorkspaceClient
from databricks.sdk.runtime import dbutils, spark
from mlflow.models import infer_signature
from mlflow.tracking import MlflowClient
from pyspark.sql import functions as F
from pyspark.sql.types import (
    DoubleType,
    IntegerType,
    StringType,
    StructField,
    StructType,
    TimestampType,
)
from pyspark.sql.window import Window
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.inspection import permutation_importance
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedKFold, cross_val_predict, train_test_split

dbutils.widgets.text("catalog", "lakehouse_rotaperfume", "Catalog")
catalog = dbutils.widgets.get("catalog")

if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", catalog):
    raise ValueError(f"Nome de catalogo invalido: {catalog!r}")

FEATURES = [
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
]

tabela_features_treino = f"`{catalog}`.`gold`.`features_treino`"
tabela_features_cliente = f"`{catalog}`.`gold`.`features_cliente`"
nome_modelo = f"{catalog}.gold.propensao_compra"

# COMMAND ----------

# Baselines no holdout, calculados antes do treinamento do modelo.
treino_pdf = spark.table(tabela_features_treino).toPandas()
X = treino_pdf[FEATURES]
y = treino_pdf["comprou_em_7d"].astype("int32")

X_treino, X_holdout, y_treino, y_holdout = train_test_split(
    X,
    y,
    test_size=0.25,
    random_state=42,
    stratify=y,
)

auc_baseline_recencia = roc_auc_score(y_holdout, -X_holdout["recencia_dias"])
auc_baseline_valor_total = roc_auc_score(y_holdout, X_holdout["valor_total"])
auc_baseline_atraso = roc_auc_score(y_holdout, X_holdout["atraso_relativo"].fillna(0.0))

baselines = {
    "-recencia_dias": auc_baseline_recencia,
    "valor_total": auc_baseline_valor_total,
    "atraso_relativo": auc_baseline_atraso,
}
melhor_baseline_nome, melhor_baseline_auc = max(baselines.items(), key=lambda item: item[1])

tabela_baselines = pd.DataFrame(
    [
        {
            "moeda": 0.5,
            "-recencia_dias": auc_baseline_recencia,
            "valor_total": auc_baseline_valor_total,
            "atraso_relativo": auc_baseline_atraso,
        }
    ],
    index=["AUC"],
)
print("Baselines no holdout:")
print(tabela_baselines.to_string(float_format=lambda valor: f"{valor:.4f}"))
print(f"Melhor baseline: {melhor_baseline_nome} ({melhor_baseline_auc:.4f})")

# COMMAND ----------

# Modelo do holdout. Os NaN intencionais das features de ritmo são preservados.
modelo_holdout = HistGradientBoostingClassifier(random_state=42)
modelo_holdout.fit(X_treino, y_treino)
score_holdout = modelo_holdout.predict_proba(X_holdout)[:, 1]
auc = roc_auc_score(y_holdout, score_holdout)

# A fila top-200 usa probabilidades out-of-fold sobre toda a base de treino.
validacao_cruzada = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
score_oof = cross_val_predict(
    HistGradientBoostingClassifier(random_state=42),
    X,
    y,
    cv=validacao_cruzada,
    method="predict_proba",
)[:, 1]

indices_top200 = np.argsort(-score_oof)[:200]
acertos_top200 = int(y.iloc[indices_top200].sum())
taxa_base = float(y.mean())
taxa_top200 = acertos_top200 / 200
lift_top200 = taxa_top200 / taxa_base

print(f"AUC no holdout: {auc:.4f}")
print(f"Taxa base: {taxa_base:.4%}")
print(f"Acertos entre os 200 primeiros: {acertos_top200}")
print(f"Lift top-200: {lift_top200:.4f}x")

# COMMAND ----------

resultado_permutacao = permutation_importance(
    modelo_holdout,
    X_holdout,
    y_holdout,
    scoring="roc_auc",
    n_repeats=5,
    random_state=42,
)
importancias = (
    pd.DataFrame(
        {
            "feature": FEATURES,
            "importancia_media": resultado_permutacao.importances_mean,
            "desvio": resultado_permutacao.importances_std,
        }
    )
    .sort_values("importancia_media", ascending=False)
    .reset_index(drop=True)
)
feature_numero_1 = str(importancias.iloc[0]["feature"])

print("Top 10 features por importância de permutação:")
print(importancias.head(10).to_string(index=False, float_format=lambda valor: f"{valor:.6f}"))

# COMMAND ----------

# Os três testes são bloqueantes e não podem ser reduzidos ou removidos.
assert auc >= melhor_baseline_auc + 0.05, (
    f"O modelo não superou o melhor baseline por pelo menos 0,05 de AUC: "
    f"modelo={auc:.4f}, baseline={melhor_baseline_auc:.4f}"
)
assert auc < 0.99, f"AUC de {auc:.4f} é alta demais e indica possível vazamento de dados"
assert lift_top200 >= 2.5, f"Lift top-200 de {lift_top200:.4f} é insuficiente para justificar a fila comercial"

# COMMAND ----------

mlflow.set_registry_uri("databricks-uc")
workspace_client = WorkspaceClient()
usuario = workspace_client.current_user.me().user_name
pasta_experimento = f"/Users/{usuario}/rotaperfume_ml"
workspace_client.workspace.mkdirs(pasta_experimento)
mlflow.set_experiment(f"{pasta_experimento}/propensao_compra")

modelo_final = HistGradientBoostingClassifier(random_state=42)
modelo_final.fit(X, y)
signature = infer_signature(X, modelo_final.predict_proba(X)[:, 1])

with mlflow.start_run(run_name="hist_gradient_boosting_propensao") as run:
    mlflow.log_params(
        {
            "algoritmo": "HistGradientBoostingClassifier",
            "random_state": 42,
            "holdout_pct": 0.25,
            "cv_folds": 5,
            "top_n": 200,
        }
    )
    mlflow.log_metrics(
        {
            "auc": auc,
            "lift_top200": lift_top200,
            "acertos_top200": acertos_top200,
            "taxa_base": taxa_base,
            "auc_baseline_recencia": auc_baseline_recencia,
            "auc_baseline_valor_total": auc_baseline_valor_total,
            "auc_baseline_atraso_relativo": auc_baseline_atraso,
        }
    )
    modelo_logado = mlflow.sklearn.log_model(
        modelo_final,
        artifact_path="modelo",
        signature=signature,
        input_example=X.head(5),
    )

versao_registrada = mlflow.register_model(model_uri=modelo_logado.model_uri, name=nome_modelo)
versao_modelo = int(versao_registrada.version)
cliente_mlflow = MlflowClient(registry_uri="databricks-uc")
cliente_mlflow.set_registered_model_alias(nome_modelo, "prod", versao_modelo)

print(f"Modelo registrado: {nome_modelo}, versão {versao_modelo}, alias @prod, run_id={run.info.run_id}")

# COMMAND ----------

# Pontuação em pandas, usando exatamente a ordem de features gravada no modelo.
modelo_prod = mlflow.sklearn.load_model(f"models:/{nome_modelo}@prod")
features_modelo = list(modelo_prod.feature_names_in_)
clientes_pdf = spark.table(tabela_features_cliente).toPandas()
scores_clientes = modelo_prod.predict_proba(clientes_pdf[features_modelo])[:, 1]

score_pdf = pd.DataFrame(
    {
        "cliente_id": clientes_pdf["cliente_id"].astype("int32"),
        "score": scores_clientes.astype("float64"),
        "_referencia": clientes_pdf["_referencia"],
        "versao_modelo": np.int32(versao_modelo),
    }
)
janela_score = Window.orderBy(F.col("score").asc())
score_propensao = (
    spark.createDataFrame(score_pdf)
    .withColumn("cliente_id", F.col("cliente_id").cast("int"))
    .withColumn("score", F.col("score").cast("double"))
    .withColumn("_referencia", F.col("_referencia").cast("date"))
    .withColumn("versao_modelo", F.col("versao_modelo").cast("int"))
    .withColumn("quartil", F.ntile(4).over(janela_score))
    .withColumn(
        "faixa",
        F.when(F.col("quartil") == 1, "Fria")
        .when(F.col("quartil") == 2, "Morna")
        .when(F.col("quartil") == 3, "Quente")
        .otherwise("Muito quente"),
    )
    .select("cliente_id", "score", "faixa", "_referencia", "versao_modelo")
)

tabela_score = f"`{catalog}`.`gold`.`score_propensao`"
score_propensao.write.format("delta").mode("overwrite").option("overwriteSchema", True).saveAsTable(tabela_score)
spark.sql(
    f"COMMENT ON TABLE {tabela_score} IS "
    "'Score de propensão de compra por cliente, segmentado em quatro faixas de prioridade comercial'"
)

# COMMAND ----------

schema_metricas = StructType(
    [
        StructField("versao_modelo", IntegerType(), nullable=False),
        StructField("auc", DoubleType(), nullable=False),
        StructField("lift_top200", DoubleType(), nullable=False),
        StructField("acertos_top200", IntegerType(), nullable=False),
        StructField("taxa_base", DoubleType(), nullable=False),
        StructField("auc_baseline_recencia", DoubleType(), nullable=False),
        StructField("auc_baseline_valor_total", DoubleType(), nullable=False),
        StructField("auc_baseline_atraso_relativo", DoubleType(), nullable=False),
        StructField("feature_numero_1", StringType(), nullable=False),
        StructField("_treinado_em", TimestampType(), nullable=False),
    ]
)
metricas = spark.createDataFrame(
    [
        (
            versao_modelo,
            float(auc),
            float(lift_top200),
            acertos_top200,
            taxa_base,
            float(auc_baseline_recencia),
            float(auc_baseline_valor_total),
            float(auc_baseline_atraso),
            feature_numero_1,
            datetime.now(timezone.utc),
        )
    ],
    schema=schema_metricas,
)
tabela_metricas = f"`{catalog}`.`gold`.`modelo_metricas`"
metricas.write.format("delta").mode("append").saveAsTable(tabela_metricas)
spark.sql(
    f"COMMENT ON TABLE {tabela_metricas} IS "
    "'Histórico de desempenho, baselines e principal feature de cada versão do modelo de propensão'"
)

# COMMAND ----------

holdout_pdf = pd.DataFrame(
    {
        "score": score_holdout.astype("float64"),
        "comprou": y_holdout.to_numpy(dtype="int32"),
    }
)
janela_holdout = Window.orderBy(F.col("score").asc())
calibragem_holdout = (
    spark.createDataFrame(holdout_pdf)
    .withColumn("quartil", F.ntile(4).over(janela_holdout))
    .withColumn(
        "faixa",
        F.when(F.col("quartil") == 1, "Fria")
        .when(F.col("quartil") == 2, "Morna")
        .when(F.col("quartil") == 3, "Quente")
        .otherwise("Muito quente"),
    )
    .groupBy("faixa", "quartil")
    .agg(
        F.count("*").alias("clientes"),
        F.sum("comprou").alias("compraram"),
        F.avg("comprou").cast("double").alias("taxa_de_compra"),
        F.avg("score").cast("double").alias("score_medio"),
    )
    .orderBy("quartil")
    .drop("quartil")
)
tabela_calibragem = f"`{catalog}`.`gold`.`calibragem_holdout`"
calibragem_holdout.write.format("delta").mode("overwrite").option("overwriteSchema", True).saveAsTable(
    tabela_calibragem
)
spark.sql(
    f"COMMENT ON TABLE {tabela_calibragem} IS "
    "'Calibragem do score no holdout por faixa, com volume, compras observadas e taxa de conversão'"
)

print("Modelo, scores, métricas e calibragem gravados com sucesso.")

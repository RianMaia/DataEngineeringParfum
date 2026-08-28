Continue o mesmo bundle. As features estão em gold.features_treino e
gold.features_cliente.

Crie src/ml/12-modelo.py — um notebook Python para serverless. Nesta ordem:

1. BASELINE, antes de treinar qualquer coisa.
   Separe 25% de gold.features_treino como holdout, com random_state=42 e
   estratificado pelo alvo. No holdout, calcule roc_auc_score do alvo contra
   cada regra simples, usada como se fosse o score:
     a) -recencia_dias      ("ligue para quem comprou recentemente")
     b)  valor_total        ("ligue para quem compra mais")
     c)  atraso_relativo    ("ligue para quem está atrasado")
   Imprima os três lado a lado, com 0,5000 (a moeda) na mesma tabela.
   Guarde o melhor deles: é a régua do teste 1.

2. TREINO.
   HistGradientBoostingClassifier do scikit-learn, random_state=42.
   NÃO impute NULL: este algoritmo trata NaN nativamente, e as features de
   ritmo são NULL de propósito para quem tem um pedido só.
   NÃO use XGBoost: ele treina e registra, mas falha ao carregar de volta no
   serverless por conflito com scikit-learn 1.6.1 (__sklearn_tags__), e o erro
   só aparece uma tarefa depois.

3. AS DUAS MÉTRICAS.
   auc          — no holdout
   lift_top200  — pontue TODOS os clientes de features_treino por validação
                  cruzada out-of-fold (StratifiedKFold, 5 folds, shuffle,
                  random_state=42), ordene por score, pegue os 200 primeiros e
                  divida a taxa de compra deles pela taxa base.
                  Out-of-fold, e não só o holdout, porque a fila real é de 200
                  entre 3.000 — no holdout de 700 os 200 primeiros seriam 28%
                  da amostra, e o número sairia otimista.
                  Imprima também acertos_top200 (quantos dos 200 compraram).
                  Essa é a métrica que responde a pergunta do diretor.

4. IMPORTÂNCIA POR PERMUTAÇÃO, no holdout, n_repeats=5. Imprima o top 10.

5. MLFLOW.
   Antes de mlflow.set_experiment, crie a pasta pai com
   WorkspaceClient().workspace.mkdirs(...) — sem isso o erro é
   "BAD_REQUEST: For input string: None" e não menciona pasta nenhuma.
   O serverless tem MLflow 2.22: use log_model(..., artifact_path="modelo"),
   nunca o name= do MLflow 3.
   Registre em lakehouse_rotaperfume.gold.propensao_compra com
   mlflow.set_registry_uri("databricks-uc") e aponte o alias @prod para a
   versão recém-criada.
   Logue params, auc, lift_top200, acertos_top200 e a taxa base.

6. TRÊS TESTES QUE INTERROMPEM A TAREFA (assert, com mensagem em português):
   - o modelo ganha do MELHOR baseline por pelo menos 0,05 de AUC
   - auc < 0,99 — bom demais é vazamento, não competência
   - lift_top200 >= 2,5 — abaixo disso a fila não justifica o projeto

7. SCORE.
   Carregue o modelo com mlflow.sklearn.load_model("models:/...@prod") e use
   predict_proba — NÃO use pyfunc.predict, que devolve a classe e transforma
   a coluna inteira em zeros e uns.
   NÃO use mlflow.pyfunc.spark_udf: não roda no serverless
   (InvalidVersion: '18.x-aarch64-photon-scala2'). Traga para pandas: 3.000
   clientes cabem na memória com folga.
   Pontue com EXATAMENTE as colunas do treino, na mesma ordem, lendo
   modelo.feature_names_in_ — não confie na ordem das colunas da tabela.
   Grave gold.score_propensao com cliente_id (INT), score, a faixa
   (NTILE(4) sobre o score: Fria, Morna, Quente, Muito quente), _referencia e
   a versao do modelo — o número que veio do registro no UC.

8. AS MÉTRICAS TAMBÉM VIRAM TABELA — o Genie não lê MLflow, e daqui a seis
   meses ninguém abre a interface de experimento:

   gold.modelo_metricas     uma linha por treino: versao, auc, lift_top200,
                            acertos_top200, taxa_base, o AUC de cada um dos
                            três baselines, a feature nº 1 e _treinado_em
   gold.calibragem_holdout  faixa, clientes, compraram, taxa_de_compra e
                            score_medio, calculados no holdout — é a prova do
                            slide *Não é acurácia*, e a única que o comercial confere sozinho

COMMENT em português NA TABELA, nas três que este prompt cria. A auditoria da
noite 2 quebra o job se faltar, e saveAsTable não grava comment de tabela:
rode COMMENT ON TABLE em seguida.

Registre a tarefa ml_modelo em resources/pipeline.job.yml, depois de
ml_features, e faça o deploy.

NÃO rode o job inteiro para testar: rode só a tarefa nova, com
bash scripts/rodar-tarefa.sh <perfil> ml_modelo — o job completo leva 3m30 e
a tarefa sozinha 35s.
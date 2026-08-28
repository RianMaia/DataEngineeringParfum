Leia aulas/aula-02-engenharia-de-dados/prd/CLAUDE.md antes de começar.

Crie o projeto da noite 2 em aulas/aula-02-engenharia-de-dados/rotaperfume/,
como um Databricks Asset Bundle. Esta é a primeira de seis entregas — as outras
cinco estendem este mesmo bundle, então deixe a estrutura pronta para crescer.

O ambiente está ZERADO: o catálogo não existe. Crie tudo.

CONTEXTO DO WORKSPACE
- profile: projeto-dados-ia   (sempre passe --profile, nunca deixe implícito)
- host: https://dbc-84cd5511-fa25.cloud.databricks.com
- SQL Warehouse: 666be37e3fededf2 (Serverless Starter Warehouse)
- Databricks Free Edition: tudo serverless, nunca configure cluster

1. databricks.yml
   - bundle name: rotaperfume
   - variables: catalog (default lakehouse_rotaperfume) e warehouse_id
     (default 666be37e3fededf2)
   - targets dev (default) e prod
   - include: resources/*.yml

   ARMADILHA IMPORTANTE: NÃO use `mode: development` no target dev. Ele prefixa
   o nome dos recursos com [dev seu_usuario] — inclusive os SCHEMAS do Unity
   Catalog, que virariam dev_fulano_bronze e quebrariam todo o SQL da noite.
   Em vez disso, pause o agendamento explicitamente com
   `presets: { trigger_pause_status: PAUSED }`. Deixe um comentário no YAML
   explicando isso, porque é o tipo de coisa que só se descobre errando.

2. scripts/criar-catalogo.sh
   Cria o catálogo com `CREATE CATALOG IF NOT EXISTS`, via
   `databricks experimental aitools tools query`. Recebe o profile como
   primeiro argumento.

   POR QUE NÃO ESTÁ NO BUNDLE: no Free Edition o Default Storage está ligado,
   e nessa configuração a API do Unity Catalog RECUSA criar catálogo — ela
   exige um MANAGED LOCATION que a conta gratuita não tem:
     Error: Metastore storage root URL does not exist.
            Default Storage is enabled in your account. (400 INVALID_STATE)
   O comando SQL funciona. Deixe esse motivo comentado no script.

3. resources/catalogo.yml — o resto do catálogo como recurso do bundle:
   - schemas: bronze, silver e gold
   - volumes: bronze.raw, do tipo MANAGED
   COMMENT em todos, explicando o papel de cada camada em uma frase.

4. scripts/subir-raw.sh
   Sobe os CSVs de dados/erp e dados/crm (na raiz do repositório) para
   /Volumes/{catalog}/bronze/raw/erp e /crm.
   Use `databricks fs cp --recursive --overwrite` — e lembre que o comando
   exige o esquema `dbfs:` no destino, mesmo sendo um Volume do UC.
   Se dados/ não existir, gere antes com
   `python3 material/gerar_dataset.py --saida ./dados --seed 42`.
   O profile é o primeiro argumento, sem default.

5. src/raw/conferencia.py
   Notebook Python serverless (cabeçalho `# Databricks notebook source`) que faz
   a CONFERÊNCIA DE CHEGADA do raw:
   - lê o parâmetro catalog via dbutils.widgets
   - confere que os 10 arquivos esperados existem no Volume
     (erp: produtos, pedidos, itens_pedido, pagamentos, estoque;
      crm: clientes, vendedores, carteira, oportunidades, visitas)
   - para cada um: tamanho em bytes e número de linhas de dado
   - grava a tabela de controle bronze._raw_arquivos com
     (sistema, arquivo, bytes, linhas, conferido_em) e COMMENT
   - se faltar arquivo ou algum vier vazio, levante exceção e interrompa
   - imprime uma tabela legível ao final

6. resources/pipeline.job.yml
   O job rotaperfume_pipeline, com UMA tarefa: raw_conferencia. Serverless.
   Agendamento diário às 6h, timezone America/Sao_Paulo.
   Este job ganha tarefas nos próximos cinco prompts — escreva isso num
   comentário no topo do YAML, com o desenho de como ele vai ficar.

7. Rode NESTA ORDEM e me mostre a saída de cada passo:
   bash scripts/criar-catalogo.sh projeto-dados-ia
   databricks bundle validate --target dev --profile projeto-dados-ia
   databricks bundle deploy   --target dev --profile projeto-dados-ia
   bash scripts/subir-raw.sh  projeto-dados-ia
   databricks bundle run rotaperfume_pipeline --target dev --profile projeto-dados-ia

A ordem importa duas vezes: o catálogo tem que existir antes do deploy criar os
schemas, e o Volume tem que existir antes de subir arquivo nele.

Não crie a camada bronze ainda. Hoje o dado só chega no Volume.
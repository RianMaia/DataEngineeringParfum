Continue o bundle em aulas/aula-02-engenharia-de-dados/rotaperfume/.
A camada raw já está no Volume e conferida. Agora crie a bronze.

1. src/bronze/ingestao.py
   Notebook Python serverless (`# Databricks notebook source`) que lê os 10
   CSVs de /Volumes/{catalog}/bronze/raw/{sistema}/{tabela}.csv e grava
   {catalog}.bronze.{tabela} em Delta, modo overwrite.

   REGRAS DA BRONZE — nenhuma limpeza, nenhuma conversão de tipo:
   - leia TUDO como string. Nada de inferSchema.
   - os CSVs são CRLF e têm header. Não use multiLine.
   - adicione só duas colunas: _ingerido_em (timestamp) e _arquivo_origem.
   - escreva a função de ingestão UMA vez e itere sobre a lista das 10 tabelas.
     Não repita bloco por tabela.
   - ao final, imprima uma tabela com o nome e a contagem de linhas de cada uma,
     e compare com o que bronze._raw_arquivos registrou no prompt anterior:
     linhas da tabela = linhas do arquivo menos o header. Se divergir, falhe.

   Adicione COMMENT em cada tabela dizendo de qual sistema de origem ela veio.

2. resources/pipeline.job.yml
   Acrescente a tarefa bronze_ingestao, com depends_on: raw_conferencia.
   A ordem é o conteúdo: se a conferência falhar, a bronze não roda.

3. Rode e me mostre a saída:
   databricks bundle deploy --target dev --profile projeto-dados-ia
   databricks bundle run rotaperfume_pipeline --target dev --profile projeto-dados-ia

CONTAGENS ESPERADAS (do gerador com seed 42 — se divergir, o erro é seu):
  produtos 292 · pedidos 28.729 · itens_pedido 197.724 · pagamentos 27.772
  estoque 8.400 · clientes 3.040 · vendedores 42 · carteira 3.637
  oportunidades 5.979 · visitas 37.936     total: 313.551

Não limpe nada. A sujeira é o conteúdo do próximo prompt.
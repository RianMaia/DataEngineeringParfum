Continue o bundle em aulas/aula-02-engenharia-de-dados/rotaperfume/.
A bronze está pronta. Agora a silver: limpar, tipar e declarar o contrato.

Crie os arquivos em src/silver/, um por assunto, em SQL (rodam como sql_task
no warehouse 666be37e3fededf2). Use CREATE OR REPLACE TABLE
lakehouse_rotaperfume.silver.{tabela}.

ATENÇÃO — armadilha já medida neste workspace: ANSI mode está ligado.
to_date() e date_trunc() sobre data malformada ABORTAM a query com
CAST_INVALID_INPUT, não retornam NULL. Use try_to_date() em toda conversão
de data, sempre.

01-clientes.sql
- cnpj vem em três formatos: puro, pontuado e com espaço em volta.
  Normalize para 14 dígitos: trim, depois regexp_replace tirando não-dígito,
  depois lpad com zero à esquerda. Nunca converta CNPJ para número.
- razao_social tem caixa e espaçamento inconsistentes. Padronize com initcap
  e colapse espaço duplo.
- data_cadastro vem em ISO e em dd/MM/yyyy misturados: coalesce de dois
  try_to_date.
- 40 CNPJs têm dois cliente_id. Deduplique com row_number() por cnpj,
  mantendo o cadastro MAIS ANTIGO. Guarde cliente_ids_duplicados (array) para
  rastreabilidade — os pedidos antigos apontam para o id descartado.
- ativo: de 'S'/'N' para boolean.

02-pedidos.sql
- data_pedido nos dois formatos, mesmo tratamento.
- valor_total é texto: CAST para DECIMAL(18,2).
- pedido cancelado tem valor zerado sem flag clara: crie a coluna booleana
  cancelado a partir do status.
- crie valor_liquido: zero quando cancelado, valor_total caso contrário.
- crie ano e mes a partir da data.

03-itens-e-produtos.sql
- produtos: tipos certos, data_lancamento com try_to_date, ativo boolean.
- itens_pedido: quantidade negativa é DEVOLUÇÃO, não erro. Crie devolucao
  (boolean) e quantidade_abs (int). NÃO descarte essas linhas.
- join com produtos para marcar sku_descontinuado quando o produto não está
  mais ativo.

04-crm-e-financeiro.sql
- vendedores, carteira, oportunidades, visitas, pagamentos, estoque.
- carteira: existe vendedor desligado com carteira vigente. Não conserte o
  dado — crie a coluna vigente, que respeita data_fim E data_desligamento, e
  a coluna orfao_vendedor_desligado, que EXPÕE o problema para o gestor.
- oportunidades: as etapas na origem se chamam 'Fechado ganho' e
  'Fechado perdido'. NÃO são 'Ganha' e 'Perdida' — confira antes de escrever
  o CASE, com um SELECT DISTINCT etapa.
- estoque: ruptura como boolean a partir de saldo = 0.

EM TODAS as tabelas silver:
- colunas de auditoria _processado_em e _linhas_origem
- COMMENT na tabela e nas colunas que exigiram decisão de limpeza,
  dizendo o que foi feito e por quê
- depois do CREATE, declare o contrato com
  ALTER TABLE ... ADD CONSTRAINT ... CHECK (...):
    silver.clientes     → length(cnpj) = 14
    silver.clientes     → data_cadastro IS NOT NULL
    silver.pedidos      → data_pedido IS NOT NULL
    silver.pedidos      → NOT cancelado OR valor_liquido = 0
    silver.itens_pedido → quantidade_abs > 0

  ATENÇÃO À QUARTA. A regra intuitiva seria `valor_liquido >= 0`, e ela FALHA:
  135 pedidos têm valor negativo. Não é sujeira — os 135 contêm item devolvido,
  e o saldo do pedido virou negativo. Negócio legítimo. A constraint certa é a
  que está escrita acima: pedido cancelado tem que ter valor ZERO.

  Se uma constraint falhar ao ser adicionada, ela fez o trabalho dela: virou
  uma suposição sua em pergunta, antes de ela virar número no dashboard.

Escreva o caminho COMPLETO das tabelas no SQL (lakehouse_rotaperfume.silver.x).
`sql_task` não substitui identificador por parâmetro, e SQL legível vale mais
numa aula do que IDENTIFIER(:catalog || '.silver.x').

Acrescente ao resources/pipeline.job.yml quatro tarefas sql_task, todas com
depends_on: bronze_ingestao. Elas rodam EM PARALELO entre si — nenhuma
depende da outra, e é o formato que o DAG desenha melhor na tela.

Rode e me mostre a saída:
  databricks bundle deploy --target dev --profile projeto-dados-ia
  databricks bundle run rotaperfume_pipeline --target dev --profile projeto-dados-ia

O QUE PRECISA BATER (medido na noite 1, com seed 42):
  3.443 datas em dd/MM/yyyy convertidas · 1.111 CNPJ pontuados
  223 CNPJ com espaço · 309 CNPJ com zero à esquerda
  40 CNPJ duplicados → 3.000 clientes únicos no final
  2.327 itens de devolução · 957 pedidos cancelados
  76 itens com SKU descontinuado · 441 carteiras de vendedor desligado
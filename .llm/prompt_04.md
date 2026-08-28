Continue o bundle em aulas/aula-02-engenharia-de-dados/rotaperfume/.
A silver está limpa e com contrato. Agora a gold: modelar para consumo.

Crie em src/gold/, em SQL, lendo SÓ da silver — nunca da bronze.

05-dimensoes.sql — quatro dimensões conformadas
  gold.dim_cliente    uma linha por cliente: segmento, cidade, uf, data de
                      cadastro, data do primeiro e do último pedido, total de
                      pedidos, receita acumulada, dias desde a última compra
  gold.dim_produto    uma linha por SKU: marca, categoria, nota olfativa,
                      custo, preço de tabela, data de lançamento, descontinuado
  gold.dim_vendedor   uma linha por vendedor: região, meta mensal, ativo
  gold.dim_calendario uma linha por dia dos 24 meses: ano, mes, nome do mês,
                      trimestre, dia da semana, e a coluna mes_pico_setor
                      (abril, junho e outubro = TRUE)

06-fato-vendas.sql — o contrato, escrito antes do SQL num comentário no topo
  Granularidade: uma linha por ITEM de pedido
  Filtro: exclua pedidos cancelados. NÃO exclua devolução.
  Dimensões: data_pedido, ano, mes, canal, cliente_id, razao_social, segmento,
             cidade, vendedor_id, sku, categoria, marca, nota_olfativa
  Métricas:  quantidade, preco_praticado, receita, custo, margem, devolucao
  custo  = quantidade * custo_unitario do produto
  margem = receita - custo
  Devolução entra com quantidade e receita NEGATIVAS, com a flag devolucao.
  Particione por ano e mes.

  POR QUE A DEVOLUÇÃO FICA DENTRO: se ela ficar de fora, a gold soma
  R$ 103,6 mi e a silver R$ 102,3 mi. R$ 1,26 milhão de diferença entre duas
  camadas do mesmo pipeline. Quem quiser o bruto pede:
    SUM(receita) FILTER (WHERE NOT devolucao)

07-marts.sql — um mart por diretoria, todos sobre o MESMO fato
  gold.mart_vendas_por_vendedor   grão vendedor × mês: receita, margem, meta,
                                  atingimento, clientes atendidos, ticket médio
  gold.mart_produto_performance   grão SKU × mês: receita, margem, margem %,
                                  quantidade, curva ABC por receita acumulada
  gold.mart_financeiro_recebimento grão mês de vencimento: valor a receber,
                                  recebido, atraso médio, custo de taxa

COMMENT em TODAS as tabelas, e em TODAS as colunas de fato_vendas, explicando
o significado de NEGÓCIO, não o técnico. Por exemplo, em margem:
"Receita menos custo do produto. Não considera desconto comercial nem frete."
Nas dimensões, comente as colunas que exigiram decisão (dias_sem_comprar,
mes_pico_setor); cidade e uf se explicam sozinhas.
Isso não é capricho: é o que o Genie lê no prompt 6 para escolher a coluna
certa. Coluna sem comentário é coluna que ele usa errado, com confiança.

08-testes.sql — os 9 testes, cada um levantando exceção com raise_error()
quando falhar, para o job PARAR:
  1. receita da gold = receita da silver = R$ 102.303.828,05 (tolerância 0,01)
     Esse é o teste que mais importa: limpeza NÃO PODE mudar o faturamento.
  2. CNPJ único na silver.clientes (0 duplicados)
  3. nenhuma data_pedido nula na silver.pedidos
  4. receita negativa só onde devolucao = true
  5. volume da gold.fato_vendas entre 140.000 e 250.000 linhas
  6. nenhum pedido_id na gold que não exista na silver.pedidos
  7. nenhum cliente_id na gold que não exista na silver.clientes
  8. mart_produto_performance soma o mesmo que fato_vendas
  9. todo CNPJ com exatamente 14 dígitos
  Cada teste imprime nome, valor calculado, valor esperado e passou/falhou.

Acrescente ao resources/pipeline.job.yml:
  gold_dimensoes   depends_on: as quatro tarefas silver
  gold_fato_vendas depends_on: gold_dimensoes
  gold_marts       depends_on: gold_fato_vendas
  testes           depends_on: gold_marts   ← por último, e obrigatório

Rode e me mostre a saída:
  databricks bundle deploy --target dev --profile projeto-dados-ia
  databricks bundle run rotaperfume_pipeline --target dev --profile projeto-dados-ia

Os 9 testes precisam passar. Se algum falhar, corrija a transformação —ç
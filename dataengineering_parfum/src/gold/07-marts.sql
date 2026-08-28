SET ANSI_MODE = TRUE;

CREATE OR REPLACE TABLE lakehouse_rotaperfume.gold.mart_vendas_por_vendedor
COMMENT 'Desempenho comercial mensal por vendedor, conciliado com a fato de vendas'
AS
SELECT
  f.vendedor_id,
  v.nome AS vendedor,
  v.regiao,
  f.ano,
  f.mes,
  CAST(SUM(f.receita) AS DECIMAL(18, 2)) AS receita,
  CAST(SUM(f.margem) AS DECIMAL(18, 2)) AS margem,
  v.meta_mensal AS meta,
  CAST(100 * SUM(f.receita) / NULLIF(v.meta_mensal, 0) AS DECIMAL(18, 2)) AS atingimento_pct,
  COUNT(DISTINCT f.cliente_id) AS clientes_atendidos,
  CAST(SUM(f.receita) / NULLIF(COUNT(DISTINCT f.pedido_id), 0) AS DECIMAL(18, 2)) AS ticket_medio
FROM lakehouse_rotaperfume.gold.fato_vendas f
INNER JOIN lakehouse_rotaperfume.gold.dim_vendedor v ON f.vendedor_id = v.vendedor_id
GROUP BY f.vendedor_id, v.nome, v.regiao, f.ano, f.mes, v.meta_mensal;

COMMENT ON COLUMN lakehouse_rotaperfume.gold.mart_vendas_por_vendedor.atingimento_pct IS
  'Percentual da receita líquida mensal em relação à meta mensal do vendedor';
COMMENT ON COLUMN lakehouse_rotaperfume.gold.mart_vendas_por_vendedor.ticket_medio IS
  'Receita líquida mensal dividida pela quantidade de pedidos não cancelados';

CREATE OR REPLACE TABLE lakehouse_rotaperfume.gold.mart_produto_performance
COMMENT 'Desempenho mensal por SKU com margem e classificação ABC pela receita líquida acumulada'
AS
WITH resumo AS (
  SELECT
    sku,
    categoria,
    marca,
    ano,
    mes,
    CAST(SUM(receita) AS DECIMAL(18, 2)) AS receita,
    CAST(SUM(margem) AS DECIMAL(18, 2)) AS margem,
    SUM(quantidade) AS quantidade
  FROM lakehouse_rotaperfume.gold.fato_vendas
  GROUP BY sku, categoria, marca, ano, mes
),
acumulado AS (
  SELECT
    resumo.*,
    SUM(receita) OVER (
      PARTITION BY ano, mes
      ORDER BY receita DESC, sku
      ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) / NULLIF(SUM(receita) OVER (PARTITION BY ano, mes), 0) AS percentual_receita_acumulada
  FROM resumo
)
SELECT
  sku,
  categoria,
  marca,
  ano,
  mes,
  receita,
  margem,
  CAST(100 * margem / NULLIF(receita, 0) AS DECIMAL(18, 2)) AS margem_pct,
  quantidade,
  CAST(percentual_receita_acumulada AS DECIMAL(18, 6)) AS percentual_receita_acumulada,
  CASE
    WHEN percentual_receita_acumulada <= 0.80 THEN 'A'
    WHEN percentual_receita_acumulada <= 0.95 THEN 'B'
    ELSE 'C'
  END AS curva_abc
FROM acumulado;

COMMENT ON COLUMN lakehouse_rotaperfume.gold.mart_produto_performance.margem_pct IS
  'Margem do SKU dividida por sua receita líquida no mês';
COMMENT ON COLUMN lakehouse_rotaperfume.gold.mart_produto_performance.curva_abc IS
  'Classe A até 80%, B até 95% e C no restante da receita líquida acumulada do mês';

CREATE OR REPLACE TABLE lakehouse_rotaperfume.gold.mart_financeiro_recebimento
COMMENT 'Posição financeira por mês de vencimento dos pedidos presentes na fato de vendas'
AS
WITH pedidos_na_fato AS (
  SELECT DISTINCT pedido_id
  FROM lakehouse_rotaperfume.gold.fato_vendas
)
SELECT
  YEAR(p.data_vencimento) AS ano,
  MONTH(p.data_vencimento) AS mes,
  CAST(SUM(p.valor) AS DECIMAL(18, 2)) AS valor_a_receber,
  CAST(SUM(CASE WHEN p.data_pagamento IS NOT NULL THEN p.valor_liquido ELSE 0 END) AS DECIMAL(18, 2)) AS recebido,
  CAST(AVG(
    CASE
      WHEN p.data_pagamento IS NULL THEN NULL
      ELSE GREATEST(DATEDIFF(p.data_pagamento, p.data_vencimento), 0)
    END
  ) AS DECIMAL(18, 2)) AS atraso_medio_dias,
  CAST(SUM(p.valor - p.valor_liquido) AS DECIMAL(18, 2)) AS custo_taxa
FROM lakehouse_rotaperfume.silver.pagamentos p
INNER JOIN pedidos_na_fato f ON p.pedido_id = f.pedido_id
GROUP BY YEAR(p.data_vencimento), MONTH(p.data_vencimento);

COMMENT ON COLUMN lakehouse_rotaperfume.gold.mart_financeiro_recebimento.recebido IS
  'Valor líquido dos pagamentos com data de recebimento registrada';
COMMENT ON COLUMN lakehouse_rotaperfume.gold.mart_financeiro_recebimento.atraso_medio_dias IS
  'Média de dias de atraso dos pagamentos realizados; antecipações contam como zero';
COMMENT ON COLUMN lakehouse_rotaperfume.gold.mart_financeiro_recebimento.custo_taxa IS
  'Diferença acumulada entre o valor cobrado e o valor líquido após taxas';

CREATE OR REPLACE VIEW lakehouse_rotaperfume.gold.receita_mensal (
  mes_referencia COMMENT 'Primeiro dia do mês usado como eixo cronológico',
  ano COMMENT 'Ano do pedido',
  mes COMMENT 'Número do mês do pedido',
  nome_mes COMMENT 'Nome do mês em português',
  mes_pico_setor COMMENT 'Indica abril, junho e outubro, quando o varejo antecipa compras sazonais',
  receita COMMENT 'Receita líquida mensal, incluindo devoluções com valor negativo',
  margem COMMENT 'Receita líquida mensal menos o custo dos produtos',
  pedidos COMMENT 'Quantidade distinta de pedidos no mês'
)
COMMENT 'Qual foi a receita, a margem e o número de pedidos em cada mês, e quais meses são picos do setor?'
AS
SELECT
  CAST(DATE_TRUNC('MONTH', f.data_pedido) AS DATE) AS mes_referencia,
  dc.ano,
  dc.mes,
  dc.nome_mes,
  dc.mes_pico_setor,
  CAST(SUM(f.receita) AS DECIMAL(18, 2)) AS receita,
  CAST(SUM(f.margem) AS DECIMAL(18, 2)) AS margem,
  COUNT(DISTINCT f.pedido_id) AS pedidos
FROM lakehouse_rotaperfume.gold.fato_vendas f
INNER JOIN lakehouse_rotaperfume.gold.dim_calendario dc ON dc.data = f.data_pedido
GROUP BY
  CAST(DATE_TRUNC('MONTH', f.data_pedido) AS DATE),
  dc.ano,
  dc.mes,
  dc.nome_mes,
  dc.mes_pico_setor;

CREATE OR REPLACE VIEW lakehouse_rotaperfume.gold.ranking_marcas (
  marca COMMENT 'Marca comercial do produto',
  receita COMMENT 'Receita líquida acumulada da marca',
  margem_pct COMMENT 'Margem da marca como percentual de sua receita líquida',
  participacao_pct COMMENT 'Participação percentual da marca na receita líquida total'
)
COMMENT 'Quais marcas lideram a receita e qual é a margem e a participação de cada uma no total?'
AS
WITH resumo AS (
  SELECT
    marca,
    CAST(SUM(receita) AS DECIMAL(18, 2)) AS receita,
    CAST(SUM(margem) AS DECIMAL(18, 2)) AS margem
  FROM lakehouse_rotaperfume.gold.fato_vendas
  GROUP BY marca
)
SELECT
  marca,
  receita,
  CAST(100 * margem / NULLIF(receita, 0) AS DECIMAL(18, 2)) AS margem_pct,
  CAST(100 * receita / NULLIF(SUM(receita) OVER (), 0) AS DECIMAL(18, 2)) AS participacao_pct
FROM resumo;

CREATE OR REPLACE VIEW lakehouse_rotaperfume.gold.margem_por_categoria (
  categoria COMMENT 'Categoria comercial do produto',
  receita COMMENT 'Receita líquida acumulada da categoria',
  margem COMMENT 'Receita líquida menos o custo dos produtos da categoria',
  margem_pct COMMENT 'Margem da categoria como percentual de sua receita líquida'
)
COMMENT 'Quais categorias geram mais receita e quais operam com a menor margem percentual?'
AS
SELECT
  categoria,
  CAST(SUM(receita) AS DECIMAL(18, 2)) AS receita,
  CAST(SUM(margem) AS DECIMAL(18, 2)) AS margem,
  CAST(100 * SUM(margem) / NULLIF(SUM(receita), 0) AS DECIMAL(18, 2)) AS margem_pct
FROM lakehouse_rotaperfume.gold.fato_vendas
GROUP BY categoria;

CREATE OR REPLACE VIEW lakehouse_rotaperfume.gold.clientes_em_risco (
  cliente_id COMMENT 'Identificador canônico do cliente',
  cnpj COMMENT 'CNPJ textual de 14 dígitos do cliente',
  razao_social COMMENT 'Nome empresarial do cliente',
  segmento COMMENT 'Segmento comercial do cliente',
  cidade COMMENT 'Cidade do cliente',
  data_referencia COMMENT 'Data mais recente disponível na fato, usada para medir inatividade',
  data_ultimo_pedido COMMENT 'Data da compra mais recente do cliente',
  dias_sem_comprar COMMENT 'Dias entre a data de referência e a última compra',
  meses_com_compra COMMENT 'Quantidade de meses distintos em que o cliente comprou',
  receita_acumulada COMMENT 'Receita líquida acumulada do cliente antes de entrar em risco',
  receita_media_mensal COMMENT 'Receita acumulada dividida pelos meses em que o cliente comprou'
)
COMMENT 'Quais clientes estão há mais de 90 dias sem comprar e quanto compravam por mês antes de sumir?'
AS
WITH referencia AS (
  SELECT MAX(data_pedido) AS data_referencia
  FROM lakehouse_rotaperfume.gold.fato_vendas
),
historico AS (
  SELECT
    cliente_id,
    MAX(data_pedido) AS data_ultimo_pedido,
    CAST(SUM(receita) AS DECIMAL(18, 2)) AS receita_acumulada,
    COUNT(DISTINCT DATE_TRUNC('MONTH', data_pedido)) AS meses_com_compra
  FROM lakehouse_rotaperfume.gold.fato_vendas
  GROUP BY cliente_id
)
SELECT
  h.cliente_id,
  c.cnpj,
  c.razao_social,
  c.segmento,
  c.cidade,
  r.data_referencia,
  h.data_ultimo_pedido,
  DATEDIFF(r.data_referencia, h.data_ultimo_pedido) AS dias_sem_comprar,
  h.meses_com_compra,
  h.receita_acumulada,
  CAST(h.receita_acumulada / NULLIF(h.meses_com_compra, 0) AS DECIMAL(18, 2)) AS receita_media_mensal
FROM historico h
INNER JOIN lakehouse_rotaperfume.gold.dim_cliente c ON c.cliente_id = h.cliente_id
CROSS JOIN referencia r
WHERE DATEDIFF(r.data_referencia, h.data_ultimo_pedido) > 90;

CREATE OR REPLACE VIEW lakehouse_rotaperfume.gold.efeito_lancamento (
  sku COMMENT 'Identificador do produto lançado',
  descricao COMMENT 'Descrição comercial do produto',
  marca COMMENT 'Marca comercial do produto',
  categoria COMMENT 'Categoria comercial do produto',
  data_lancamento COMMENT 'Data de lançamento informada no catálogo',
  receita_primeiros_120_dias COMMENT 'Receita líquida do lançamento até 119 dias depois',
  receita_resto_periodo COMMENT 'Receita líquida fora dos primeiros 120 dias após o lançamento',
  diferenca_receita COMMENT 'Receita dos primeiros 120 dias menos a receita do restante do período'
)
COMMENT 'Quanto cada SKU faturou nos primeiros 120 dias após o lançamento em comparação com o restante do período?'
AS
WITH resumo AS (
  SELECT
    p.sku,
    p.descricao,
    p.marca,
    p.categoria,
    p.data_lancamento,
    CAST(SUM(
      CASE
        WHEN DATEDIFF(f.data_pedido, p.data_lancamento) BETWEEN 0 AND 119 THEN COALESCE(f.receita, 0)
        ELSE 0
      END
    ) AS DECIMAL(18, 2)) AS receita_primeiros_120_dias,
    CAST(SUM(
      CASE
        WHEN DATEDIFF(f.data_pedido, p.data_lancamento) BETWEEN 0 AND 119 THEN 0
        ELSE COALESCE(f.receita, 0)
      END
    ) AS DECIMAL(18, 2)) AS receita_resto_periodo
  FROM lakehouse_rotaperfume.gold.dim_produto p
  LEFT JOIN lakehouse_rotaperfume.gold.fato_vendas f ON f.sku = p.sku
  GROUP BY p.sku, p.descricao, p.marca, p.categoria, p.data_lancamento
)
SELECT
  sku,
  descricao,
  marca,
  categoria,
  data_lancamento,
  receita_primeiros_120_dias,
  receita_resto_periodo,
  CAST(receita_primeiros_120_dias - receita_resto_periodo AS DECIMAL(18, 2)) AS diferenca_receita
FROM resumo;

CREATE OR REPLACE VIEW lakehouse_rotaperfume.gold.ruptura_por_marca (
  marca COMMENT 'Marca comercial do produto em estoque',
  snapshots COMMENT 'Quantidade de observações de estoque da marca',
  snapshots_em_ruptura COMMENT 'Quantidade de observações com saldo igual a zero',
  ruptura_pct COMMENT 'Percentual das observações de estoque em ruptura'
)
COMMENT 'Quais marcas ficam sem estoque com maior frequência nos snapshots disponíveis?'
AS
SELECT
  p.marca,
  COUNT(*) AS snapshots,
  SUM(CASE WHEN e.ruptura THEN 1 ELSE 0 END) AS snapshots_em_ruptura,
  CAST(
    100 * SUM(CASE WHEN e.ruptura THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0)
    AS DECIMAL(18, 2)
  ) AS ruptura_pct
FROM lakehouse_rotaperfume.silver.estoque e
INNER JOIN lakehouse_rotaperfume.gold.dim_produto p ON p.sku = e.sku
GROUP BY p.marca;

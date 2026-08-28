-- CONTRATO DE GRÃO E FILTRO
-- Granularidade: uma linha por item de pedido.
-- Filtro: pedidos cancelados são excluídos; devoluções permanecem com quantidade e receita negativas.
-- Receita: quantidade assinada multiplicada pelo preço praticado.
-- Custo: quantidade assinada multiplicada pelo custo unitário do produto.
-- Margem: receita menos custo do produto.

SET ANSI_MODE = TRUE;

CREATE OR REPLACE TABLE lakehouse_rotaperfume.gold.fato_vendas
USING DELTA
PARTITIONED BY (ano, mes)
COMMENT 'Fato transacional de vendas no grão de item, incluindo devoluções e excluindo pedidos cancelados'
AS
WITH mapa_cliente AS (
  SELECT
    cliente_id AS cliente_id_canonico,
    cliente_id AS cliente_id_pedido,
    razao_social,
    segmento,
    cidade
  FROM lakehouse_rotaperfume.silver.clientes

  UNION ALL

  SELECT
    c.cliente_id AS cliente_id_canonico,
    id_duplicado AS cliente_id_pedido,
    c.razao_social,
    c.segmento,
    c.cidade
  FROM lakehouse_rotaperfume.silver.clientes c
  LATERAL VIEW EXPLODE(c.cliente_ids_duplicados) ids AS id_duplicado
),
vendas AS (
  SELECT
    i.item_id,
    p.pedido_id,
    p.data_pedido,
    p.canal,
    c.cliente_id_canonico AS cliente_id,
    c.razao_social,
    c.segmento,
    c.cidade,
    p.vendedor_id,
    i.sku,
    pr.categoria,
    pr.marca,
    pr.nota_olfativa,
    i.quantidade,
    i.preco_praticado,
    CAST(i.quantidade * i.preco_praticado AS DECIMAL(18, 2)) AS receita,
    CAST(i.quantidade * pr.custo_unitario AS DECIMAL(18, 2)) AS custo,
    i.devolucao,
    p.ano,
    p.mes
  FROM lakehouse_rotaperfume.silver.pedidos p
  INNER JOIN lakehouse_rotaperfume.silver.itens_pedido i ON p.pedido_id = i.pedido_id
  INNER JOIN mapa_cliente c ON p.cliente_id = c.cliente_id_pedido
  INNER JOIN lakehouse_rotaperfume.silver.produtos pr ON i.sku = pr.sku
  WHERE NOT p.cancelado
)
SELECT
  item_id,
  pedido_id,
  data_pedido,
  canal,
  cliente_id,
  razao_social,
  segmento,
  cidade,
  vendedor_id,
  sku,
  categoria,
  marca,
  nota_olfativa,
  quantidade,
  preco_praticado,
  receita,
  custo,
  CAST(receita - custo AS DECIMAL(18, 2)) AS margem,
  devolucao,
  ano,
  mes
FROM vendas;

COMMENT ON COLUMN lakehouse_rotaperfume.gold.fato_vendas.item_id IS
  'Identificador do item que define a granularidade da venda';
COMMENT ON COLUMN lakehouse_rotaperfume.gold.fato_vendas.pedido_id IS
  'Pedido comercial ao qual o item pertence';
COMMENT ON COLUMN lakehouse_rotaperfume.gold.fato_vendas.data_pedido IS
  'Data em que o pedido comercial foi realizado';
COMMENT ON COLUMN lakehouse_rotaperfume.gold.fato_vendas.ano IS
  'Ano da realização do pedido, usado no acompanhamento temporal';
COMMENT ON COLUMN lakehouse_rotaperfume.gold.fato_vendas.mes IS
  'Número do mês da realização do pedido';
COMMENT ON COLUMN lakehouse_rotaperfume.gold.fato_vendas.canal IS
  'Canal comercial usado para originar o pedido';
COMMENT ON COLUMN lakehouse_rotaperfume.gold.fato_vendas.cliente_id IS
  'Cliente canônico após a consolidação de cadastros com o mesmo CNPJ';
COMMENT ON COLUMN lakehouse_rotaperfume.gold.fato_vendas.razao_social IS
  'Nome empresarial do cliente responsável pela compra';
COMMENT ON COLUMN lakehouse_rotaperfume.gold.fato_vendas.segmento IS
  'Segmento comercial em que o cliente atua';
COMMENT ON COLUMN lakehouse_rotaperfume.gold.fato_vendas.cidade IS
  'Cidade do cliente no momento da consolidação da Gold';
COMMENT ON COLUMN lakehouse_rotaperfume.gold.fato_vendas.vendedor_id IS
  'Vendedor responsável pelo pedido';
COMMENT ON COLUMN lakehouse_rotaperfume.gold.fato_vendas.sku IS
  'Produto vendido ou devolvido no item';
COMMENT ON COLUMN lakehouse_rotaperfume.gold.fato_vendas.categoria IS
  'Categoria comercial do produto';
COMMENT ON COLUMN lakehouse_rotaperfume.gold.fato_vendas.marca IS
  'Marca comercial do produto';
COMMENT ON COLUMN lakehouse_rotaperfume.gold.fato_vendas.nota_olfativa IS
  'Família de aroma predominante do produto';
COMMENT ON COLUMN lakehouse_rotaperfume.gold.fato_vendas.quantidade IS
  'Unidades movimentadas; valor negativo representa devolução';
COMMENT ON COLUMN lakehouse_rotaperfume.gold.fato_vendas.preco_praticado IS
  'Preço unitário efetivamente praticado no item';
COMMENT ON COLUMN lakehouse_rotaperfume.gold.fato_vendas.receita IS
  'Quantidade multiplicada pelo preço praticado. Devoluções reduzem a receita';
COMMENT ON COLUMN lakehouse_rotaperfume.gold.fato_vendas.custo IS
  'Quantidade multiplicada pelo custo unitário. Devoluções reduzem o custo reconhecido';
COMMENT ON COLUMN lakehouse_rotaperfume.gold.fato_vendas.margem IS
  'Receita menos custo do produto. Não considera desconto comercial nem frete.';
COMMENT ON COLUMN lakehouse_rotaperfume.gold.fato_vendas.devolucao IS
  'Identifica item devolvido, mantido na apuração para reconciliar a receita líquida';

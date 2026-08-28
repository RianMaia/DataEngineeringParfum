SET ANSI_MODE = TRUE;

CREATE OR REPLACE TABLE lakehouse_rotaperfume.silver.produtos
COMMENT 'Cadastro de produtos ERP tipado, com datas tolerantes a formatos mistos e situação convertida para booleano'
AS
SELECT
  TRIM(sku) AS sku,
  TRIM(descricao) AS descricao,
  TRIM(categoria) AS categoria,
  TRIM(marca) AS marca,
  TRIM(nota_olfativa) AS nota_olfativa,
  CAST(preco_tabela AS DECIMAL(18, 2)) AS preco_tabela,
  CAST(custo_unitario AS DECIMAL(18, 2)) AS custo_unitario,
  TRIM(unidade) AS unidade,
  CASE UPPER(TRIM(ativo)) WHEN 'S' THEN TRUE WHEN 'N' THEN FALSE END AS ativo,
  COALESCE(
    TRY_TO_DATE(TRIM(data_lancamento), 'yyyy-MM-dd'),
    TRY_TO_DATE(TRIM(data_lancamento), 'dd/MM/yyyy')
  ) AS data_lancamento,
  CURRENT_TIMESTAMP() AS _processado_em,
  (SELECT COUNT(*) FROM lakehouse_rotaperfume.bronze.produtos) AS _linhas_origem
FROM lakehouse_rotaperfume.bronze.produtos;

COMMENT ON COLUMN lakehouse_rotaperfume.silver.produtos.ativo IS
  'Indicador booleano derivado de S ou N na origem';
COMMENT ON COLUMN lakehouse_rotaperfume.silver.produtos.data_lancamento IS
  'Data convertida com try_to_date para aceitar yyyy-MM-dd e dd/MM/yyyy sem abortar em valor inválido';
COMMENT ON COLUMN lakehouse_rotaperfume.silver.produtos._processado_em IS
  'Instante de processamento da camada Silver';
COMMENT ON COLUMN lakehouse_rotaperfume.silver.produtos._linhas_origem IS
  'Quantidade total de linhas lidas da tabela Bronze';

CREATE OR REPLACE TABLE lakehouse_rotaperfume.silver.itens_pedido
COMMENT 'Itens de pedido ERP tipados; quantidades negativas são preservadas e identificadas como devolução'
AS
WITH tipados AS (
  SELECT
    CAST(item_id AS BIGINT) AS item_id,
    CAST(pedido_id AS BIGINT) AS pedido_id,
    TRIM(sku) AS sku,
    CAST(quantidade AS INT) AS quantidade,
    CAST(preco_praticado AS DECIMAL(18, 2)) AS preco_praticado,
    CAST(desconto_pct AS DECIMAL(18, 2)) AS desconto_pct,
    CAST(valor_bruto AS DECIMAL(18, 2)) AS valor_bruto
  FROM lakehouse_rotaperfume.bronze.itens_pedido
)
SELECT
  i.item_id,
  i.pedido_id,
  i.sku,
  i.quantidade,
  i.quantidade < 0 AS devolucao,
  ABS(i.quantidade) AS quantidade_abs,
  i.preco_praticado,
  i.desconto_pct,
  i.valor_bruto,
  NOT p.ativo AS sku_descontinuado,
  CURRENT_TIMESTAMP() AS _processado_em,
  (SELECT COUNT(*) FROM lakehouse_rotaperfume.bronze.itens_pedido) AS _linhas_origem
FROM tipados i
LEFT JOIN lakehouse_rotaperfume.silver.produtos p ON i.sku = p.sku;

COMMENT ON COLUMN lakehouse_rotaperfume.silver.itens_pedido.quantidade IS
  'Quantidade original preservada; valores negativos representam devoluções legítimas';
COMMENT ON COLUMN lakehouse_rotaperfume.silver.itens_pedido.devolucao IS
  'Verdadeiro quando a quantidade original é negativa; nenhuma devolução é descartada';
COMMENT ON COLUMN lakehouse_rotaperfume.silver.itens_pedido.quantidade_abs IS
  'Módulo inteiro da quantidade, usado para medir unidades sem perder a direção da operação';
COMMENT ON COLUMN lakehouse_rotaperfume.silver.itens_pedido.sku_descontinuado IS
  'Verdadeiro quando o SKU existe no cadastro e o produto está inativo';
COMMENT ON COLUMN lakehouse_rotaperfume.silver.itens_pedido._processado_em IS
  'Instante de processamento da camada Silver';
COMMENT ON COLUMN lakehouse_rotaperfume.silver.itens_pedido._linhas_origem IS
  'Quantidade total de linhas lidas da tabela Bronze';

ALTER TABLE lakehouse_rotaperfume.silver.itens_pedido
  DROP CONSTRAINT IF EXISTS itens_quantidade_positiva;
ALTER TABLE lakehouse_rotaperfume.silver.itens_pedido
  ADD CONSTRAINT itens_quantidade_positiva CHECK (quantidade_abs > 0);

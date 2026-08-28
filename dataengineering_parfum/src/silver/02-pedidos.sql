SET ANSI_MODE = TRUE;

CREATE OR REPLACE TABLE lakehouse_rotaperfume.silver.pedidos
COMMENT 'Pedidos ERP tipados, com tratamento explícito de cancelamentos e preservação de saldos negativos legítimos'
AS
WITH tipados AS (
  SELECT
    CAST(pedido_id AS BIGINT) AS pedido_id,
    CAST(cliente_id AS BIGINT) AS cliente_id,
    CAST(vendedor_id AS BIGINT) AS vendedor_id,
    COALESCE(
      TRY_TO_DATE(TRIM(data_pedido), 'yyyy-MM-dd'),
      TRY_TO_DATE(TRIM(data_pedido), 'dd/MM/yyyy')
    ) AS data_pedido,
    TRIM(canal) AS canal,
    TRIM(status) AS status,
    CAST(valor_total AS DECIMAL(18, 2)) AS valor_total,
    LOWER(TRIM(status)) = 'cancelado' AS cancelado
  FROM lakehouse_rotaperfume.bronze.pedidos
)
SELECT
  pedido_id,
  cliente_id,
  vendedor_id,
  data_pedido,
  canal,
  status,
  valor_total,
  cancelado,
  CAST(CASE WHEN cancelado THEN 0 ELSE valor_total END AS DECIMAL(18, 2)) AS valor_liquido,
  YEAR(data_pedido) AS ano,
  MONTH(data_pedido) AS mes,
  CURRENT_TIMESTAMP() AS _processado_em,
  (SELECT COUNT(*) FROM lakehouse_rotaperfume.bronze.pedidos) AS _linhas_origem
FROM tipados;

COMMENT ON COLUMN lakehouse_rotaperfume.silver.pedidos.data_pedido IS
  'Data convertida com try_to_date para aceitar yyyy-MM-dd e dd/MM/yyyy sem abortar em valor inválido';
COMMENT ON COLUMN lakehouse_rotaperfume.silver.pedidos.valor_total IS
  'Valor textual da origem convertido para DECIMAL(18,2), inclusive quando negativo por devolução legítima';
COMMENT ON COLUMN lakehouse_rotaperfume.silver.pedidos.cancelado IS
  'Indicador booleano derivado do status Cancelado';
COMMENT ON COLUMN lakehouse_rotaperfume.silver.pedidos.valor_liquido IS
  'Zero para pedido cancelado; caso contrário preserva valor_total, inclusive saldos negativos de devolução';
COMMENT ON COLUMN lakehouse_rotaperfume.silver.pedidos.ano IS
  'Ano derivado da data_pedido já validada';
COMMENT ON COLUMN lakehouse_rotaperfume.silver.pedidos.mes IS
  'Mês derivado da data_pedido já validada';
COMMENT ON COLUMN lakehouse_rotaperfume.silver.pedidos._processado_em IS
  'Instante de processamento da camada Silver';
COMMENT ON COLUMN lakehouse_rotaperfume.silver.pedidos._linhas_origem IS
  'Quantidade total de linhas lidas da tabela Bronze';

ALTER TABLE lakehouse_rotaperfume.silver.pedidos
  DROP CONSTRAINT IF EXISTS pedidos_data_pedido_obrigatoria;
ALTER TABLE lakehouse_rotaperfume.silver.pedidos
  ADD CONSTRAINT pedidos_data_pedido_obrigatoria CHECK (data_pedido IS NOT NULL);
ALTER TABLE lakehouse_rotaperfume.silver.pedidos
  DROP CONSTRAINT IF EXISTS pedidos_cancelados_zerados;
ALTER TABLE lakehouse_rotaperfume.silver.pedidos
  ADD CONSTRAINT pedidos_cancelados_zerados CHECK (NOT cancelado OR valor_liquido = 0);

SET ANSI_MODE = TRUE;

CREATE OR REPLACE TABLE lakehouse_rotaperfume.silver.clientes
COMMENT 'Clientes CRM normalizados e deduplicados por CNPJ, preservando rastreabilidade dos IDs descartados'
AS
WITH normalizados AS (
  SELECT
    CAST(cliente_id AS BIGINT) AS cliente_id,
    LPAD(REGEXP_REPLACE(TRIM(cnpj), '[^0-9]', ''), 14, '0') AS cnpj,
    INITCAP(REGEXP_REPLACE(TRIM(razao_social), '[[:space:]]+', ' ')) AS razao_social,
    TRIM(segmento) AS segmento,
    TRIM(cidade) AS cidade,
    UPPER(TRIM(uf)) AS uf,
    TRIM(bairro) AS bairro,
    COALESCE(
      TRY_TO_DATE(TRIM(data_cadastro), 'yyyy-MM-dd'),
      TRY_TO_DATE(TRIM(data_cadastro), 'dd/MM/yyyy')
    ) AS data_cadastro,
    CASE UPPER(TRIM(ativo)) WHEN 'S' THEN TRUE WHEN 'N' THEN FALSE END AS ativo
  FROM lakehouse_rotaperfume.bronze.clientes
),
ids_por_cnpj AS (
  SELECT cnpj, SORT_ARRAY(COLLECT_SET(cliente_id)) AS cliente_ids
  FROM normalizados
  GROUP BY cnpj
),
ranqueados AS (
  SELECT
    n.*,
    FILTER(i.cliente_ids, id -> id <> n.cliente_id) AS cliente_ids_duplicados,
    ROW_NUMBER() OVER (
      PARTITION BY n.cnpj
      ORDER BY n.data_cadastro ASC NULLS LAST, n.cliente_id ASC
    ) AS ordem_cadastro
  FROM normalizados n
  INNER JOIN ids_por_cnpj i ON n.cnpj = i.cnpj
)
SELECT
  cliente_id,
  cnpj,
  razao_social,
  segmento,
  cidade,
  uf,
  bairro,
  data_cadastro,
  ativo,
  cliente_ids_duplicados,
  CURRENT_TIMESTAMP() AS _processado_em,
  (SELECT COUNT(*) FROM lakehouse_rotaperfume.bronze.clientes) AS _linhas_origem
FROM ranqueados
WHERE ordem_cadastro = 1;

COMMENT ON COLUMN lakehouse_rotaperfume.silver.clientes.cnpj IS
  'CNPJ como STRING de 14 dígitos após trim, remoção de pontuação e lpad; nunca convertido para número';
COMMENT ON COLUMN lakehouse_rotaperfume.silver.clientes.razao_social IS
  'Razão social com espaços colapsados e capitalização padronizada por initcap';
COMMENT ON COLUMN lakehouse_rotaperfume.silver.clientes.data_cadastro IS
  'Data convertida com try_to_date para aceitar yyyy-MM-dd e dd/MM/yyyy sem abortar em valor inválido';
COMMENT ON COLUMN lakehouse_rotaperfume.silver.clientes.ativo IS
  'Indicador booleano derivado de S ou N na origem';
COMMENT ON COLUMN lakehouse_rotaperfume.silver.clientes.cliente_ids_duplicados IS
  'IDs descartados na deduplicação por CNPJ; permanece o cadastro mais antigo';
COMMENT ON COLUMN lakehouse_rotaperfume.silver.clientes._processado_em IS
  'Instante de processamento da camada Silver';
COMMENT ON COLUMN lakehouse_rotaperfume.silver.clientes._linhas_origem IS
  'Quantidade total de linhas lidas da tabela Bronze antes da deduplicação';

ALTER TABLE lakehouse_rotaperfume.silver.clientes
  DROP CONSTRAINT IF EXISTS clientes_cnpj_14;
ALTER TABLE lakehouse_rotaperfume.silver.clientes
  ADD CONSTRAINT clientes_cnpj_14 CHECK (LENGTH(cnpj) = 14);
ALTER TABLE lakehouse_rotaperfume.silver.clientes
  DROP CONSTRAINT IF EXISTS clientes_data_cadastro_obrigatoria;
ALTER TABLE lakehouse_rotaperfume.silver.clientes
  ADD CONSTRAINT clientes_data_cadastro_obrigatoria CHECK (data_cadastro IS NOT NULL);

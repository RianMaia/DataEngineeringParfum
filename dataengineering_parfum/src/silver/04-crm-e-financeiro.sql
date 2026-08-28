SET ANSI_MODE = TRUE;

CREATE OR REPLACE TABLE lakehouse_rotaperfume.silver.vendedores
COMMENT 'Vendedores CRM tipados, incluindo admissão, desligamento e meta mensal'
AS
SELECT
  CAST(vendedor_id AS BIGINT) AS vendedor_id,
  TRIM(nome) AS nome,
  TRIM(regiao) AS regiao,
  UPPER(TRIM(uf)) AS uf,
  COALESCE(
    TRY_TO_DATE(TRIM(data_admissao), 'yyyy-MM-dd'),
    TRY_TO_DATE(TRIM(data_admissao), 'dd/MM/yyyy')
  ) AS data_admissao,
  COALESCE(
    TRY_TO_DATE(TRIM(data_desligamento), 'yyyy-MM-dd'),
    TRY_TO_DATE(TRIM(data_desligamento), 'dd/MM/yyyy')
  ) AS data_desligamento,
  CAST(meta_mensal AS DECIMAL(18, 2)) AS meta_mensal,
  CURRENT_TIMESTAMP() AS _processado_em,
  (SELECT COUNT(*) FROM lakehouse_rotaperfume.bronze.vendedores) AS _linhas_origem
FROM lakehouse_rotaperfume.bronze.vendedores;

COMMENT ON COLUMN lakehouse_rotaperfume.silver.vendedores.data_admissao IS
  'Data convertida com try_to_date nos formatos yyyy-MM-dd e dd/MM/yyyy';
COMMENT ON COLUMN lakehouse_rotaperfume.silver.vendedores.data_desligamento IS
  'Data opcional convertida com try_to_date nos formatos yyyy-MM-dd e dd/MM/yyyy';
COMMENT ON COLUMN lakehouse_rotaperfume.silver.vendedores._processado_em IS
  'Instante de processamento da camada Silver';
COMMENT ON COLUMN lakehouse_rotaperfume.silver.vendedores._linhas_origem IS
  'Quantidade total de linhas lidas da tabela Bronze';

CREATE OR REPLACE TABLE lakehouse_rotaperfume.silver.carteira
COMMENT 'Carteira cliente-vendedor tipada, expondo atribuições abertas para vendedores desligados sem corrigir a origem'
AS
WITH tipados AS (
  SELECT
    CAST(c.carteira_id AS BIGINT) AS carteira_id,
    CAST(c.cliente_id AS BIGINT) AS cliente_id,
    CAST(c.vendedor_id AS BIGINT) AS vendedor_id,
    COALESCE(
      TRY_TO_DATE(TRIM(c.data_inicio), 'yyyy-MM-dd'),
      TRY_TO_DATE(TRIM(c.data_inicio), 'dd/MM/yyyy')
    ) AS data_inicio,
    COALESCE(
      TRY_TO_DATE(TRIM(c.data_fim), 'yyyy-MM-dd'),
      TRY_TO_DATE(TRIM(c.data_fim), 'dd/MM/yyyy')
    ) AS data_fim,
    v.data_desligamento
  FROM lakehouse_rotaperfume.bronze.carteira c
  LEFT JOIN lakehouse_rotaperfume.silver.vendedores v
    ON CAST(c.vendedor_id AS BIGINT) = v.vendedor_id
)
SELECT
  carteira_id,
  cliente_id,
  vendedor_id,
  data_inicio,
  data_fim,
  (data_fim IS NULL OR data_fim >= CURRENT_DATE())
    AND (data_desligamento IS NULL OR data_desligamento > CURRENT_DATE()) AS vigente,
  data_fim IS NULL AND data_desligamento IS NOT NULL AS orfao_vendedor_desligado,
  CURRENT_TIMESTAMP() AS _processado_em,
  (SELECT COUNT(*) FROM lakehouse_rotaperfume.bronze.carteira) AS _linhas_origem
FROM tipados;

COMMENT ON COLUMN lakehouse_rotaperfume.silver.carteira.data_inicio IS
  'Data convertida com try_to_date nos formatos yyyy-MM-dd e dd/MM/yyyy';
COMMENT ON COLUMN lakehouse_rotaperfume.silver.carteira.data_fim IS
  'Data opcional convertida com try_to_date nos formatos yyyy-MM-dd e dd/MM/yyyy';
COMMENT ON COLUMN lakehouse_rotaperfume.silver.carteira.vigente IS
  'Verdadeiro somente se a carteira não terminou e o vendedor ainda não foi desligado';
COMMENT ON COLUMN lakehouse_rotaperfume.silver.carteira.orfao_vendedor_desligado IS
  'Expõe carteira sem data_fim vinculada a vendedor desligado; o dado original não é corrigido';
COMMENT ON COLUMN lakehouse_rotaperfume.silver.carteira._processado_em IS
  'Instante de processamento da camada Silver';
COMMENT ON COLUMN lakehouse_rotaperfume.silver.carteira._linhas_origem IS
  'Quantidade total de linhas lidas da tabela Bronze';

CREATE OR REPLACE TABLE lakehouse_rotaperfume.silver.oportunidades
COMMENT 'Oportunidades CRM tipadas, com resultado derivado das etapas exatas observadas na origem'
AS
SELECT
  CAST(oportunidade_id AS BIGINT) AS oportunidade_id,
  CAST(cliente_id AS BIGINT) AS cliente_id,
  CAST(vendedor_id AS BIGINT) AS vendedor_id,
  TRIM(origem) AS origem,
  COALESCE(
    TRY_TO_DATE(TRIM(data_abertura), 'yyyy-MM-dd'),
    TRY_TO_DATE(TRIM(data_abertura), 'dd/MM/yyyy')
  ) AS data_abertura,
  TRIM(etapa) AS etapa,
  CAST(probabilidade_pct AS INT) AS probabilidade_pct,
  CAST(valor_estimado AS DECIMAL(18, 2)) AS valor_estimado,
  COALESCE(
    TRY_TO_DATE(TRIM(data_fechamento), 'yyyy-MM-dd'),
    TRY_TO_DATE(TRIM(data_fechamento), 'dd/MM/yyyy')
  ) AS data_fechamento,
  CAST(NULLIF(TRIM(ciclo_dias), '') AS INT) AS ciclo_dias,
  NULLIF(TRIM(motivo_perda), '') AS motivo_perda,
  CASE TRIM(etapa)
    WHEN 'Fechado ganho' THEN 'GANHA'
    WHEN 'Fechado perdido' THEN 'PERDIDA'
    ELSE 'ABERTA'
  END AS resultado_oportunidade,
  CURRENT_TIMESTAMP() AS _processado_em,
  (SELECT COUNT(*) FROM lakehouse_rotaperfume.bronze.oportunidades) AS _linhas_origem
FROM lakehouse_rotaperfume.bronze.oportunidades;

COMMENT ON COLUMN lakehouse_rotaperfume.silver.oportunidades.data_abertura IS
  'Data convertida com try_to_date nos formatos yyyy-MM-dd e dd/MM/yyyy';
COMMENT ON COLUMN lakehouse_rotaperfume.silver.oportunidades.data_fechamento IS
  'Data opcional convertida com try_to_date nos formatos yyyy-MM-dd e dd/MM/yyyy';
COMMENT ON COLUMN lakehouse_rotaperfume.silver.oportunidades.resultado_oportunidade IS
  'Classificação baseada nos valores exatos Fechado ganho e Fechado perdido confirmados na origem';
COMMENT ON COLUMN lakehouse_rotaperfume.silver.oportunidades._processado_em IS
  'Instante de processamento da camada Silver';
COMMENT ON COLUMN lakehouse_rotaperfume.silver.oportunidades._linhas_origem IS
  'Quantidade total de linhas lidas da tabela Bronze';

CREATE OR REPLACE TABLE lakehouse_rotaperfume.silver.visitas
COMMENT 'Visitas CRM tipadas e preservadas em granularidade de evento'
AS
SELECT
  CAST(visita_id AS BIGINT) AS visita_id,
  CAST(cliente_id AS BIGINT) AS cliente_id,
  CAST(vendedor_id AS BIGINT) AS vendedor_id,
  COALESCE(
    TRY_TO_DATE(TRIM(data_visita), 'yyyy-MM-dd'),
    TRY_TO_DATE(TRIM(data_visita), 'dd/MM/yyyy')
  ) AS data_visita,
  TRIM(resultado) AS resultado,
  CAST(duracao_min AS INT) AS duracao_min,
  CURRENT_TIMESTAMP() AS _processado_em,
  (SELECT COUNT(*) FROM lakehouse_rotaperfume.bronze.visitas) AS _linhas_origem
FROM lakehouse_rotaperfume.bronze.visitas;

COMMENT ON COLUMN lakehouse_rotaperfume.silver.visitas.data_visita IS
  'Data convertida com try_to_date nos formatos yyyy-MM-dd e dd/MM/yyyy';
COMMENT ON COLUMN lakehouse_rotaperfume.silver.visitas._processado_em IS
  'Instante de processamento da camada Silver';
COMMENT ON COLUMN lakehouse_rotaperfume.silver.visitas._linhas_origem IS
  'Quantidade total de linhas lidas da tabela Bronze';

CREATE OR REPLACE TABLE lakehouse_rotaperfume.silver.pagamentos
COMMENT 'Pagamentos ERP tipados, preservando datas opcionais e valores financeiros em DECIMAL(18,2)'
AS
SELECT
  CAST(pagamento_id AS BIGINT) AS pagamento_id,
  CAST(pedido_id AS BIGINT) AS pedido_id,
  TRIM(forma_pagamento) AS forma_pagamento,
  CAST(parcelas AS INT) AS parcelas,
  CAST(valor AS DECIMAL(18, 2)) AS valor,
  CAST(taxa_pct AS DECIMAL(18, 2)) AS taxa_pct,
  CAST(valor_liquido AS DECIMAL(18, 2)) AS valor_liquido,
  COALESCE(
    TRY_TO_DATE(TRIM(data_vencimento), 'yyyy-MM-dd'),
    TRY_TO_DATE(TRIM(data_vencimento), 'dd/MM/yyyy')
  ) AS data_vencimento,
  COALESCE(
    TRY_TO_DATE(TRIM(data_pagamento), 'yyyy-MM-dd'),
    TRY_TO_DATE(TRIM(data_pagamento), 'dd/MM/yyyy')
  ) AS data_pagamento,
  TRIM(status_pagamento) AS status_pagamento,
  CURRENT_TIMESTAMP() AS _processado_em,
  (SELECT COUNT(*) FROM lakehouse_rotaperfume.bronze.pagamentos) AS _linhas_origem
FROM lakehouse_rotaperfume.bronze.pagamentos;

COMMENT ON COLUMN lakehouse_rotaperfume.silver.pagamentos.data_vencimento IS
  'Data convertida com try_to_date nos formatos yyyy-MM-dd e dd/MM/yyyy';
COMMENT ON COLUMN lakehouse_rotaperfume.silver.pagamentos.data_pagamento IS
  'Data opcional convertida com try_to_date nos formatos yyyy-MM-dd e dd/MM/yyyy';
COMMENT ON COLUMN lakehouse_rotaperfume.silver.pagamentos._processado_em IS
  'Instante de processamento da camada Silver';
COMMENT ON COLUMN lakehouse_rotaperfume.silver.pagamentos._linhas_origem IS
  'Quantidade total de linhas lidas da tabela Bronze';

CREATE OR REPLACE TABLE lakehouse_rotaperfume.silver.estoque
COMMENT 'Snapshots de estoque ERP tipados, com ruptura recalculada objetivamente a partir do saldo'
AS
SELECT
  COALESCE(
    TRY_TO_DATE(TRIM(data_snapshot), 'yyyy-MM-dd'),
    TRY_TO_DATE(TRIM(data_snapshot), 'dd/MM/yyyy')
  ) AS data_snapshot,
  TRIM(sku) AS sku,
  CAST(saldo AS INT) AS saldo,
  CAST(saldo AS INT) = 0 AS ruptura,
  CURRENT_TIMESTAMP() AS _processado_em,
  (SELECT COUNT(*) FROM lakehouse_rotaperfume.bronze.estoque) AS _linhas_origem
FROM lakehouse_rotaperfume.bronze.estoque;

COMMENT ON COLUMN lakehouse_rotaperfume.silver.estoque.data_snapshot IS
  'Data convertida com try_to_date nos formatos yyyy-MM-dd e dd/MM/yyyy';
COMMENT ON COLUMN lakehouse_rotaperfume.silver.estoque.ruptura IS
  'Indicador booleano recalculado como saldo igual a zero, sem confiar na flag textual da origem';
COMMENT ON COLUMN lakehouse_rotaperfume.silver.estoque._processado_em IS
  'Instante de processamento da camada Silver';
COMMENT ON COLUMN lakehouse_rotaperfume.silver.estoque._linhas_origem IS
  'Quantidade total de linhas lidas da tabela Bronze';

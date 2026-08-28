-- A auditoria é bloqueante: objetos sem comentário não estão prontos para consumo pelo Genie.
WITH objetos_esperados AS (
  SELECT EXPLODE(ARRAY(
    'receita_mensal',
    'ranking_marcas',
    'margem_por_categoria',
    'clientes_em_risco',
    'efeito_lancamento',
    'ruptura_por_marca'
  )) AS table_name
),
objetos_com_problema AS (
  SELECT CONCAT(t.table_name, ': comentário ausente') AS problema
  FROM lakehouse_rotaperfume.information_schema.tables t
  WHERE t.table_schema = 'gold'
    AND NULLIF(TRIM(t.comment), '') IS NULL

  UNION ALL

  SELECT CONCAT(e.table_name, ': objeto ausente') AS problema
  FROM objetos_esperados e
  LEFT JOIN lakehouse_rotaperfume.information_schema.tables t
    ON t.table_schema = 'gold' AND t.table_name = e.table_name
  WHERE t.table_name IS NULL
)
SELECT
  CASE
    WHEN COUNT(*) = 0 THEN 'PASSOU: todos os objetos Gold têm COMMENT'
    ELSE RAISE_ERROR(CONCAT(
      'Auditoria de metadado falhou nos objetos: ',
      CONCAT_WS(', ', SORT_ARRAY(COLLECT_LIST(problema)))
    ))
  END AS auditoria_objetos
FROM objetos_com_problema;

-- Toda coluna da fato e das seis views precisa explicar seu significado de negócio.
WITH colunas_sem_comentario AS (
  SELECT CONCAT(table_name, '.', column_name) AS coluna
  FROM lakehouse_rotaperfume.information_schema.columns
  WHERE table_schema = 'gold'
    AND table_name IN (
      'fato_vendas',
      'receita_mensal',
      'ranking_marcas',
      'margem_por_categoria',
      'clientes_em_risco',
      'efeito_lancamento',
      'ruptura_por_marca'
    )
    AND NULLIF(TRIM(comment), '') IS NULL
)
SELECT
  CASE
    WHEN COUNT(*) = 0 THEN 'PASSOU: todas as colunas críticas têm COMMENT'
    ELSE RAISE_ERROR(CONCAT(
      'Auditoria de metadado falhou nas colunas: ',
      CONCAT_WS(', ', SORT_ARRAY(COLLECT_LIST(coluna)))
    ))
  END AS auditoria_colunas
FROM colunas_sem_comentario;

-- Relatório final, informativo, para apresentar a cobertura a consumidores da Gold.
SELECT
  t.table_name AS objeto,
  t.table_type AS tipo,
  CASE WHEN NULLIF(TRIM(t.comment), '') IS NULL THEN 'NÃO' ELSE 'SIM' END AS objeto_comentado,
  COUNT(c.column_name) AS total_colunas,
  SUM(CASE WHEN NULLIF(TRIM(c.comment), '') IS NULL THEN 0 ELSE 1 END) AS colunas_comentadas,
  CAST(
    100 * SUM(CASE WHEN NULLIF(TRIM(c.comment), '') IS NULL THEN 0 ELSE 1 END)
      / NULLIF(COUNT(c.column_name), 0)
    AS DECIMAL(5, 2)
  ) AS cobertura_colunas_pct
FROM lakehouse_rotaperfume.information_schema.tables t
LEFT JOIN lakehouse_rotaperfume.information_schema.columns c
  ON c.table_catalog = t.table_catalog
  AND c.table_schema = t.table_schema
  AND c.table_name = t.table_name
WHERE t.table_schema = 'gold'
GROUP BY t.table_name, t.table_type, t.comment
ORDER BY t.table_name;

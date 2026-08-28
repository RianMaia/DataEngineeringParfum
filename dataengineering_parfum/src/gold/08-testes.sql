SET ANSI_MODE = TRUE;

-- 1. A transformação por item deve reconciliar exatamente com a receita líquida dos pedidos.
WITH valores AS (
  SELECT
    (SELECT CAST(SUM(receita) AS DECIMAL(18, 2)) FROM lakehouse_rotaperfume.gold.fato_vendas) AS receita_gold,
    (
      SELECT CAST(SUM(valor_liquido) AS DECIMAL(18, 2))
      FROM lakehouse_rotaperfume.silver.pedidos
      WHERE NOT cancelado
    ) AS receita_silver
)
SELECT
  '01_receita_gold_igual_silver' AS teste,
  CONCAT('gold=', CAST(receita_gold AS STRING), '; silver=', CAST(receita_silver AS STRING)) AS valor_calculado,
  'gold = silver = 102303828.05; tolerância 0.01' AS valor_esperado,
  CASE
    WHEN ABS(receita_gold - receita_silver) <= 0.01
      AND ABS(receita_gold - CAST(102303828.05 AS DECIMAL(18, 2))) <= 0.01
      THEN 'PASSOU'
    ELSE RAISE_ERROR(CONCAT(
      '01_receita_gold_igual_silver falhou: gold=', CAST(receita_gold AS STRING),
      ', silver=', CAST(receita_silver AS STRING), ', esperado=102303828.05'
    ))
  END AS resultado
FROM valores;

-- 2. A Silver deve manter uma única linha por CNPJ.
WITH valor AS (
  SELECT COUNT(*) - COUNT(DISTINCT cnpj) AS duplicados
  FROM lakehouse_rotaperfume.silver.clientes
)
SELECT
  '02_cnpj_unico_silver' AS teste,
  CAST(duplicados AS STRING) AS valor_calculado,
  '0 duplicados' AS valor_esperado,
  CASE
    WHEN duplicados = 0 THEN 'PASSOU'
    ELSE RAISE_ERROR(CONCAT('02_cnpj_unico_silver falhou: calculado=', duplicados, ', esperado=0'))
  END AS resultado
FROM valor;

-- 3. Todo pedido precisa de data para entrar nas análises temporais.
WITH valor AS (
  SELECT COUNT(*) AS datas_nulas
  FROM lakehouse_rotaperfume.silver.pedidos
  WHERE data_pedido IS NULL
)
SELECT
  '03_data_pedido_nao_nula' AS teste,
  CAST(datas_nulas AS STRING) AS valor_calculado,
  '0 datas nulas' AS valor_esperado,
  CASE
    WHEN datas_nulas = 0 THEN 'PASSOU'
    ELSE RAISE_ERROR(CONCAT('03_data_pedido_nao_nula falhou: calculado=', datas_nulas, ', esperado=0'))
  END AS resultado
FROM valor;

-- 4. Receita negativa só é permitida em itens identificados como devolução.
WITH valor AS (
  SELECT COUNT(*) AS negativas_sem_devolucao
  FROM lakehouse_rotaperfume.gold.fato_vendas
  WHERE receita < 0 AND NOT devolucao
)
SELECT
  '04_receita_negativa_so_devolucao' AS teste,
  CAST(negativas_sem_devolucao AS STRING) AS valor_calculado,
  '0 receitas negativas sem devolução' AS valor_esperado,
  CASE
    WHEN negativas_sem_devolucao = 0 THEN 'PASSOU'
    ELSE RAISE_ERROR(CONCAT(
      '04_receita_negativa_so_devolucao falhou: calculado=', negativas_sem_devolucao, ', esperado=0'
    ))
  END AS resultado
FROM valor;

-- 5. A fato deve manter volume compatível com o grão de item não cancelado.
WITH valor AS (
  SELECT COUNT(*) AS linhas
  FROM lakehouse_rotaperfume.gold.fato_vendas
)
SELECT
  '05_volume_fato_vendas' AS teste,
  CAST(linhas AS STRING) AS valor_calculado,
  'entre 140000 e 250000 linhas' AS valor_esperado,
  CASE
    WHEN linhas BETWEEN 140000 AND 250000 THEN 'PASSOU'
    ELSE RAISE_ERROR(CONCAT(
      '05_volume_fato_vendas falhou: calculado=', linhas, ', esperado entre 140000 e 250000'
    ))
  END AS resultado
FROM valor;

-- 6. Todo pedido da fato deve existir na Silver.
WITH valor AS (
  SELECT COUNT(*) AS pedidos_orfaos
  FROM lakehouse_rotaperfume.gold.fato_vendas f
  LEFT ANTI JOIN lakehouse_rotaperfume.silver.pedidos p ON f.pedido_id = p.pedido_id
)
SELECT
  '06_pedido_existente_silver' AS teste,
  CAST(pedidos_orfaos AS STRING) AS valor_calculado,
  '0 itens com pedido inexistente' AS valor_esperado,
  CASE
    WHEN pedidos_orfaos = 0 THEN 'PASSOU'
    ELSE RAISE_ERROR(CONCAT('06_pedido_existente_silver falhou: calculado=', pedidos_orfaos, ', esperado=0'))
  END AS resultado
FROM valor;

-- 7. Todo cliente canônico usado na fato deve existir na Silver.
WITH valor AS (
  SELECT COUNT(*) AS clientes_orfaos
  FROM lakehouse_rotaperfume.gold.fato_vendas f
  LEFT ANTI JOIN lakehouse_rotaperfume.silver.clientes c ON f.cliente_id = c.cliente_id
)
SELECT
  '07_cliente_existente_silver' AS teste,
  CAST(clientes_orfaos AS STRING) AS valor_calculado,
  '0 itens com cliente inexistente' AS valor_esperado,
  CASE
    WHEN clientes_orfaos = 0 THEN 'PASSOU'
    ELSE RAISE_ERROR(CONCAT('07_cliente_existente_silver falhou: calculado=', clientes_orfaos, ', esperado=0'))
  END AS resultado
FROM valor;

-- 8. O mart de produto não pode criar nem perder receita da fato.
WITH valores AS (
  SELECT
    (SELECT CAST(SUM(receita) AS DECIMAL(18, 2)) FROM lakehouse_rotaperfume.gold.mart_produto_performance)
      AS receita_mart,
    (SELECT CAST(SUM(receita) AS DECIMAL(18, 2)) FROM lakehouse_rotaperfume.gold.fato_vendas) AS receita_fato
)
SELECT
  '08_receita_mart_produto_igual_fato' AS teste,
  CONCAT('mart=', CAST(receita_mart AS STRING), '; fato=', CAST(receita_fato AS STRING)) AS valor_calculado,
  'diferença máxima de 0.01' AS valor_esperado,
  CASE
    WHEN ABS(receita_mart - receita_fato) <= 0.01 THEN 'PASSOU'
    ELSE RAISE_ERROR(CONCAT(
      '08_receita_mart_produto_igual_fato falhou: mart=', CAST(receita_mart AS STRING),
      ', fato=', CAST(receita_fato AS STRING), ', tolerância=0.01'
    ))
  END AS resultado
FROM valores;

-- 9. CNPJ é identificador textual e precisa ter exatamente 14 dígitos.
WITH valor AS (
  SELECT COUNT(*) AS cnpjs_invalidos
  FROM lakehouse_rotaperfume.silver.clientes
  WHERE cnpj IS NULL OR NOT (cnpj RLIKE '^[0-9]{14}$')
)
SELECT
  '09_cnpj_com_14_digitos' AS teste,
  CAST(cnpjs_invalidos AS STRING) AS valor_calculado,
  '0 CNPJs inválidos' AS valor_esperado,
  CASE
    WHEN cnpjs_invalidos = 0 THEN 'PASSOU'
    ELSE RAISE_ERROR(CONCAT('09_cnpj_com_14_digitos falhou: calculado=', cnpjs_invalidos, ', esperado=0'))
  END AS resultado
FROM valor;

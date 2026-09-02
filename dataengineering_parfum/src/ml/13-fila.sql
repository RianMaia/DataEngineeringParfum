SET ANSI_MODE=TRUE;

CREATE OR REPLACE TABLE lakehouse_rotaperfume.gold.fila_semanal
COMMENT 'Fila semanal dos 200 clientes elegíveis com maior propensão, ordenada para ação da equipe comercial'
AS
WITH carteira_vigente AS (
  SELECT cliente_id, vendedor_id
  FROM (
    SELECT
      cliente_id,
      vendedor_id,
      ROW_NUMBER() OVER (
        PARTITION BY cliente_id
        ORDER BY data_inicio DESC, carteira_id DESC
      ) AS atribuicao
    FROM lakehouse_rotaperfume.silver.carteira
    WHERE vigente = TRUE
      AND orfao_vendedor_desligado = FALSE
  )
  WHERE atribuicao = 1
),
referencia AS (
  SELECT MAX(_referencia) AS data_referencia
  FROM lakehouse_rotaperfume.gold.score_propensao
),
estoque_recente AS (
  SELECT sku, saldo, ruptura
  FROM (
    SELECT
      sku,
      saldo,
      ruptura,
      ROW_NUMBER() OVER (
        PARTITION BY sku
        ORDER BY data_snapshot DESC
      ) AS snapshot
    FROM lakehouse_rotaperfume.silver.estoque
  )
  WHERE snapshot = 1
),
marca_preferida AS (
  SELECT cliente_id, marca
  FROM (
    SELECT
      cliente_id,
      marca,
      ROW_NUMBER() OVER (
        PARTITION BY cliente_id
        ORDER BY SUM(quantidade) DESC, marca
      ) AS preferencia
    FROM lakehouse_rotaperfume.gold.fato_vendas
    WHERE devolucao = FALSE
    GROUP BY cliente_id, marca
  )
  WHERE preferencia = 1
),
sku_historico AS (
  SELECT
    f.cliente_id,
    f.sku,
    f.marca,
    p.descricao,
    SUM(f.quantidade) AS unidades_compradas,
    MAX(f.data_pedido) AS ultima_compra
  FROM lakehouse_rotaperfume.gold.fato_vendas f
  INNER JOIN marca_preferida m
    ON m.cliente_id = f.cliente_id
   AND m.marca = f.marca
  INNER JOIN lakehouse_rotaperfume.gold.dim_produto p ON p.sku = f.sku
  WHERE f.devolucao = FALSE
  GROUP BY f.cliente_id, f.sku, f.marca, p.descricao
),
sugestoes AS (
  SELECT cliente_id, sku, descricao, saldo, ruptura
  FROM (
    SELECT
      h.cliente_id,
      h.sku,
      h.descricao,
      e.saldo,
      e.ruptura,
      ROW_NUMBER() OVER (
        PARTITION BY h.cliente_id
        ORDER BY h.unidades_compradas DESC, h.ultima_compra DESC, h.sku
      ) AS prioridade
    FROM sku_historico h
    CROSS JOIN referencia r
    LEFT JOIN estoque_recente e ON e.sku = h.sku
    WHERE h.ultima_compra < DATE_SUB(r.data_referencia, 90)
  )
  WHERE prioridade = 1
),
elegiveis AS (
  SELECT
    v.nome AS vendedor,
    CAST(s.cliente_id AS INT) AS cliente_id,
    d.razao_social,
    d.cidade,
    d.uf,
    s.score,
    s.faixa,
    f.ticket_medio,
    f.intervalo_medio_dias,
    f.recencia_dias,
    f.atraso_relativo,
    f.comprou_lancamento,
    f.valor_total,
    PERCENT_RANK() OVER (ORDER BY f.valor_total DESC) AS percentil_valor,
    g.sku AS sku_sugerido,
    g.descricao AS produto_sugerido,
    g.saldo AS saldo_sugerido,
    g.ruptura AS ruptura_sugerida
  FROM lakehouse_rotaperfume.gold.score_propensao s
  INNER JOIN lakehouse_rotaperfume.gold.features_cliente f ON f.cliente_id = s.cliente_id
  INNER JOIN lakehouse_rotaperfume.gold.dim_cliente d ON d.cliente_id = s.cliente_id
  INNER JOIN carteira_vigente c ON c.cliente_id = s.cliente_id
  INNER JOIN lakehouse_rotaperfume.silver.vendedores v ON v.vendedor_id = c.vendedor_id
  LEFT JOIN sugestoes g ON g.cliente_id = s.cliente_id
),
top_200 AS (
  SELECT *
  FROM elegiveis
  ORDER BY score DESC, cliente_id ASC
  LIMIT 200
),
fila AS (
  SELECT
    vendedor,
    ROW_NUMBER() OVER (
      PARTITION BY vendedor
      ORDER BY score DESC, cliente_id ASC
    ) AS ordem,
    cliente_id,
    razao_social,
    cidade,
    uf,
    score,
    faixa,
    ticket_medio,
    CASE
      WHEN atraso_relativo > 3 THEN CONCAT(
        'Compra a cada ', FORMAT_NUMBER(intervalo_medio_dias, 0),
        ' dias e está há ', FORMAT_NUMBER(recencia_dias, 0),
        ' sem pedido. Risco de perder para o concorrente.'
      )
      WHEN atraso_relativo > 1.5 THEN CONCAT(
        'Está ', FORMAT_NUMBER(atraso_relativo, 1),
        ' vezes mais atrasado que o ritmo dele.'
      )
      WHEN comprou_lancamento > 0 THEN
        'Comprou lançamento recente. Alta chance de repetir.'
      WHEN percentil_valor <= 0.10 THEN CONCAT(
        'Cliente grande, R$ ', FORMAT_NUMBER(valor_total, 2),
        ' no ano. Manter próximo.'
      )
      ELSE 'Dentro do ritmo. Contato de manutenção.'
    END AS motivo,
    CASE
      WHEN sku_sugerido IS NULL THEN 'Sem sugestão disponível para os critérios da semana.'
      ELSE CONCAT(
        sku_sugerido, ' — ', produto_sugerido,
        ' (saldo: ', COALESCE(CAST(saldo_sugerido AS STRING), 'sem snapshot'),
        CASE WHEN ruptura_sugerida = TRUE THEN ', em ruptura' ELSE '' END,
        ')'
      )
    END AS sugestao
  FROM top_200
)
SELECT
  vendedor,
  ordem,
  cliente_id,
  razao_social,
  cidade,
  uf,
  score,
  faixa,
  ticket_medio,
  motivo,
  sugestao
FROM fila;

COMMENT ON COLUMN lakehouse_rotaperfume.gold.fila_semanal.vendedor IS
  'Nome do vendedor responsável pelo contato';
COMMENT ON COLUMN lakehouse_rotaperfume.gold.fila_semanal.ordem IS
  'Prioridade do cliente dentro da carteira do vendedor, começando em um';
COMMENT ON COLUMN lakehouse_rotaperfume.gold.fila_semanal.cliente_id IS
  'Identificador canônico do cliente priorizado';
COMMENT ON COLUMN lakehouse_rotaperfume.gold.fila_semanal.razao_social IS
  'Nome empresarial do cliente que deve receber o contato';
COMMENT ON COLUMN lakehouse_rotaperfume.gold.fila_semanal.cidade IS
  'Cidade do cliente priorizado';
COMMENT ON COLUMN lakehouse_rotaperfume.gold.fila_semanal.uf IS
  'Unidade federativa do cliente priorizado';
COMMENT ON COLUMN lakehouse_rotaperfume.gold.fila_semanal.score IS
  'Probabilidade estimada de compra, em escala de zero a um';
COMMENT ON COLUMN lakehouse_rotaperfume.gold.fila_semanal.faixa IS
  'Faixa comercial derivada do score de propensão';
COMMENT ON COLUMN lakehouse_rotaperfume.gold.fila_semanal.ticket_medio IS
  'Valor médio dos pedidos históricos do cliente';
COMMENT ON COLUMN lakehouse_rotaperfume.gold.fila_semanal.motivo IS
  'Explicação em linguagem comercial para a prioridade do contato';
COMMENT ON COLUMN lakehouse_rotaperfume.gold.fila_semanal.sugestao IS
  'Produto recomendado e saldo do snapshot de estoque mais recente';

CREATE OR REPLACE FUNCTION lakehouse_rotaperfume.gold.priorizar_carteira(
  p_vendedor STRING COMMENT 'Nome exato do vendedor',
  p_quantos INT COMMENT 'Quantidade máxima de contatos desejada'
)
RETURNS TABLE (
  ordem BIGINT,
  cliente_id INT,
  razao_social STRING,
  cidade STRING,
  uf STRING,
  score DOUBLE,
  faixa STRING,
  ticket_medio DOUBLE,
  motivo STRING,
  sugestao STRING
)
COMMENT 'Retorna a fatia priorizada da fila semanal de um vendedor, na ordem correta de contato'
RETURN
  SELECT
    ordem,
    cliente_id,
    razao_social,
    cidade,
    uf,
    score,
    faixa,
    ticket_medio,
    motivo,
    sugestao
  FROM lakehouse_rotaperfume.gold.fila_semanal
  WHERE vendedor = p_vendedor
    AND ordem <= p_quantos
  ORDER BY ordem;

CREATE OR REPLACE FUNCTION lakehouse_rotaperfume.gold.contexto_cliente(
  p_cliente_id INT COMMENT 'Identificador canônico do cliente'
)
RETURNS TABLE (
  cliente_id INT,
  razao_social STRING,
  data_primeira_compra DATE,
  data_ultima_compra DATE,
  pedidos BIGINT,
  ticket_medio DOUBLE,
  marca_preferida STRING,
  receita_marca DOUBLE,
  ranking_marca BIGINT
)
COMMENT 'Resume histórico, ticket médio, últimas compras e marcas preferidas para preparar o contato comercial'
RETURN
  WITH resumo AS (
    SELECT
      CAST(f.cliente_id AS INT) AS cliente_id,
      MAX(f.razao_social) AS razao_social,
      MIN(f.data_pedido) AS data_primeira_compra,
      MAX(f.data_pedido) AS data_ultima_compra,
      COUNT(DISTINCT f.pedido_id) AS pedidos,
      CAST(SUM(f.receita) / NULLIF(COUNT(DISTINCT f.pedido_id), 0) AS DOUBLE) AS ticket_medio
    FROM lakehouse_rotaperfume.gold.fato_vendas f
    WHERE f.cliente_id = p_cliente_id
    GROUP BY f.cliente_id
  ),
  marcas AS (
    SELECT
      CAST(f.cliente_id AS INT) AS cliente_id,
      f.marca,
      CAST(SUM(f.receita) AS DOUBLE) AS receita_marca,
      ROW_NUMBER() OVER (
        PARTITION BY f.cliente_id
        ORDER BY SUM(f.receita) DESC, f.marca
      ) AS ranking_marca
    FROM lakehouse_rotaperfume.gold.fato_vendas f
    WHERE f.cliente_id = p_cliente_id
    GROUP BY f.cliente_id, f.marca
  )
  SELECT
    r.cliente_id,
    r.razao_social,
    r.data_primeira_compra,
    r.data_ultima_compra,
    r.pedidos,
    r.ticket_medio,
    m.marca AS marca_preferida,
    m.receita_marca,
    m.ranking_marca
  FROM resumo r
  INNER JOIN marcas m ON m.cliente_id = r.cliente_id
  WHERE m.ranking_marca <= 3
  ORDER BY m.ranking_marca;

CREATE OR REPLACE FUNCTION lakehouse_rotaperfume.gold.sugerir_produtos(
  p_cliente_id INT COMMENT 'Identificador canônico do cliente'
)
RETURNS TABLE (
  sku STRING,
  descricao STRING,
  marca STRING,
  unidades_compradas BIGINT,
  ultima_compra DATE,
  saldo INT,
  ruptura BOOLEAN
)
COMMENT 'Lista produtos historicamente comprados pelo cliente, sem recompra nos últimos 90 dias, com estoque atual'
RETURN
  WITH referencia AS (
    SELECT MAX(_referencia) AS data_referencia
    FROM lakehouse_rotaperfume.gold.score_propensao
  ),
  estoque_recente AS (
    SELECT sku, saldo, ruptura
    FROM (
      SELECT
        sku,
        saldo,
        ruptura,
        ROW_NUMBER() OVER (
          PARTITION BY sku
          ORDER BY data_snapshot DESC
        ) AS snapshot
      FROM lakehouse_rotaperfume.silver.estoque
    )
    WHERE snapshot = 1
  ),
  compras AS (
    SELECT
      f.sku,
      p.descricao,
      f.marca,
      SUM(f.quantidade) AS unidades_compradas,
      MAX(f.data_pedido) AS ultima_compra
    FROM lakehouse_rotaperfume.gold.fato_vendas f
    INNER JOIN lakehouse_rotaperfume.gold.dim_produto p ON p.sku = f.sku
    WHERE f.cliente_id = p_cliente_id
      AND f.devolucao = FALSE
    GROUP BY f.sku, p.descricao, f.marca
  )
  SELECT
    c.sku,
    c.descricao,
    c.marca,
    c.unidades_compradas,
    c.ultima_compra,
    e.saldo,
    e.ruptura
  FROM compras c
  CROSS JOIN referencia r
  LEFT JOIN estoque_recente e ON e.sku = c.sku
  WHERE c.ultima_compra < DATE_SUB(r.data_referencia, 90)
  ORDER BY c.unidades_compradas DESC, c.ultima_compra DESC, c.sku;

CREATE OR REPLACE FUNCTION lakehouse_rotaperfume.gold.checar_disponibilidade(
  p_sku STRING COMMENT 'SKU a consultar'
)
RETURNS TABLE (
  sku STRING,
  data_snapshot DATE,
  saldo INT,
  ruptura BOOLEAN
)
COMMENT 'Consulta saldo e ruptura de um SKU no snapshot de estoque mais recente disponível'
RETURN
  SELECT sku, data_snapshot, saldo, ruptura
  FROM lakehouse_rotaperfume.silver.estoque
  WHERE sku = p_sku
  ORDER BY data_snapshot DESC
  LIMIT 1;

SELECT
  CASE
    WHEN COUNT(*) = 200 THEN 'OK: fila com exatamente 200 contatos'
    ELSE RAISE_ERROR(CONCAT(
      'ml_fila falhou: esperado=200, calculado=', COUNT(*)
    ))
  END AS teste_volume
FROM lakehouse_rotaperfume.gold.fila_semanal;

SELECT
  CASE
    WHEN COUNT_IF(motivo IS NULL OR TRIM(motivo) = '') = 0 THEN
      'OK: todos os contatos possuem motivo'
    ELSE RAISE_ERROR(CONCAT(
      'ml_fila falhou: motivos nulos ou vazios=',
      COUNT_IF(motivo IS NULL OR TRIM(motivo) = '')
    ))
  END AS teste_motivo
FROM lakehouse_rotaperfume.gold.fila_semanal;

SELECT
  CASE
    WHEN COUNT_IF(score IS NULL OR score < 0 OR score > 1) = 0 THEN
      'OK: todos os scores estão entre zero e um'
    ELSE RAISE_ERROR(CONCAT(
      'ml_fila falhou: scores inválidos=',
      COUNT_IF(score IS NULL OR score < 0 OR score > 1)
    ))
  END AS teste_score
FROM lakehouse_rotaperfume.gold.fila_semanal;

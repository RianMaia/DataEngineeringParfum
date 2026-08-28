SET ANSI_MODE = TRUE;

CREATE OR REPLACE TABLE lakehouse_rotaperfume.gold.dim_cliente
COMMENT 'Visão conformada de clientes com histórico consolidado de compras não canceladas'
AS
WITH mapa_cliente AS (
  SELECT
    cliente_id AS cliente_id_canonico,
    cliente_id AS cliente_id_pedido
  FROM lakehouse_rotaperfume.silver.clientes

  UNION ALL

  SELECT
    c.cliente_id AS cliente_id_canonico,
    id_duplicado AS cliente_id_pedido
  FROM lakehouse_rotaperfume.silver.clientes c
  LATERAL VIEW EXPLODE(c.cliente_ids_duplicados) ids AS id_duplicado
),
historico_pedidos AS (
  SELECT
    m.cliente_id_canonico AS cliente_id,
    MIN(p.data_pedido) AS data_primeiro_pedido,
    MAX(p.data_pedido) AS data_ultimo_pedido,
    COUNT(DISTINCT p.pedido_id) AS total_pedidos,
    CAST(SUM(p.valor_liquido) AS DECIMAL(18, 2)) AS receita_acumulada
  FROM lakehouse_rotaperfume.silver.pedidos p
  INNER JOIN mapa_cliente m ON p.cliente_id = m.cliente_id_pedido
  WHERE NOT p.cancelado
  GROUP BY m.cliente_id_canonico
)
SELECT
  c.cliente_id,
  c.cnpj,
  c.razao_social,
  c.segmento,
  c.cidade,
  c.uf,
  c.data_cadastro,
  h.data_primeiro_pedido,
  h.data_ultimo_pedido,
  COALESCE(h.total_pedidos, 0) AS total_pedidos,
  COALESCE(h.receita_acumulada, CAST(0 AS DECIMAL(18, 2))) AS receita_acumulada,
  CASE
    WHEN h.data_ultimo_pedido IS NULL THEN NULL
    ELSE DATEDIFF(CURRENT_DATE(), h.data_ultimo_pedido)
  END AS dias_sem_comprar
FROM lakehouse_rotaperfume.silver.clientes c
LEFT JOIN historico_pedidos h ON c.cliente_id = h.cliente_id;

COMMENT ON COLUMN lakehouse_rotaperfume.gold.dim_cliente.data_primeiro_pedido IS
  'Data da primeira compra não cancelada, considerando IDs antigos remapeados para o cliente canônico';
COMMENT ON COLUMN lakehouse_rotaperfume.gold.dim_cliente.data_ultimo_pedido IS
  'Data da compra não cancelada mais recente, considerando IDs antigos remapeados para o cliente canônico';
COMMENT ON COLUMN lakehouse_rotaperfume.gold.dim_cliente.total_pedidos IS
  'Quantidade de pedidos não cancelados atribuídos ao cliente';
COMMENT ON COLUMN lakehouse_rotaperfume.gold.dim_cliente.receita_acumulada IS
  'Receita líquida acumulada dos pedidos não cancelados, incluindo o efeito de devoluções';
COMMENT ON COLUMN lakehouse_rotaperfume.gold.dim_cliente.dias_sem_comprar IS
  'Dias corridos entre hoje e a última compra não cancelada; nulo quando o cliente nunca comprou';

CREATE OR REPLACE TABLE lakehouse_rotaperfume.gold.dim_produto
COMMENT 'Visão conformada do catálogo de produtos para análises comerciais e de margem'
AS
SELECT
  sku,
  descricao,
  marca,
  categoria,
  nota_olfativa,
  custo_unitario,
  preco_tabela,
  data_lancamento,
  NOT ativo AS descontinuado
FROM lakehouse_rotaperfume.silver.produtos;

COMMENT ON COLUMN lakehouse_rotaperfume.gold.dim_produto.descontinuado IS
  'Verdadeiro quando o produto não está mais ativo no catálogo comercial';

CREATE OR REPLACE TABLE lakehouse_rotaperfume.gold.dim_vendedor
COMMENT 'Visão conformada da equipe comercial com região, meta vigente e situação funcional'
AS
SELECT
  vendedor_id,
  nome,
  regiao,
  uf,
  meta_mensal,
  data_admissao,
  data_desligamento,
  data_desligamento IS NULL OR data_desligamento > CURRENT_DATE() AS ativo
FROM lakehouse_rotaperfume.silver.vendedores;

COMMENT ON COLUMN lakehouse_rotaperfume.gold.dim_vendedor.ativo IS
  'Verdadeiro quando não há desligamento ou quando o desligamento ocorrerá após a data atual';

CREATE OR REPLACE TABLE lakehouse_rotaperfume.gold.dim_calendario
COMMENT 'Calendário diário conformado para os 24 meses cobertos pelos pedidos da Silver'
AS
WITH limites AS (
  SELECT
    CAST(DATE_TRUNC('MONTH', MIN(data_pedido)) AS DATE) AS data_inicial,
    LAST_DAY(MAX(data_pedido)) AS data_final
  FROM lakehouse_rotaperfume.silver.pedidos
),
datas AS (
  SELECT EXPLODE(SEQUENCE(data_inicial, data_final, INTERVAL 1 DAY)) AS data
  FROM limites
)
SELECT
  data,
  YEAR(data) AS ano,
  MONTH(data) AS mes,
  CASE MONTH(data)
    WHEN 1 THEN 'Janeiro'
    WHEN 2 THEN 'Fevereiro'
    WHEN 3 THEN 'Março'
    WHEN 4 THEN 'Abril'
    WHEN 5 THEN 'Maio'
    WHEN 6 THEN 'Junho'
    WHEN 7 THEN 'Julho'
    WHEN 8 THEN 'Agosto'
    WHEN 9 THEN 'Setembro'
    WHEN 10 THEN 'Outubro'
    WHEN 11 THEN 'Novembro'
    WHEN 12 THEN 'Dezembro'
  END AS nome_mes,
  QUARTER(data) AS trimestre,
  CASE DAYOFWEEK(data)
    WHEN 1 THEN 'Domingo'
    WHEN 2 THEN 'Segunda-feira'
    WHEN 3 THEN 'Terça-feira'
    WHEN 4 THEN 'Quarta-feira'
    WHEN 5 THEN 'Quinta-feira'
    WHEN 6 THEN 'Sexta-feira'
    WHEN 7 THEN 'Sábado'
  END AS dia_semana,
  MONTH(data) IN (4, 6, 10) AS mes_pico_setor
FROM datas;

COMMENT ON COLUMN lakehouse_rotaperfume.gold.dim_calendario.mes_pico_setor IS
  'Identifica abril, junho e outubro, meses de pico comercial definidos pelo setor de perfumaria';

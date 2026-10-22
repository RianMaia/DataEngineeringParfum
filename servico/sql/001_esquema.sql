-- Esquema do banco de serviço do DataEngineeringParfum (PostgreSQL 16).
--
-- Este banco é uma CÓPIA DE LEITURA dos resultados do pipeline Databricks, não a fonte da verdade.
-- A carga (etapa futura) substitui o conteúdo inteiro numa única transação. Por isso:
--   * as regras de negócio NÃO são recalculadas aqui; só copiamos o que o pipeline produziu;
--   * as restrições (chaves, CHECK, FOREIGN KEY) protegem as invariantes que medimos no pipeline,
--     e fazem a carga falhar, sem alterar nada, se algum dado violar o que esperamos;
--   * NOT NULL só aparece onde o pipeline garante o valor.
-- Tipos: STRING -> TEXT, BIGINT -> BIGINT, INT -> INTEGER, DOUBLE -> DOUBLE PRECISION (sem arredondar),
-- DECIMAL(18,2) -> NUMERIC(18,2), DATE -> DATE.

BEGIN;

-- Equipe comercial (origem: gold.dim_vendedor, 42 linhas).
CREATE TABLE vendedores (
    vendedor_id        BIGINT PRIMARY KEY,
    nome               TEXT NOT NULL,
    regiao             TEXT,
    uf                 TEXT,
    data_admissao      DATE,
    data_desligamento  DATE,
    meta_mensal        NUMERIC(18, 2),
    ativo              BOOLEAN NOT NULL,
    -- Permite que a fila referencie (id, nome) e prove que o nome bate com o ID.
    CONSTRAINT vendedores_id_nome_unico UNIQUE (vendedor_id, nome)
);

-- Universo de clientes (origem: gold.dim_cliente). Só o identificador: serve para separar
-- "cliente inexistente" (404) de "cliente sem dados" (200 com lista vazia).
CREATE TABLE clientes (
    cliente_id  BIGINT PRIMARY KEY
);

-- Catálogo + estoque mais recente por SKU (origem: gold.dim_produto + gold.checar_disponibilidade).
CREATE TABLE produtos (
    sku            TEXT PRIMARY KEY,
    descricao      TEXT,
    marca          TEXT,
    descontinuado  BOOLEAN NOT NULL,
    saldo          INTEGER,
    ruptura        BOOLEAN,
    data_snapshot  DATE,
    -- Estoque é tudo ou nada: ou há snapshot completo, ou os três campos são nulos.
    CONSTRAINT produtos_estoque_completo CHECK (
        (saldo IS NULL AND ruptura IS NULL AND data_snapshot IS NULL)
        OR (saldo IS NOT NULL AND ruptura IS NOT NULL AND data_snapshot IS NOT NULL)
    ),
    -- Regra do pipeline (silver.estoque): ruptura significa exatamente saldo igual a zero.
    CONSTRAINT produtos_ruptura_e_saldo_zero CHECK (ruptura IS NULL OR ruptura = (saldo = 0))
);

-- Fila semanal (origem: gold.fila_semanal, 200 linhas, mais o vendedor_id recuperado na carga).
CREATE TABLE fila_semanal (
    cliente_id     BIGINT PRIMARY KEY REFERENCES clientes (cliente_id),
    vendedor_id    BIGINT NOT NULL,
    vendedor_nome  TEXT NOT NULL,
    ordem_fila     BIGINT NOT NULL,
    posicao        INTEGER NOT NULL,
    razao_social   TEXT,
    cidade         TEXT,
    uf             TEXT,
    score          DOUBLE PRECISION NOT NULL,
    faixa          TEXT,
    ticket_medio   DOUBLE PRECISION,
    motivo         TEXT NOT NULL,
    sugestao       TEXT NOT NULL,
    -- O nome que o pipeline gravou tem de ser o nome desse vendedor_id (conciliação 200 de 200).
    CONSTRAINT fila_vendedor_id_e_nome_batem
        FOREIGN KEY (vendedor_id, vendedor_nome) REFERENCES vendedores (vendedor_id, nome),
    CONSTRAINT fila_score_entre_0_e_1 CHECK (score BETWEEN 0 AND 1),
    CONSTRAINT fila_ordem_fila_positiva CHECK (ordem_fila >= 1),
    CONSTRAINT fila_posicao_positiva CHECK (posicao >= 1),
    -- Invariante do pipeline: a numeração é única por NOME (vendedores homônimos dividem uma fila).
    CONSTRAINT fila_ordem_unica_por_nome UNIQUE (vendedor_nome, ordem_fila),
    -- Invariante da API: a posição é única por vendedor. Também serve de índice da consulta da fila.
    CONSTRAINT fila_posicao_unica_por_vendedor UNIQUE (vendedor_id, posicao)
);

-- Contexto do cliente: até 3 marcas por cliente (origem: gold.contexto_cliente).
CREATE TABLE contexto_cliente (
    cliente_id            BIGINT NOT NULL REFERENCES clientes (cliente_id),
    ranking_marca         SMALLINT NOT NULL,
    razao_social          TEXT,
    data_primeira_compra  DATE,
    data_ultima_compra    DATE,
    pedidos               BIGINT,
    ticket_medio          DOUBLE PRECISION,
    marca_preferida       TEXT,
    receita_marca         DOUBLE PRECISION,
    PRIMARY KEY (cliente_id, ranking_marca),
    CONSTRAINT contexto_ranking_de_1_a_3 CHECK (ranking_marca BETWEEN 1 AND 3)
);

-- Sugestões por cliente (origem: gold.sugerir_produtos). Descrição, marca, saldo, ruptura e
-- descontinuado NÃO são copiados: vêm de produtos por JOIN, para ter uma só fonte.
CREATE TABLE sugestoes_cliente (
    cliente_id          BIGINT NOT NULL REFERENCES clientes (cliente_id),
    sku                 TEXT NOT NULL REFERENCES produtos (sku),
    ordem               INTEGER NOT NULL,
    unidades_compradas  BIGINT,
    ultima_compra       DATE NOT NULL,
    PRIMARY KEY (cliente_id, sku),
    CONSTRAINT sugestoes_ordem_positiva CHECK (ordem >= 1),
    -- Ordem determinística: única por cliente. Também serve de índice da consulta.
    CONSTRAINT sugestoes_ordem_unica_por_cliente UNIQUE (cliente_id, ordem)
);

-- Uma linha por tentativa de carga. O log é gravado FORA da transação da carga, para sobreviver a falhas.
CREATE TABLE carga_log (
    carga_id                 BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    iniciada_em              TIMESTAMPTZ NOT NULL DEFAULT now(),
    concluida_em             TIMESTAMPTZ,
    status                   TEXT NOT NULL DEFAULT 'em_andamento',
    data_referencia_score    DATE,
    snapshot_estoque_global  DATE,
    contagens                JSONB,
    erro                     TEXT,
    CONSTRAINT carga_status_valido CHECK (status IN ('em_andamento', 'concluida', 'falha')),
    CONSTRAINT carga_fim_coerente CHECK ((status = 'em_andamento') = (concluida_em IS NULL))
);

COMMENT ON TABLE fila_semanal IS 'Cópia de gold.fila_semanal com vendedor_id recuperado na carga.';
COMMENT ON COLUMN fila_semanal.ordem_fila IS
    'Valor original do pipeline: posição na fila do NOME do vendedor (homônimos dividem a numeração).';
COMMENT ON COLUMN fila_semanal.posicao IS
    'Posição dentro da fila do vendedor_id, de 1 a N, na ordem de ordem_fila. É a ordem de contato da API.';
COMMENT ON COLUMN produtos.ruptura IS
    'Verdadeiro quando saldo = 0 no snapshot mais recente do SKU. Nulo quando o SKU não tem snapshot.';
COMMENT ON COLUMN produtos.data_snapshot IS
    'Data do snapshot de estoque deste SKU. Varia por SKU e pode ser bem anterior ao snapshot global.';
COMMENT ON COLUMN sugestoes_cliente.ordem IS
    'Ordem da função: unidades_compradas desc, ultima_compra desc, sku. Persistida para não depender de collation.';
COMMENT ON TABLE carga_log IS 'Histórico das cargas. A API lê a última com status concluida para montar o meta.';

COMMIT;

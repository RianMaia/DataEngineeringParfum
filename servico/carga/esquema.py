"""As 6 tabelas copiadas do Databricks: colunas, chaves e a ordem de gravação.

Tudo aqui espelha servico/sql/001_esquema.sql. Se o esquema mudar, este arquivo muda junto.
"""

# A ordem das colunas é a ordem do SELECT de cada consulta em extracao.py e a ordem do COPY em gravacao.py.
COLUNAS = {
    "vendedores": ("vendedor_id", "nome", "regiao", "uf", "data_admissao", "data_desligamento", "meta_mensal", "ativo"),
    "clientes": ("cliente_id",),
    "produtos": ("sku", "descricao", "marca", "descontinuado", "saldo", "ruptura", "data_snapshot"),
    "fila_semanal": (
        "cliente_id",
        "vendedor_id",
        "vendedor_nome",
        "ordem_fila",
        "posicao",
        "razao_social",
        "cidade",
        "uf",
        "score",
        "faixa",
        "ticket_medio",
        "motivo",
        "sugestao",
    ),
    "contexto_cliente": (
        "cliente_id",
        "ranking_marca",
        "razao_social",
        "data_primeira_compra",
        "data_ultima_compra",
        "pedidos",
        "ticket_medio",
        "marca_preferida",
        "receita_marca",
    ),
    "sugestoes_cliente": ("cliente_id", "sku", "ordem", "unidades_compradas", "ultima_compra"),
}

# Quem é "pai" vem primeiro ao gravar (vendedores, clientes, produtos); ao apagar, a ordem é a inversa.
ORDEM_INSERCAO = tuple(COLUNAS)
ORDEM_APAGAR = tuple(reversed(ORDEM_INSERCAO))

# Conjuntos de colunas que não podem repetir (chave primária e UNIQUE do esquema).
UNICIDADES = {
    "vendedores": (("vendedor_id",),),
    "clientes": (("cliente_id",),),
    "produtos": (("sku",),),
    "fila_semanal": (("cliente_id",), ("vendedor_nome", "ordem_fila"), ("vendedor_id", "posicao")),
    "contexto_cliente": (("cliente_id", "ranking_marca"),),
    "sugestoes_cliente": (("cliente_id", "sku"), ("cliente_id", "ordem")),
}

# Chaves estrangeiras: (tabela filha, colunas da filha, tabela pai, colunas do pai).
REFERENCIAS = (
    ("fila_semanal", ("cliente_id",), "clientes", ("cliente_id",)),
    ("fila_semanal", ("vendedor_id", "vendedor_nome"), "vendedores", ("vendedor_id", "nome")),
    ("contexto_cliente", ("cliente_id",), "clientes", ("cliente_id",)),
    ("sugestoes_cliente", ("cliente_id",), "clientes", ("cliente_id",)),
    ("sugestoes_cliente", ("sku",), "produtos", ("sku",)),
)

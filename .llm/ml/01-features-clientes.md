Continue o bundle em aulas/aula-02-engenharia-de-dados/rotaperfume/.
A gold está pronta, testada e com metadado auditado. Começa a camada de ML.

Crie src/ml/11-features.py — um notebook Python para serverless.

Defina UMA função montar_features(referencia) que devolve uma linha por
cliente com tudo que se sabia dele ATÉ essa data. Cada fonte é filtrada pela
data dela na primeira linha da leitura, sem exceção:

  gold.fato_vendas        data_pedido   < referencia
  silver.oportunidades    data_abertura < referencia
  silver.visitas          data_visita   < referencia

NÃO leia gold.dim_cliente: dias_sem_comprar, receita_acumulada e
total_pedidos agregam a base INTEIRA, sem corte — usar qualquer uma é
vazamento. Ela só entra no prompt 3, para nome e cidade.

Vinte features, em quatro grupos. Tudo sai de gold.fato_vendas, que já traz
razao_social, canal, categoria e marca — não precisa de join para isso:

  RFM
    recencia_dias        = datediff(referencia, max(data_pedido))
    frequencia_pedidos   = count(distinct pedido_id)
    valor_total          = sum(receita)   -- devolução já entra negativa
    ticket_medio         = valor_total / frequencia_pedidos
    margem_total         = sum(margem)
    margem_percentual    = margem_total / nullif(valor_total, 0)

  Ritmo
    intervalo_medio_dias   = média dos intervalos entre pedidos consecutivos
    desvio_intervalo_dias  = desvio padrão desses mesmos intervalos
                             (calcule os gaps uma vez, com lag() sobre as datas
                              distintas de pedido, e tire média e desvio dali)
    atraso_relativo        = recencia_dias / intervalo_medio_dias,
                             com NULLIF no denominador e teto em 10
    pedidos_ultimos_90d    = pedidos distintos nos 90 dias antes do corte

  CRM
    oportunidades_abertas  = nem ganha nem perdida (as duas são colunas
                             booleanas em silver.oportunidades)
    oportunidades_ganhas   = coluna ganha
    taxa_ganho             = ganhas / nullif(total de oportunidades, 0)
    visitas_90d            = visitas nos 90 dias antes do corte
    conversao_visita       = visitas com gerou_pedido / nullif(visitas, 0)

  Mix
    skus_distintos          = count(distinct sku)
    categorias_distintas    = count(distinct categoria)
    marcas_distintas        = count(distinct marca)
    concentracao_marca_top  = receita da marca top / nullif(valor_total, 0)
    comprou_lancamento      = 1 se comprou algum SKU cuja data_lancamento
                              (de gold.dim_produto) esteja nos 120 dias
                              anteriores ao corte. É o único join necessário.

Grave duas tabelas, chamando a MESMA função duas vezes:

  gold.features_treino   referencia = 2026-08-01, mais o alvo comprou_em_7d
                         = 1 se fez pedido entre 2026-08-01 e 2026-08-07
  gold.features_cliente  referencia = 2026-08-31, sem alvo — é o que será
                         pontuado

As duas gravam uma coluna _referencia com a data de corte usada. Toda soma de
receita ou margem sai da gold como DECIMAL(18,2): use cast para double em
TODAS as features numéricas, senão o registro do modelo quebra depois com
"Object of type Decimal is not JSON serializable".

Cliente sem oportunidade ou sem visita fica com 0, não com NULL — só as
features de ritmo podem ser NULL, para cliente com um pedido só.

Nada de current_date() em lugar nenhum: o "hoje" deste dataset é 2026-08-31.

COMMENT em português NA TABELA — as duas. A auditoria de metadado da noite 2
quebra o job se faltar. Ela não exige comentário nas colunas destas tabelas, e
saveAsTable não grava comment de tabela: rode COMMENT ON TABLE em seguida.

Depois registre a tarefa ml_features em resources/pipeline.job.yml, rodando
depois de testes_de_qualidade — modelo não se treina com dado que ainda não
passou nos testes — e faça o deploy.

DUAS ARMADILHAS MEDIDAS — as duas quebraram na preparação:
  1. F.least() IGNORA nulo e devolve o outro valor: no teto do atraso_relativo,
     os 80 clientes de um pedido só recebem 10 e vão para o TOPO da fila.
     Envolva num when(intervalo_medio_dias IS NOT NULL AND > 0).
  2. Célula que começa com # MAGIC %md é markdown INTEIRA — sem um
     # COMMAND ---------- antes do código, a função não é definida (NameError).
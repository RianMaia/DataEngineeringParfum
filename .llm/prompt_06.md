Continue o bundle em aulas/aula-02-engenharia-de-dados/rotaperfume/.
A gold está modelada, testada e no dashboard. Última entrega: preparar tudo
para consumo por linguagem natural.

1. src/gold/09-metricas-negocio.sql
   Crie views nomeadas como uma pessoa de negócio nomearia — em português, sem
   prefixo técnico:
     gold.receita_mensal        receita, margem e pedidos por mês, com a coluna
                                mes_pico_setor vinda da dim_calendario
     gold.ranking_marcas        marca → receita, margem %, participação %
     gold.margem_por_categoria  categoria → receita, margem, margem %
     gold.clientes_em_risco     sem compra há mais de 90 dias, com quanto
                                compravam por mês antes de sumir
     gold.efeito_lancamento     receita dos SKUs nos 120 dias após o lançamento
                                contra o resto do período
     gold.ruptura_por_marca     % de snapshots em ruptura por marca
   COMMENT em cada view dizendo QUAL PERGUNTA DE NEGÓCIO ela responde — não o
   que ela é. É assim que o Genie escolhe onde procurar.
   Use a forma compacta `CREATE OR REPLACE VIEW nome (col COMMENT '...', ...)`
   para comentar toda coluna sem precisar de um ALTER por coluna.

2. src/gold/10-auditoria-metadado.sql

   Consulte information_schema e QUEBRE com raise_error() se:
   - alguma tabela ou view da gold estiver sem COMMENT
   - alguma coluna de fato_vendas ou das 6 views estiver sem COMMENT
   Ao final, imprima um relatório de cobertura de metadado por objeto — sem
   quebrar. Serve para a conversa com quem vai consumir a gold.
   Metadado faltando é BUG, não pendência de documentação.

3. docs/genie-instrucoes.md
   O texto para colar na configuração do Genie space:
   - Contexto: distribuidora B2B de perfumaria árabe, vende para varejo
   - Glossário: ruptura, carteira, oportunidade, devolução, SKU, segmento,
     atingimento de meta, curva ABC
   - REGRA DE SAZONALIDADE, a mais importante: o pico da distribuidora é o mês
     ANTERIOR à data comemorativa, porque o varejo compra antes. Abril (Dia das
     Mães), junho (Namorados) e outubro (Black Friday) são picos; dezembro e
     janeiro são VALE, e isso é saudável, não é queda.
   - Regra de cálculo de cada métrica: receita, margem, ticket médio,
     atingimento, churn (90 dias sem compra)
   - Aviso: devolução entra com valor negativo. Para o bruto vendido,
     filtre devolucao = false.

4. O Genie space COMO CÓDIGO, dentro do bundle:
   - resources/comercial.geniespace.json com a definição serializada
   - resources/genie.genie_space.yml declarando o recurso `genie_spaces`,
     com title, description, file_path e warehouse_id

   Conteúdo do JSON: as 6 views + fato_vendas + as dimensões como data_sources,
   o texto de instruções acima em `instructions.text_instructions`, pelo menos
   5 perguntas de exemplo em `config.sample_questions`, e 6 pares
   pergunta→SQL em `instructions.example_question_sqls` com SQL já validado.

   QUATRO REGRAS DA API QUE FAZEM O DEPLOY FALHAR SE FOREM IGNORADAS:
   a) `data_sources.tables` tem que estar ORDENADO por `identifier`
   b) `column_configs` de cada tabela ordenado por `column_name`
   c) toda sample_question, text_instruction e example_question_sql precisa de
      um `id` de 32 caracteres hexadecimais minúsculos, sem hífen
   d) essas listas também têm que estar ORDENADAS por `id`

   Gere os ids de forma DETERMINÍSTICA (md5 do conteúdo da pergunta), nunca
   aleatória: assim um redeploy não recria as perguntas nem gera diff no Git
   sem motivo.

   A chave do recurso tem que ser diferente da chave do dashboard — o bundle
   recusa duas chaves iguais mesmo em tipos diferentes.

5. Acrescente ao pipeline as tarefas metricas_de_negocio e
   auditoria_de_metadado, nessa ordem, depois de gold_marts.

6. Rode:
   databricks bundle validate --target dev --profile projeto-dados-ia
   databricks bundle deploy   --target dev --profile projeto-dados-ia
   databricks bundle run rotaperfume_pipeline --target dev --profile projeto-dados-ia

   O pipeline completo tem que rodar verde de ponta a ponta, com 12 tarefas:
   raw → bronze → silver ×4 → dimensões → fato → marts → testes,
   e em paralelo métricas de negócio → auditoria de metadado
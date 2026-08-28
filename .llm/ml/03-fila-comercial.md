Continue o mesmo bundle. gold.score_propensao tem os 3.000 clientes com nota.

Crie src/ml/13-fila.sql — um arquivo SQL para rodar como sql_task.

1. A TABELA DA SEMANA: gold.fila_semanal

   As fontes e como juntar:
     gold.score_propensao   cliente_id, score, faixa, versao
     gold.features_cliente  as features, para escrever o motivo
     gold.dim_cliente       razao_social, cidade, uf
     silver.carteira        cliente_id -> vendedor_id.
                            FILTRE por vigente = true, e descarte
                            orfao_vendedor_desligado = true: vendedor
                            desligado não recebe ligação para fazer.
     silver.vendedores      vendedor_id -> nome. A carteira só tem o id.

   A ORDEM DAS OPERAÇÕES IMPORTA, e é o erro mais fácil de cometer aqui:

     1º  junte a carteira e DESCARTE quem não é elegível
         (sem carteira vigente, ou vendedor desligado)
     2º  ORDER BY score DESC LIMIT 200
     3º  ROW_NUMBER() OVER (PARTITION BY vendedor ORDER BY score DESC)

   Se o descarte vier DEPOIS do LIMIT, a fila sai com ~172 linhas em vez de
   200 — seis dos 42 vendedores estão desligados e levam junto os clientes
   deles — e o teste 1 quebra o job. Filtrando antes, sobram 2.393 clientes
   elegíveis e a fila fecha em 200 exatas, distribuídas em ~36 vendedores.
   Não use cota igual por vendedor: a carteira de um é mais quente que a do
   outro, e cota fixa obriga a gastar ligação com cliente frio.

   Colunas: vendedor, ordem, cliente_id, razao_social, cidade, uf, score,
   faixa, ticket_medio, e duas colunas escritas para gente ler:

   motivo — uma frase em português montada com CASE WHEN sobre as features,
   com os números reais do cliente dentro, via FORMAT_NUMBER:
     atraso_relativo > 3   -> 'Compra a cada N dias e está há M sem pedido.
                               Risco de perder para o concorrente.'
     atraso_relativo > 1.5 -> 'Está N vezes mais atrasado que o ritmo dele.'
     comprou_lancamento    -> 'Comprou lançamento recente. Alta chance de
                               repetir.'
     valor_total no topo   -> 'Cliente grande, R$ X no ano. Manter próximo.'
     ELSE                  -> 'Dentro do ritmo. Contato de manutenção.'
   O ELSE é obrigatório: motivo nulo quebra o teste 2.

   sugestao — o SKU mais comprado pelo cliente na marca preferida dele que
   ele NÃO comprou nos últimos 90 dias, com o saldo vindo do snapshot mais
   recente de silver.estoque (a tabela é um snapshot semanal: pegue
   max(data_snapshot) por sku, não a tabela inteira).

2. AS QUATRO FERRAMENTAS, como funções SQL no Unity Catalog, cada uma com
   COMMENT em português dizendo para que serve — é o COMMENT que o agente lê:

   gold.priorizar_carteira(p_vendedor STRING, p_quantos INT)
     RETURNS TABLE — a fatia da fila_semanal daquele vendedor, em ordem
   gold.contexto_cliente(p_cliente_id INT)
     RETURNS TABLE — histórico, ticket médio, marcas preferidas, última compra
   gold.sugerir_produtos(p_cliente_id INT)
     RETURNS TABLE — o que ele compra e parou de comprar nos últimos 90 dias
   gold.checar_disponibilidade(p_sku STRING)
     RETURNS TABLE — saldo e ruptura no snapshot mais recente

   Prefixe TODO parâmetro com p_: parâmetro com o mesmo nome de uma coluna
   fica ambíguo dentro do corpo da função e o CREATE falha.
   cliente_id é INT no catálogo, não BIGINT.

3. TRÊS TESTES QUE QUEBRAM O JOB, no mesmo padrão raise_error() dentro de
   CASE WHEN que a noite 2 usa:
   - a fila tem exatamente 200 linhas
   - nenhuma linha com motivo nulo ou vazio
   - nenhum score fora do intervalo [0, 1]

A ORDEM DOS PASSOS 4 E 5 IMPORTA, e é o erro mais fácil de cometer aqui: o
Genie RECUSA referenciar tabela que ainda não existe. Se o deploy do Genie
acontecer antes de fila_semanal ser criada, ele morre com
"PERMISSION_DENIED ... Table ... does not exist" — e a mensagem não diz que o
problema é ordem. Crie a tabela primeiro (rode a tarefa, ou o SQL pelo
scripts/run_sql.py), e só então faça o deploy com o Genie atualizado.

4. Acrescente uma PÁGINA ao dashboard da noite 2
   (resources/dashboard-comercial.lvdash.json), chamada "Fila da semana":
   um filtro de vendedor e a tabela com ordem, cliente, cidade, nota, faixa,
   motivo e sugestão. É onde o vendedor vai ver a lista — sem isso, os 200
   ficam numa tabela que ele nunca abre.

   NÃO renomeie a chave do recurso do dashboard: trocar a chave faz o bundle
   apagar e recriar, com URL nova.

5. Some gold.fila_semanal e gold.score_propensao ao Genie Space que já existe
   em resources/ (genie.genie_space.yml e o comercial.geniespace.json), com a
   instrução:
   "Use sempre as tabelas e funções deste espaço. Nunca invente número,
    nome de cliente ou quantidade de estoque."

COMMENT em português na TABELA (a auditoria quebra o job sem ele) e TAMBÉM em
todas as colunas de fila_semanal: é o comentário de coluna que o Genie lê para
responder sem inventar. Nas funções, o COMMENT é o que diz ao agente quando
usar cada uma.

Registre a tarefa ml_fila em resources/pipeline.job.yml, depois de ml_modelo,
e faça o deploy.

NÃO rode o job inteiro para testar: rode só a tarefa nova, com
bash scripts/rodar-tarefa.sh <perfil> ml_fila — o job completo leva 3m30 e
a tarefa sozinha 35s.
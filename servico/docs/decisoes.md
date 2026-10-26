# Decisões de projeto

Cada decisão diz o que foi escolhido, por quê, o que foi descartado e qual o custo. Tudo aqui foi verificado por teste
ou por execução real (a carga e a API rodaram contra o Databricks e o PostgreSQL reais).

## 1. Um PostgreSQL entre o Databricks e a API

A API não consulta o Databricks: ela lê uma cópia local. **Por quê:** o warehouse leva dezenas de segundos para
responder a primeira consulta e custa enquanto está ligado; uma API precisa de milissegundos e de um serviço sempre
disponível. **Custo:** os dados são um retrato (snapshot) da última carga, e a API informa isso em `meta`.

## 2. Carga por substituição total, em uma transação

A carga lê tudo (cerca de 138 mil linhas na carga de referência) e troca as 6 tabelas com `DELETE` seguido de `COPY`, numa única transação.
**Por quê:** o conjunto é pequeno e é sempre um retrato completo; substituir é mais simples e mais fácil de provar que
mesclar. Repetir a carga dá exatamente o mesmo resultado (provado por impressão digital das tabelas). **`DELETE` e não
`TRUNCATE`:** o `TRUNCATE` trava as leituras até o fim; com `DELETE`, quem lê continua vendo os dados antigos até o
`COMMIT`.

## 3. O log da carga usa três transações separadas

(A) grava "em andamento" e confirma na hora; (B) troca os dados e marca "concluída", tudo ou nada; (C) marca "falha".
**Por quê:** se a falha desfizesse o próprio registro dela, não sobraria rastro. A troca só vale se o log ainda estiver
"em andamento" (se outra carga o marcou como interrompido, a troca é desfeita).

## 3b. Uma carga de cada vez

Um cadeado do PostgreSQL (`pg_try_advisory_lock`) impede duas cargas ao mesmo tempo: a segunda desiste (código de saída
2). Cargas que ficaram "em andamento" porque o processo morreu viram "falha" na carga seguinte.

## 4. Conferir antes de apagar

Antes do `DELETE`, a carga confere na memória: nenhuma tabela vazia, nenhuma com menos de 50% da carga anterior, chaves
únicas e chaves estrangeiras fechadas. **Por quê:** uma leitura incompleta do Databricks não pode esvaziar o banco.

## 5. Mensagens de erro sem valores

O texto de um erro do PostgreSQL repete os valores da linha (campo `DETAIL`). Um teste prova o vazamento. Por isso o
log guarda só a etapa, o tipo, o código, a tabela e a restrição, e a saída da carga nunca imprime valores de linhas.

## 6. Databricks: perfil OAuth, nunca token em arquivo

A conexão usa o perfil do Databricks CLI. O navegador de login é bloqueado de propósito (um processo automático não deve
abrir janelas), e um cronômetro de 30 minutos encerra a carga se algo travar.

## 7. A API só lê, em duas camadas

A garantia de verdade é o papel `parfum_api`, que tem apenas `SELECT` nas 7 tabelas (testado contra o `002_perfis.sql`:
`INSERT`, `UPDATE`, `DELETE`, `TRUNCATE`, `CREATE` e `DROP` são negados, e o papel consegue executar todas as consultas da
API). A segunda camada, a sessão aberta em modo somente leitura, protege contra um erro de código da própria API, mas não
contra quem tiver a senha: quem se conecta pode desligá-la, e por isso ela não é a garantia.

## 8. Cada requisição vê uma única fotografia do banco

As rotas que fazem mais de uma consulta usam `REPEATABLE READ`. **Por quê:** se uma carga terminasse no meio de uma
requisição, a resposta misturaria dados antigos e novos.

## 9. Erros previsíveis e sem vazamento

Erros esperados saem como `{"detalhe": ...}`. Banco fora do ar é `503` sem host, usuário ou senha. `/saude` não consulta
o banco (a API está viva); `/pronto` consulta (a API está útil). Inconsistência conhecida: o `422` mantém o formato
padrão do FastAPI (`detail`).

## 10. `sem_ruptura` exige estoque confirmado

Produto sem informação de estoque também sai da lista. **Por quê:** é melhor não sugerir o que pode não existir.
`defasado` avisa quando o snapshot do produto é anterior ao snapshot global.

## 11. Como sabemos que funciona

Testes contra PostgreSQL real, não simulações; cada regra importante tem um **defeito proposital** (mutante) que o teste
precisa pegar; piso de cobertura de 95%; teste do servidor `uvicorn` de verdade; teste de contrato (as 6 rotas, `meta`,
`404` e `503` documentados); e arquivos entregues com impressão digital (SHA-256) conferida. Uma revisão independente do
carregador achou 4 defeitos reais, todos reproduzidos por teste e corrigidos.

## 12. Imagem Docker mínima

Só as dependências de produção (sem `pytest`, `ruff`, Databricks nem `pandas`, conferido dentro da imagem), usuário sem
privilégios, e o `.env` nunca entra na imagem (`.dockerignore`).

## 13. Sem autenticação, por enquanto

A API não pede senha nem chave, e a decisão é consciente: ela só escuta em `127.0.0.1` (o Compose não a expõe na rede) e os
dados de origem são, com quase certeza, sintéticos (os CNPJs do CSV têm dígitos verificadores inválidos). Antes de expô-la
fora desta máquina ela precisa de autenticação, HTTPS e limite de requisições, e a lista de razões sociais e nomes de
vendedores que ela devolve precisa ser reavaliada.

## 14. Conexões e limites de tempo

O pool testa cada conexão antes de emprestá-la: se o PostgreSQL reiniciar, a próxima requisição recebe uma conexão nova em
vez de um erro. Cada sessão da API tem limites: uma consulta é cancelada após 10 s, a espera por um lock de outra sessão
desiste após 3 s e uma transação parada por 30 s é encerrada. **Por quê:** sem eles, um lock esquecido (um `TRUNCATE` ou
`ALTER` manual) prenderia as 5 conexões do pool e toda a API passaria a responder `503`. Testado: derrubar as conexões,
segurar um lock forte e abrir uma transação de carga sem `COMMIT` (esta **não** bloqueia a leitura: quem lê continua vendo
os dados antigos).

## 15. A dependência de teste `httpx2`

O `TestClient` do FastAPI precisa de um cliente HTTP, e hoje ele é o `httpx2`: o sucessor do `httpx`, do mesmo autor (Tom
Christie), publicado em `github.com/pydantic/httpx2` e exigido pelo próprio `starlette` 1.7.0 (extra `full`). A origem foi
conferida no PyPI e no `uv.lock`. Ele só existe no grupo de desenvolvimento, nunca na imagem Docker.

## 16. O modelo de propensão, que alimenta os scores

Os scores que a API serve vêm do modelo `gold.propensao_compra`, registrado no Unity Catalog (alias `@prod`) e treinado
com `HistGradientBoostingClassifier`. Valores lidos no run do MLflow da versão em produção (verificados em 25/10/2026):
AUC de 0,874 no holdout de 25%; entre os 200 primeiros clientes do ranking (validação cruzada, 5 partes), 87 compraram,
contra uma taxa base de 10,1%, ou seja, um ganho (lift) de 4,30 vezes. Os baselines, medidos no mesmo holdout, ficaram
abaixo: "quem está atrasado" 0,772, "quem compra mais" 0,610 e "quem comprou há pouco" 0,358. Este último, abaixo de 0,5,
ordena pior do que o acaso: neste conjunto, comprar há pouco indica quem **não** vai comprar logo (inferência a partir da
métrica, não uma medição direta). Cautelas: os dados são sintéticos, então os números mostram que o método funciona, e
não quanto renderia numa empresa real; e o treino é determinístico (`random_state=42`), compatível com a versão de
25/10 ter repetido as métricas que já constavam no README do projeto.

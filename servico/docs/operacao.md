# Guia de operação

Todos os comandos partem da raiz do repositório. O contêiner do banco se chama `rotaperfume-servico-banco-1`.

## Depois de reiniciar o computador ou o Docker

O banco não volta sozinho. Abra o Docker Desktop e rode:

```bash
docker start rotaperfume-servico-banco-1
docker exec rotaperfume-servico-banco-1 pg_isready -U parfum -d parfum
```

Espere `accepting connections`.

## Rodar uma carga

Veja o comando no [README](../README.md). Se `env | grep DATABRICKS_` mostrar variáveis (a própria CLI do Databricks
pode criar marcadores), a carga só funciona sem elas; remova-as apenas do processo, sem alterar o seu terminal:
`env $(env | grep -o '^DATABRICKS_[A-Za-z_]*' | sed 's/^/-u /') ...`.

| Código de saída | Significa |
|---|---|
| `0` | Carga concluída |
| `1` | Falha (o motivo foi impresso e gravado no log) |
| `2` | Já havia outra carga em andamento; esta desistiu sem alterar nada |

Na carga de referência, a leitura do Databricks levou cerca de 12 s (mais a abertura da conexão) e a gravação de 1 a 2 s.

## Conferir o que foi carregado

```bash
docker exec rotaperfume-servico-banco-1 psql -U parfum -d parfum -c "select carga_id, status, data_referencia_score, snapshot_estoque_global, contagens, erro from carga_log order by 1"
```

## Quando uma carga falha

O banco **continua com os dados da carga anterior** (a troca é tudo ou nada). Leia a coluna `erro` de `carga_log`:
ela começa por `etapa=` e `tipo=`.

| `etapa=` | Causa provável | O que fazer |
|---|---|---|
| `extracao` | Databricks indisponível, login expirado, consulta ou colunas diferentes do esperado | Refaça o login (`databricks auth login --profile DataJourney`) e rode de novo |
| `conferencia` | Dados suspeitos: tabela vazia, menos de 50% da carga anterior, chave repetida ou sem pai | **Não force.** Investigue o Databricks antes de repetir |
| `gravacao` | Violação de uma restrição do esquema (o log traz o nome dela) | Compare o esquema com os dados novos |
| `interrompida` | O processo morreu no meio | Rode de novo: a carga seguinte limpa o registro |

## Senhas

Ficam só em `servico/.env` (fora do Git). Nunca as imprima. Para trocar a senha da API, apague do `.env` (num editor) as
duas linhas `POSTGRES_API_USUARIO` e `POSTGRES_API_SENHA` e repita o passo 3 da primeira vez no [README](../README.md);
sem apagar antes, o passo acrescentaria linhas repetidas. Se o `ALTER ROLE` falhar, o PostgreSQL pode registrar o texto do
comando, com a senha, no próprio log: nesse caso defina uma senha nova.

## A API em contêiner

```bash
docker compose -f servico/docker-compose.yml --profile api up -d --build api
docker compose -f servico/docker-compose.yml --profile api rm -sf api
```

O segundo comando remove só o contêiner da API. Nunca use `docker compose down -v` neste projeto: o `-v` apaga os dados.

## Limitações conhecidas

- Os dados da API são um **retrato** da última carga, e a carga não é agendada. O job do pipeline roda todo dia às 06:00
  (horário de Brasília; verificado em 25/10/2026) e, como `vigente` e `ativo` dependem de `CURRENT_DATE()`, o conteúdo do
  Gold muda com a data: rode a carga de novo para a API refletir o dia.
- O histórico de execuções do job tem lacunas (por exemplo, nenhuma execução entre 16/09 e 21/10). Nenhuma execução
  listada falhou, e a causa das lacunas não foi confirmada: seriam necessários os logs de auditoria do workspace.
- No Gold, a fila e a função `fila_do_vendedor` usam o nome do vendedor, e 2 pares de vendedores têm o mesmo nome (ids 31 e
  37, e 34 e 36). A API usa o `vendedor_id` e não é afetada, mas o dashboard e as consultas por nome misturam as carteiras
  de 34 e 36.
- Os dados de origem são, com quase certeza, sintéticos (veja "Sobre os dados" no [README](../README.md)); é uma
  conclusão por evidência, não uma confirmação da origem.
- Muitos produtos têm snapshot de estoque anterior ao global (a API sinaliza com `defasado`).
- A API não tem autenticação e só escuta em `127.0.0.1`: não a exponha na rede assim.
- O perfil e o identificador do warehouse do Databricks estão fixos em `carga/extracao.py`.
- O `422` usa o formato `detail` do FastAPI, diferente do `detalhe` dos demais erros.
- `sem_ruptura` ainda inclui produtos descontinuados e trata saldo negativo como estoque confirmado: é uma regra de
  negócio em aberto.
- O passo a passo da "primeira vez" (volume novo) não foi executado de ponta a ponta: o banco atual foi montado por etapas.

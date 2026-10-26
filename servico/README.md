# Camada de serviço do Rota Perfume

Esta pasta guarda a **camada de serviço** do projeto: ela copia os resultados analíticos do pipeline Databricks
(camadas Gold e Silver) para um PostgreSQL local e os entrega por uma **API FastAPI** de leitura.

```
Databricks (gold/silver)  --carga (python -m carga.executar)-->  PostgreSQL (6 tabelas + carga_log)
                                                                        |  papel parfum_api (só leitura)
                                                                        v
                                                              API FastAPI (/fila, /cliente, /produto)
```

Por que existe e as decisões de projeto: [docs/decisoes.md](docs/decisoes.md). Como operar no dia a dia e o que
fazer quando algo falha: [docs/operacao.md](docs/operacao.md).

## Sobre os dados

Os dados de origem (`dados/`, CSV de CRM e ERP) são, com quase certeza, **sintéticos**: não vêm de uma empresa real.
Evidências medidas nos arquivos: os dígitos verificadores dos CNPJs só estão corretos em 28 de 3.040 clientes (o que o
acaso dá; num CNPJ real seriam todos); os identificadores são sequenciais e sem lacunas (`cliente_id` de 1 a 3040,
`SKU00001` a `SKU00292`); os nomes de clientes vêm de um vocabulário de 53 palavras; e há só 12 cidades. O CSV tem 3.040
clientes e 3.000 raízes de CNPJ distintas, e a `dim_cliente` do Gold tem 3.000. É uma conclusão por evidência, não uma
confirmação da origem.

## O que você precisa

- Docker Desktop e o [uv](https://docs.astral.sh/uv/).
- O Databricks CLI autenticado com o perfil `DataJourney` (`databricks auth login --profile DataJourney --host <URL do seu workspace>`).
- Todos os comandos abaixo partem da **raiz do repositório**.

## Primeira vez

1. Crie `servico/.env` a partir de `servico/.env.example` e preencha `POSTGRES_PASSWORD`. O `.env` nunca é versionado.
2. Suba o banco: `docker compose -f servico/docker-compose.yml up -d`. Na primeira subida o PostgreSQL aplica
   `sql/001_esquema.sql` (tabelas) e `sql/002_perfis.sql` (papel `parfum_api`, sem senha).
3. Defina a senha do papel da API sem imprimi-la, e registre-a no `.env`:

   ```bash
   SENHA=$(openssl rand -hex 24)
   docker exec -i rotaperfume-servico-banco-1 psql -U parfum -d parfum -v ON_ERROR_STOP=1 <<SQL && printf '\nPOSTGRES_API_USUARIO=parfum_api\nPOSTGRES_API_SENHA=%s\n' "$SENHA" >> servico/.env
   ALTER ROLE parfum_api PASSWORD '$SENHA';
   SQL
   unset SENHA
   ```

4. Instale as dependências: `cd servico && uv sync --group carga`.
5. Rode a carga (lê o Databricks, grava no PostgreSQL):

   ```bash
   cd servico && ( set -a; . ./.env; set +a; PGHOST=127.0.0.1 PGPORT="$POSTGRES_PORTA" PGUSER="$POSTGRES_USER" PGPASSWORD="$POSTGRES_PASSWORD" PGDATABASE="$POSTGRES_DB" uv run --group carga python -m carga.executar )
   ```

6. Suba a API: `docker compose -f servico/docker-compose.yml --profile api up -d --build api` (porta `API_PORTA`, padrão 8000).

## Variáveis de ambiente

| Variável | Para quê | Padrão |
|---|---|---|
| `POSTGRES_USER`, `POSTGRES_DB`, `POSTGRES_PASSWORD` | Dono do banco (usado pelo contêiner e pela carga) | `parfum`, `parfum`, sem padrão |
| `POSTGRES_PORTA` | Porta do banco no seu computador | `5433` |
| `POSTGRES_HOST` | Onde a API procura o banco | `127.0.0.1` (no Compose: `banco`) |
| `POSTGRES_API_USUARIO`, `POSTGRES_API_SENHA` | Papel somente leitura da API | `parfum_api`, sem padrão |
| `API_PORTA` | Porta da API no seu computador | `8000` |

## As rotas

Toda resposta de dados traz `meta` (a carga de onde vêm, com as datas de referência). Erros esperados saem como
`{"detalhe": "..."}`. Documentação interativa em `/docs`.

| Rota | O que devolve | Parâmetros |
|---|---|---|
| `GET /saude` | A aplicação está no ar (não consulta o banco) | |
| `GET /pronto` | O banco responde (503 se não) | |
| `GET /fila/{vendedor_id}` | A fila semanal do vendedor, na ordem de atendimento | |
| `GET /cliente/{cliente_id}/contexto` | Resumo do histórico de compras e as marcas preferidas | |
| `GET /cliente/{cliente_id}/produtos-sugeridos` | Produtos sugeridos, do mais para o menos recomendado | `limit` (1 a 100, padrão 20), `sem_ruptura` |
| `GET /produto/{sku}/disponibilidade` | Saldo e ruptura, com `defasado` se o snapshot é antigo | |

Exemplo: `curl -s http://127.0.0.1:8000/fila/21`. Códigos: `404` (não existe), `422` (parâmetro inválido), `503` (sem
carga concluída ou banco indisponível).

## Testes

```bash
cd servico && ( set -a; . ./.env; set +a; PGHOST=127.0.0.1 PGPORT="$POSTGRES_PORTA" PGUSER="$POSTGRES_USER" PGPASSWORD="$POSTGRES_PASSWORD" uv run --group carga pytest --cov )
```

Os testes usam um PostgreSQL **de verdade**: cada teste cria e apaga um banco próprio (o banco `parfum` nunca é tocado).
A cobertura mínima é 95% (`pyproject.toml`). O CI (`.github/workflows/ci.yml`) roda estilo (`ruff`), os testes com
cobertura e a construção da imagem Docker.

## Estrutura

| Pasta | Conteúdo |
|---|---|
| `app/` | A API: rotas, pool de conexões, modelos de resposta |
| `carga/` | O carregador Databricks para PostgreSQL |
| `sql/` | Esquema e papéis do PostgreSQL |
| `tests/` | `test_carga/` (carregador), `test_api/` (API, contrato, servidor real, documentação) |
| `docs/` | Decisões de projeto e guia de operação |

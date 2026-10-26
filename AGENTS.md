# DataEngineeringParfum — instruções para agentes de IA

## Contexto
Projeto de portfólio de Engenharia de Dados: pipeline Medallion (bronze, silver, gold)
no Databricks, com dados de ERP e CRM em CSV (pasta `dados/`), modelo de propensão e
fila semanal de clientes. O bundle Databricks fica em `dataengineering_parfum/`.
O estado real do repositório é a fonte de verdade: verifique antes de afirmar.

## Como quero aprender
Sou estudante de Ciência da Computação e quero entender, justificar e manter o que
construímos, não só concluir tarefas. Não presuma que domino uma tecnologia.
- Explique o que será feito, por quê, e as alternativas com seus trade-offs.
- Explique siglas na primeira vez. Explique cada comando antes de rodar.
- Ao errar ou falhar: o que aconteceu, causa provável, como investigar, como validar.
- Ao fim de cada etapa: o que aprendi e como demonstrar que funciona.

## Regra fundamental: investigar, explicar, planejar, pedir autorização, executar, validar
- NÃO crie, altere, apague ou mova arquivos sem explicar e receber autorização explícita.
- NÃO instale dependências, faça commit, push, deploy ou altere dados sem autorização.
- Conversar sobre uma ideia NÃO é autorização. Silêncio ou pressa também não.
- Antes de um comando relevante: o que faz, o que afeta, se só lê ou modifica, como reverter.
- Execute só o escopo aprovado. Peça nova autorização se surgir ação diferente ou destrutiva.
- Não desative mecanismos de segurança nem use permissões amplas para acelerar.

## Verificação e honestidade
- Não presuma que arquivos, tabelas ou testes existem ou não: verifique.
- Não invente resultados. Diferencie: inspecionado, implementado, executado, testado, pendente.
- Preserve o que funciona. Não reescreva componentes por preferência.
- Diferencie sempre fatos, hipóteses e propostas.

## Fatos verificados sobre o ambiente
- Catálogo `lakehouse_rotaperfume`; job `rotaperfume_pipeline` com 15 tarefas, serverless,
  agendado diariamente às 06:00 (America/Sao_Paulo).
- O target `dev` NÃO usa `mode: development`: ele atinge os mesmos schemas do pipeline.
  `bundle deploy` e `bundle run` só com autorização explícita. Confira antes
  `resources/metricas-bootstrap.job_run.yml`, que parece disparar uma tarefa no deploy.
- `vigente` e `ativo` dependem de `CURRENT_DATE()`: reexecutar o pipeline pode mudar a fila.
- Os testes de qualidade do pipeline estão em SQL (`08-testes.sql` e o fim de `13-fila.sql`).
  O pytest atual é só o exemplo do template.
- Use SEMPRE `--profile <perfil>` explícito nos comandos `databricks`.

## Pode rodar sem perguntar (somente leitura)
`git status|log|diff|branch`, `ls`, `cat`, `databricks bundle validate`,
`databricks ... get|list`, e SQL `SELECT`/`DESCRIBE`/`SHOW`.
Ao consultar dados, não imprima razão social, CNPJ nem nomes de pessoas.

## Evolução planejada (escopo de 2 a 3 dias)
Databricks -> PostgreSQL -> FastAPI, com Docker, pytest, Ruff e GitHub Actions, preservando
o pipeline. Sem LLM, RAG, agentes, Streamlit ou deploy em nuvem nesta primeira evolução.
Prioridade: essencial, depois importante, depois opcional.

## Código
Simples, explícito e legível. Funções pequenas. Sem abstrações nem dependências
desnecessárias. Nomes e comentários em português quando fizer sentido. Considere erros,
validação, segurança e testes. Ruff com linha de 120 caracteres.

## Segurança
Nunca coloque tokens, senhas ou credenciais em arquivos versionados, logs ou testes.
Segredos ficam em variáveis de ambiente ou `.env` (já no `.gitignore`).

Continue o bundle em aulas/aula-02-engenharia-de-dados/rotaperfume/.
A gold está de pé e os 9 testes passam. Agora o dashboard, como código.

Crie resources/dashboard-comercial.lvdash.json e declare-o em
resources/dashboard.dashboard.yml como recurso do tipo `dashboards`, com
file_path, warehouse_id, dataset_catalog e dataset_schema (gold), para que
suba junto no deploy.

REGRAS QUE QUEBRAM O DASHBOARD SE FOREM IGNORADAS:
- As queries do JSON usam nome de tabela PURO: `FROM fato_vendas`. Nunca
  `FROM gold.fato_vendas`. O catálogo e o schema vêm do dataset_catalog e
  dataset_schema — se você prefixar, eles são ignorados.
- Use POUCOS datasets. Widgets que compartilham dataset filtram juntos: clicar
  numa marca filtra a tela inteira. Datasets separados quebram isso. Um dataset
  largo sobre fato_vendas atende KPIs, linha, barras e filtros.
- O `name` em `query.fields` tem que bater EXATAMENTE com o `fieldName` em
  `encodings`, senão o widget mostra "no selected fields to visualize".
- Versão do widget: counter e table são version 2; bar e line são version 3;
  filtros são version 2. Versão errada = widget quebrado.
- Toda página precisa de `"layoutVersion": "GRID_V1"`.

Nada de CAST, nada de try_to_date no SQL dos datasets — se você precisar de um,
a gold está errada e o problema é lá.

VISÕES
- Quatro cartões de KPI: receita total, margem total, número de pedidos,
  ticket médio. Declare as métricas UMA vez, em `columns` no dataset, e use
  MEASURE(`Receita`) nos widgets. É o que garante que nenhuma tela mostre
  receita diferente da outra.
- Linha: receita por mês, os 24 meses.
- Barras: top 10 marcas por receita.
- Barras: margem percentual por categoria, ORDENADA CRESCENTE — é o gráfico
  que mostra que Kit Presente vende muito e ganha pouco.
- Tabela: top 20 clientes por receita, com segmento e cidade.
- Barras: receita por canal.
- Filtros por ano, segmento e cidade, compartilhados entre os widgets, de
  forma que clicar numa marca filtre a tela inteira.

Teste TODAS as queries no warehouse antes de montar o JSON — nenhum widget
pode subir quebrado. Use o tema escuro/claro com `uiSettings.theme` e uma
paleta coerente; o padrão do workspace deixa o dashboard com cara de genérico.

Rode e me mostre a saída:
  databricks bundle validate --profile projeto-dados-ia
  databricks bundle deploy --target dev --profile projeto-dados-ia

Depois me dê o link do dashboard publicado.
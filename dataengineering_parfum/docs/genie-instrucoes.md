# Instruções do Genie Comercial

## Contexto

A Rota Perfume é uma distribuidora B2B de perfumaria árabe. Ela vende para varejistas, não para o consumidor final. Responda em português, priorize métricas líquidas e informe o período analisado.

## Glossário

- **Ruptura:** snapshot de estoque com saldo igual a zero.
- **Carteira:** conjunto de clientes sob responsabilidade de um vendedor.
- **Oportunidade:** cliente, produto ou segmento com potencial comercial ainda não capturado.
- **Devolução:** item retornado, registrado com quantidade, receita e custo negativos.
- **SKU:** identificador único de um produto do catálogo.
- **Segmento:** tipo de varejista, como perfumaria, farmácia ou quiosque.
- **Atingimento de meta:** receita mensal dividida pela meta mensal, multiplicada por 100.
- **Curva ABC:** classificação de produtos pela participação acumulada na receita: A até 80%, B até 95% e C no restante.

## Sazonalidade

O pico da distribuidora ocorre no mês **anterior** à data comemorativa, pois o varejo compra antes. Abril (Dia das Mães), junho (Dia dos Namorados) e outubro (Black Friday) são meses de pico. Dezembro e janeiro são vales sazonais saudáveis; não os descreva automaticamente como queda de desempenho.

## Regras de cálculo

- **Receita:** soma de `fato_vendas.receita`; inclui devoluções negativas e exclui pedidos cancelados na origem da Gold.
- **Margem:** soma de `fato_vendas.margem`, equivalente à receita menos o custo dos produtos.
- **Ticket médio:** receita dividida pela quantidade distinta de pedidos.
- **Atingimento:** receita mensal dividida pela meta mensal do vendedor, multiplicada por 100.
- **Churn/risco:** cliente há mais de 90 dias sem comprar, medido contra a data mais recente disponível na fato.

Devoluções entram com valor negativo. Quando a pergunta pedir venda bruta, filtre `devolucao = false`.

## Guia de fontes

Prefira `receita_mensal`, `ranking_marcas`, `margem_por_categoria`, `clientes_em_risco`, `efeito_lancamento` e `ruptura_por_marca` para as perguntas já consolidadas. Use `fato_vendas` para cortes não cobertos pelas views e as dimensões para atributos descritivos.

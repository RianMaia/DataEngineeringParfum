# Dashboards do Databricks

`dataegineering-parfum.lvdash.json` é a definição do dashboard **DataEgineering - Parfum**, criado pela interface do
Databricks com o Genie. Ele **não faz parte do bundle**: vive só no workspace, e esta é uma cópia de segurança, exportada
em 25/10/2026 só com leitura. Tem 3 datasets e 2 páginas; o arquivo guarda as consultas SQL e a configuração dos gráficos,
sem dados.

A pasta fica **fora** de `dataengineering_parfum/` de propósito: assim o `bundle deploy` não a implanta e não sobrescreve
nada no workspace. O dashboard lê as tabelas e views do Gold ao vivo, então ele reflete o dia da última execução do job.

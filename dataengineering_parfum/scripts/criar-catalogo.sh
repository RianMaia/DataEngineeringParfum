#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Uso: $0 <profile>" >&2
  exit 64
fi

profile="$1"
catalog="lakehouse_rotaperfume"
warehouse_id="107dd2f1b9c84d4d"

# Este catalogo nao faz parte do bundle porque, no Free Edition com Default
# Storage habilitado, a API do Unity Catalog exige um MANAGED LOCATION que a
# conta gratuita nao possui e responde com 400 INVALID_STATE. O DDL executado
# pelo SQL Warehouse funciona nessa configuracao.
databricks experimental aitools tools query \
  --warehouse "$warehouse_id" \
  --profile "$profile" \
  "CREATE CATALOG IF NOT EXISTS \`$catalog\` COMMENT 'Lakehouse do projeto Rota Perfume'"

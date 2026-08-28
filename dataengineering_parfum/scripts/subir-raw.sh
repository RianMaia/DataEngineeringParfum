#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Uso: $0 <profile>" >&2
  exit 64
fi

profile="$1"
catalog="lakehouse_rotaperfume"
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
bundle_root="$(cd -- "$script_dir/.." && pwd)"
data_root="$bundle_root/../dados"

if [[ ! -d "$data_root" ]]; then
  echo "Erro: diretorio de dados nao encontrado em $data_root." >&2
  echo "Disponibilize os CSVs em ../dados antes de executar este script." >&2
  exit 1
fi

expected_files=(
  "erp/produtos.csv"
  "erp/pedidos.csv"
  "erp/itens_pedido.csv"
  "erp/pagamentos.csv"
  "erp/estoque.csv"
  "crm/clientes.csv"
  "crm/vendedores.csv"
  "crm/carteira.csv"
  "crm/oportunidades.csv"
  "crm/visitas.csv"
)

for relative_path in "${expected_files[@]}"; do
  if [[ ! -f "$data_root/$relative_path" ]]; then
    echo "Erro: arquivo esperado nao encontrado: $data_root/$relative_path" >&2
    exit 1
  fi
done

databricks fs cp --recursive --overwrite \
  "$data_root/erp" \
  "dbfs:/Volumes/$catalog/bronze/raw/erp" \
  --profile "$profile"

databricks fs cp --recursive --overwrite \
  "$data_root/crm" \
  "dbfs:/Volumes/$catalog/bronze/raw/crm" \
  --profile "$profile"

echo "Upload concluido para /Volumes/$catalog/bronze/raw/{erp,crm}."

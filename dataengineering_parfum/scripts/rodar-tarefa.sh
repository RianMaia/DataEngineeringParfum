#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "Uso: $0 <profile> <task_key>" >&2
  exit 64
fi

profile="$1"
task_key="$2"

if [[ ! "$profile" =~ ^[A-Za-z0-9._-]+$ ]]; then
  echo "Erro: profile invalido: $profile" >&2
  exit 64
fi

if [[ ! "$task_key" =~ ^[A-Za-z0-9_-]+$ ]]; then
  echo "Erro: task_key invalida: $task_key" >&2
  exit 64
fi

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
bundle_root="$(cd -- "$script_dir/.." && pwd)"

cd "$bundle_root"
exec databricks bundle run rotaperfume_pipeline \
  --only "$task_key" \
  --target dev \
  --profile "$profile"

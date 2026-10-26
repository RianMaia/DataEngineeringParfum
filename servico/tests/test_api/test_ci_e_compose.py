"""Regras de segurança do workflow do GitHub Actions e do Compose, conferidas no texto dos arquivos."""

import re
from pathlib import Path

import pytest

RAIZ_SERVICO = Path(__file__).resolve().parents[2]
CI = RAIZ_SERVICO.parent / ".github" / "workflows" / "ci.yml"
COMPOSE = RAIZ_SERVICO / "docker-compose.yml"
sem_ci = pytest.mark.skipif(not CI.exists(), reason="o ci.yml não está neste checkout")


@sem_ci
def test_o_workflow_so_pede_leitura_do_repositorio():
    assert re.search(r"^permissions:\n  contents: read$", CI.read_text(encoding="utf-8"), re.MULTILINE)


@sem_ci
def test_toda_action_do_workflow_esta_fixada_por_sha_de_commit():
    usos = re.findall(r"^\s*-?\s*uses:\s*(\S+)", CI.read_text(encoding="utf-8"), re.MULTILINE)
    assert usos, "o workflow deveria usar actions"
    for uso in usos:
        assert re.fullmatch(r"[\w.\-/]+@[0-9a-f]{40}", uso), f"action não fixada por SHA: {uso}"


@sem_ci
def test_o_ci_recusa_um_uv_lock_desatualizado_e_fixa_a_versao_do_uv():
    texto = CI.read_text(encoding="utf-8")
    assert "uv sync --locked" in texto and "--frozen" not in texto
    assert 'version: "0.11.7"' in texto
    assert texto.count("timeout-minutes:") >= 2


def test_o_servico_api_do_compose_e_endurecido():
    bloco = COMPOSE.read_text(encoding="utf-8").split("\n  api:\n", 1)[1]
    assert "read_only: true" in bloco
    assert re.search(r"cap_drop:\n\s+- ALL", bloco)
    assert "no-new-privileges:true" in bloco
    assert '"127.0.0.1:${API_PORTA:-8000}:8000"' in bloco

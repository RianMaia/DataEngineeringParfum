"""O job do pipeline limita tempo e concorrência, avisa quando falha, e o e-mail não fica no repositório."""

import re
from pathlib import Path

import pytest

BUNDLE = Path(__file__).resolve().parents[3] / "dataengineering_parfum"
JOB = BUNDLE / "resources" / "pipeline.job.yml"
DATABRICKS_YML = BUNDLE / "databricks.yml"
sem_bundle = pytest.mark.skipif(not JOB.exists(), reason="o bundle não está neste checkout")


@sem_bundle
def test_o_job_tem_limite_de_tempo_uma_execucao_por_vez_e_aviso_de_falha():
    texto = JOB.read_text(encoding="utf-8")
    assert re.search(r"^      max_concurrent_runs: 1$", texto, re.MULTILINE)
    assert re.search(r"^      timeout_seconds: 3600$", texto, re.MULTILINE)
    assert "      email_notifications:\n        on_failure:\n          - ${var.alerta_email}\n" in texto


@sem_bundle
def test_a_variavel_do_email_nao_tem_valor_padrao():
    bloco = re.search(r"^  alerta_email:\n((?:    .*\n)+)", DATABRICKS_YML.read_text(encoding="utf-8"), re.MULTILINE)
    assert bloco, "a variável alerta_email não está declarada"
    assert "default" not in bloco.group(1)


@sem_bundle
def test_nenhum_email_aparece_nos_arquivos_do_bundle():
    for arquivo in (JOB, DATABRICKS_YML):
        assert not re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", arquivo.read_text(encoding="utf-8")), arquivo.name

"""A documentação não pode ficar para trás: se o código mudar, estes testes avisam."""

import re
from pathlib import Path

import pytest

from app.main import app

RAIZ_SERVICO = Path(__file__).resolve().parents[2]
README = (RAIZ_SERVICO / "README.md").read_text(encoding="utf-8")
DOCUMENTOS = {
    "README.md": README,
    "docs/decisoes.md": (RAIZ_SERVICO / "docs" / "decisoes.md").read_text(encoding="utf-8"),
    "docs/operacao.md": (RAIZ_SERVICO / "docs" / "operacao.md").read_text(encoding="utf-8"),
}


def test_o_readme_documenta_todas_as_rotas_da_api():
    for caminho in app.openapi()["paths"]:
        assert f"`GET {caminho}`" in README, caminho


def test_toda_variavel_de_ambiente_do_projeto_esta_documentada():
    fontes = [RAIZ_SERVICO / "docker-compose.yml", RAIZ_SERVICO / ".env.example"]
    fontes += list((RAIZ_SERVICO / "app").glob("*.py")) + list((RAIZ_SERVICO / "carga").glob("*.py"))
    usadas = set()
    for fonte in fontes:
        usadas |= set(re.findall(r"\b(?:POSTGRES_[A-Z_]+|API_PORTA)\b", fonte.read_text(encoding="utf-8")))
    sem_doc = sorted(nome for nome in usadas if nome not in README)
    assert not sem_doc, f"variáveis sem documentação no README: {sem_doc}"


def test_os_links_entre_documentos_apontam_para_arquivos_que_existem():
    for nome, texto in DOCUMENTOS.items():
        base = (RAIZ_SERVICO / nome).parent
        for destino in re.findall(r"\]\(([^)#]+\.md)\)", texto):
            assert (base / destino).exists(), f"{nome}: link quebrado para {destino}"


def test_os_codigos_de_saida_documentados_sao_os_do_codigo():
    from carga.executar import FALHA, JA_EM_ANDAMENTO, SUCESSO

    operacao = DOCUMENTOS["docs/operacao.md"]
    for codigo in (SUCESSO, FALHA, JA_EM_ANDAMENTO):
        assert f"| `{codigo}` |" in operacao, codigo


def test_os_comandos_citados_existem():
    assert "python -m carga.executar" in README and (RAIZ_SERVICO / "carga" / "executar.py").exists()
    assert (RAIZ_SERVICO / "sql" / "001_esquema.sql").exists() and (RAIZ_SERVICO / "sql" / "002_perfis.sql").exists()
    assert "carga/extracao.py" in DOCUMENTOS["docs/operacao.md"] and (RAIZ_SERVICO / "carga" / "extracao.py").exists()


RAIZ_REPOSITORIO = RAIZ_SERVICO.parent
README_DA_RAIZ = RAIZ_REPOSITORIO / "README.md"


@pytest.mark.skipif(not README_DA_RAIZ.exists(), reason="o README da raiz não está neste checkout")
def test_o_readme_da_raiz_aponta_para_a_camada_de_servico_e_para_os_dashboards():
    texto = README_DA_RAIZ.read_text(encoding="utf-8")
    for destino in (
        "servico/README.md",
        "servico/docs/decisoes.md",
        "servico/docs/operacao.md",
        "dashboards/dataegineering-parfum.lvdash.json",
    ):
        assert destino in texto, f"o README da raiz não cita {destino}"
        assert (RAIZ_REPOSITORIO / destino).exists(), f"{destino} não existe"

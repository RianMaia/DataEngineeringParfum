"""A API rodando de verdade (processo uvicorn), e não só pelo TestClient."""

import os
import signal
import socket
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

from test_carga.dados_falsos import FonteFalsa, gerar

from carga.executar import executar

RAIZ_SERVICO = Path(__file__).resolve().parents[2]


def porta_livre():
    with socket.socket() as soquete:
        soquete.bind(("127.0.0.1", 0))
        return soquete.getsockname()[1]


def ambiente_da_api(servidor, banco, **sobrescritas):
    """O ambiente de um processo novo: sem nenhuma variável POSTGRES_* herdada, só as que o teste define."""
    ambiente = {chave: valor for chave, valor in os.environ.items() if not chave.startswith("POSTGRES_")}
    ambiente.update(
        POSTGRES_HOST=servidor["host"],
        POSTGRES_PORTA=str(servidor["port"]),
        POSTGRES_DB=banco,
        POSTGRES_API_USUARIO=servidor["user"],
        POSTGRES_API_SENHA=servidor["password"],
    )
    ambiente.update(sobrescritas)
    return {chave: valor for chave, valor in ambiente.items() if valor is not None}


def subir(ambiente, porta):
    comando = [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(porta)]
    return subprocess.Popen(
        [*comando, "--log-level", "info"],
        cwd=RAIZ_SERVICO,
        env=ambiente,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def pegar(porta, caminho):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{porta}{caminho}", timeout=5) as resposta:
            return resposta.status, resposta.read().decode()
    except urllib.error.HTTPError as erro:
        return erro.code, erro.read().decode()


def esperar_no_ar(porta, limite_segundos=20):
    import time

    fim = time.time() + limite_segundos
    while time.time() < fim:
        try:
            if pegar(porta, "/saude")[0] == 200:
                return
        except OSError:
            time.sleep(0.2)
    raise AssertionError("o servidor não respondeu a tempo")


def test_o_servidor_real_responde_com_dados_e_encerra_limpo(banco, servidor, conexoes):
    assert executar(FonteFalsa(*gerar()), *conexoes) == 0
    porta = porta_livre()
    processo = subir(ambiente_da_api(servidor, banco), porta)
    try:
        esperar_no_ar(porta)
        assert pegar(porta, "/saude") == (200, '{"status":"ok"}')
        assert pegar(porta, "/pronto") == (200, '{"status":"ok"}')
        status, corpo = pegar(porta, "/fila/1")
        assert status == 200 and '"total"' in corpo and '"meta"' in corpo
    finally:
        processo.terminate()
    saida, _ = processo.communicate(timeout=20)
    # O uvicorn encerra com o sinal repassado (-15) DEPOIS de desligar direito; a prova do desligamento é esta mensagem.
    assert "Application shutdown complete" in saida
    assert processo.returncode in (0, -signal.SIGTERM)


def test_sem_o_usuario_da_api_o_servidor_nao_sobe_e_diz_qual_variavel_falta(banco, servidor):
    ambiente = ambiente_da_api(servidor, banco, POSTGRES_API_USUARIO=None, POSTGRES_API_SENHA="SENHA_CANARIO_123")
    processo = subir(ambiente, porta_livre())
    saida, _ = processo.communicate(timeout=30)
    assert processo.returncode != 0
    assert "variáveis de ambiente não definidas: POSTGRES_API_USUARIO" in saida
    assert "SENHA_CANARIO_123" not in saida

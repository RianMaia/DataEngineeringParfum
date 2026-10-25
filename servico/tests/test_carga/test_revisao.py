"""Testes nascidos da revisão independente: cada um reproduz um defeito apontado e prova a correção."""

import subprocess
import sys
import time
from pathlib import Path

import psycopg
import pytest

from carga.executar import FALHA, executar
from carga.gravacao import gravar_dados, iniciar_log, marcar_interrompidas, registrar_falha

from .dados_falsos import FonteFalsa, contagens, gerar, log

RAIZ_SERVICO = Path(__file__).resolve().parents[2]


def test_gravacao_e_desfeita_se_outra_carga_marcou_esta_como_interrompida(conexoes, banco, servidor):
    dados, meta = gerar()
    controle, conn_dados = conexoes
    carga_id = iniciar_log(controle)
    with psycopg.connect(dbname=banco, autocommit=True, **servidor) as outra:
        assert marcar_interrompidas(outra) == 1  # a "outra carga" marca esta como falha
    totais = {nome: len(linhas) for nome, linhas in dados.items()}
    with pytest.raises(Exception, match="em_andamento"):
        gravar_dados(conn_dados, carga_id, dados, meta, totais)
    assert contagens(conn_dados) == {nome: 0 for nome in dados}  # nada ficou gravado (a transação foi desfeita)
    assert log(conn_dados)[-1][1] == "falha"  # o log continua 'falha': não foi sobrescrito por 'concluida'


def test_registrar_falha_nao_sobrescreve_uma_carga_ja_concluida(conexoes):
    dados, meta = gerar()
    controle, conn_dados = conexoes
    assert executar(FonteFalsa(dados, meta), controle, conn_dados) == 0
    carga_id = log(conn_dados)[-1][0]
    registrar_falha(controle, carga_id, "gravacao", RuntimeError("resposta do COMMIT se perdeu"))
    ultima = log(conn_dados)[-1]
    assert ultima[1] == "concluida" and ultima[2] is None


class ControleQueQuebraAoRegistrarFalha:
    """Uma conexão de controle que cai justamente na hora de registrar a falha."""

    def __init__(self, real):
        self._real = real

    def execute(self, consulta, *argumentos, **opcoes):
        if "SET status = 'falha'" in consulta and "contagens" in consulta:
            raise psycopg.OperationalError("a conexão caiu")
        return self._real.execute(consulta, *argumentos, **opcoes)


def test_falha_ao_registrar_no_log_nao_esconde_o_erro_original(conexoes, capsys):
    class FonteQueExplode(FonteFalsa):
        def ler(self, nome):
            raise KeyError("VALOR_SECRETO_NA_MENSAGEM")

    controle, conn_dados = conexoes
    codigo = executar(FonteQueExplode({}, {}), ControleQueQuebraAoRegistrarFalha(controle), conn_dados)
    assert codigo == FALHA
    saida = capsys.readouterr().out
    assert "falhou: etapa=extracao; tipo=KeyError" in saida  # o erro ORIGINAL aparece
    assert "não foi possível registrar a falha no log: OperationalError" in saida
    assert "SECRETO" not in saida


CODIGO_DO_CRONOMETRO = """
import sys, time
sys.path.insert(0, sys.argv[1])
from carga import executar as modulo
modulo.LIMITE_TOTAL_SEGUNDOS = 2
modulo.abrir_databricks = lambda: time.sleep(30)  # simula uma conexão que trava
modulo.main()
"""


def test_cronometro_de_seguranca_vale_tambem_enquanto_conecta_no_databricks():
    inicio = time.time()
    resultado = subprocess.run(
        [sys.executable, "-c", CODIGO_DO_CRONOMETRO, str(RAIZ_SERVICO)],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert time.time() - inicio < 15  # o processo foi encerrado pelo cronômetro, e não depois dos 30 s do travamento
    assert resultado.returncode == 1 and "Timeout" in resultado.stderr

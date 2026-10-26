import os
import subprocess
import sys
import time
from pathlib import Path

import psycopg

from carga import executar as modulo
from carga.executar import FALHA, JA_EM_ANDAMENTO, SUCESSO, executar

from .dados_falsos import DIA, FonteFalsa, contagens, gerar, log

RAIZ_SERVICO = Path(__file__).resolve().parents[2]

CODIGO_DO_OUTRO_PROCESSO = """
import sys
import psycopg
sys.path.insert(0, sys.argv[2])
sys.path.insert(0, sys.argv[2] + "/tests")
from carga.executar import executar
from test_carga.dados_falsos import FonteFalsa, gerar

dados, meta = gerar()
banco = sys.argv[1]
with psycopg.connect(dbname=banco, autocommit=True) as a:
    with psycopg.connect(dbname=banco, autocommit=True) as b:
        sys.exit(executar(FonteFalsa(dados, meta, espera=0.4), a, b))
"""


def test_duas_cargas_em_processos_diferentes_so_uma_roda(conexoes, banco, servidor):
    ambiente = dict(
        os.environ,
        PGHOST=servidor["host"],
        PGPORT=str(servidor["port"]),
        PGUSER=servidor["user"],
        PGPASSWORD=servidor["password"],
    )
    processo = subprocess.Popen(
        [sys.executable, "-c", CODIGO_DO_OUTRO_PROCESSO, banco, str(RAIZ_SERVICO)], env=ambiente
    )
    try:
        limite = time.time() + 15
        while time.time() < limite:  # espera a outra carga aparecer como 'em_andamento'
            if conexoes[1].execute("SELECT count(*) FROM carga_log WHERE status = 'em_andamento'").fetchone()[0]:
                break
            time.sleep(0.05)
        else:
            raise AssertionError("a outra carga nunca começou")
        dados, meta = gerar()
        assert executar(FonteFalsa(dados, meta), *conexoes) == JA_EM_ANDAMENTO
        assert processo.wait(timeout=60) == SUCESSO
    finally:
        processo.kill()
    assert [linha[1] for linha in log(conexoes[1])] == ["concluida"]  # só a carga do outro processo existe
    assert contagens(conexoes[1])["clientes"] == len(gerar()[0]["clientes"])


def configurar_ambiente(monkeypatch, servidor, banco, porta=None):
    for chave, valor in {
        "PGHOST": servidor["host"],
        "PGPORT": porta or str(servidor["port"]),
        "PGUSER": servidor["user"],
        "PGPASSWORD": servidor["password"],
        "PGDATABASE": banco,
    }.items():
        monkeypatch.setenv(chave, valor)


def test_main_ponta_a_ponta_com_databricks_falso(banco, servidor, monkeypatch, capsys):
    dados, meta = gerar()
    fonte = FonteFalsa(dados, meta)
    cronometros = []
    monkeypatch.setattr(modulo, "abrir_databricks", lambda: fonte)
    monkeypatch.setattr(modulo.faulthandler, "dump_traceback_later", lambda *a, **k: cronometros.append((a, k)))
    configurar_ambiente(monkeypatch, servidor, banco)
    assert modulo.main() == SUCESSO
    assert fonte.fechada is True
    assert cronometros == [((1800,), {"exit": True})]
    with psycopg.connect(dbname=banco, **servidor) as verificar:
        assert contagens(verificar) == {nome: len(linhas) for nome, linhas in dados.items()}
    assert "concluída" in capsys.readouterr().out


def test_main_falha_ao_conectar_no_databricks_imprime_so_o_tipo(banco, servidor, monkeypatch, capsys):
    def explode():
        raise RuntimeError("SEGREDO_NA_MENSAGEM")

    monkeypatch.setattr(modulo, "abrir_databricks", explode)
    monkeypatch.setattr(modulo.faulthandler, "dump_traceback_later", lambda *a, **k: None)
    configurar_ambiente(monkeypatch, servidor, banco)
    assert modulo.main() == FALHA
    saida = capsys.readouterr().out
    assert "falha ao conectar no Databricks: RuntimeError" in saida and "SEGREDO" not in saida


def test_main_falha_ao_conectar_no_postgres_fecha_a_fonte(banco, servidor, monkeypatch, capsys):
    fonte = FonteFalsa(*gerar())
    monkeypatch.setattr(modulo, "abrir_databricks", lambda: fonte)
    monkeypatch.setattr(modulo.faulthandler, "dump_traceback_later", lambda *a, **k: None)
    configurar_ambiente(monkeypatch, servidor, banco, porta="1")  # porta onde ninguém escuta
    assert modulo.main() == FALHA
    assert "falha ao conectar no PostgreSQL: OperationalError" in capsys.readouterr().out
    assert fonte.fechada is True


def test_volume_real_de_125735_sugestoes(conexoes, capsys):
    dados, meta = gerar(n_clientes=3000, n_skus=292, n_vendedores=42, n_fila=200, max_sugestoes=0)
    sorteio_n = 125_735
    base, resto = divmod(sorteio_n, 3000)
    sugestoes = []
    for indice, (cliente,) in enumerate(dados["clientes"]):
        quantidade = base + (1 if indice < resto else 0)
        for ordem in range(1, quantidade + 1):
            sugestoes.append((cliente, f"SKU_SECRETO_{(indice + ordem) % 292:04d}", ordem, 100 + ordem, DIA))
    dados["sugestoes_cliente"] = sugestoes
    assert len(sugestoes) == sorteio_n
    inicio = time.perf_counter()
    assert executar(FonteFalsa(dados, meta), *conexoes) == SUCESSO
    total = time.perf_counter() - inicio
    saida = capsys.readouterr().out
    gravado = next(float(l.split()[2].rstrip("s")) for l in saida.splitlines() if l.startswith("gravado em"))
    assert contagens(conexoes[1])["sugestoes_cliente"] == sorteio_n
    with capsys.disabled():  # mostra o tempo medido sem criar nenhum arquivo
        print(f"\n  volume de {sorteio_n} sugestoes: gravado em {gravado}s, total {total:.2f}s")
    assert gravado < 60  # limite folgado, para não falhar em máquina lenta

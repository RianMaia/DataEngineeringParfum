"""O maestro da carga: bloqueio, log, extração, conferência e gravação, nessa ordem.

Uso (a partir de servico/):  python -m carga.executar
A conexão com o PostgreSQL vem das variáveis padrão PGHOST, PGPORT, PGUSER, PGPASSWORD e PGDATABASE.
Nenhuma senha aparece no código, e nada que seja valor de linha é impresso.
"""

import faulthandler
import sys
import time

import psycopg

from carga.extracao import abrir_databricks, extrair_tudo
from carga.gravacao import (
    contar_tabelas,
    descrever_erro,
    gravar_dados,
    iniciar_log,
    liberar_bloqueio,
    marcar_interrompidas,
    obter_bloqueio,
    registrar_falha,
)
from carga.validacao import ErroDeValidacao, validar

LIMITE_TOTAL_SEGUNDOS = 1800  # cronômetro de segurança: encerra o processo (uma carga esquecida vira 'falha' depois)
SUCESSO, FALHA, JA_EM_ANDAMENTO = 0, 1, 2


def imprimir(*partes):
    print(*partes, flush=True)


def executar(fonte, conn_controle, conn_dados, minimo_relativo=0.5):
    """Roda uma carga completa. Devolve 0 (sucesso), 1 (falha) ou 2 (já havia outra carga em andamento)."""
    if not obter_bloqueio(conn_controle):
        imprimir("outra carga está em andamento; esta execução desistiu sem alterar nada")
        return JA_EM_ANDAMENTO
    carga_id = None
    etapa = "inicio"
    contagens = None
    try:
        abandonadas = marcar_interrompidas(conn_controle)
        if abandonadas:
            imprimir(f"{abandonadas} carga(s) esquecida(s) em andamento marcada(s) como falha")
        carga_id = iniciar_log(conn_controle)
        imprimir(f"carga {carga_id} iniciada")

        etapa = "extracao"
        inicio = time.perf_counter()
        dados, meta = extrair_tudo(fonte)
        contagens = {nome: len(linhas) for nome, linhas in dados.items()}
        resumo = ", ".join(f"{nome}={total}" for nome, total in contagens.items())
        imprimir(f"extraído em {time.perf_counter() - inicio:.1f}s: {resumo}")

        etapa = "conferencia"
        problemas = validar(dados, contar_tabelas(conn_dados), minimo_relativo)
        if problemas:
            raise ErroDeValidacao("; ".join(problemas))
        imprimir("conferência: ok")

        etapa = "gravacao"
        inicio = time.perf_counter()
        gravar_dados(conn_dados, carga_id, dados, meta, contagens)
        imprimir(f"gravado em {time.perf_counter() - inicio:.1f}s")
        imprimir(f"carga {carga_id} concluída")
        return SUCESSO
    except Exception as erro:  # noqa: BLE001 - borda do programa: registra a falha e devolve código 1
        # Primeiro imprime, para não perder o erro original se o registro no log também falhar.
        imprimir(f"carga {carga_id} falhou: {descrever_erro(etapa, erro)}")
        if carga_id is not None:
            try:
                registrar_falha(conn_controle, carga_id, etapa, erro, contagens)
            except psycopg.Error as erro_do_log:
                imprimir(f"não foi possível registrar a falha no log: {type(erro_do_log).__name__}")
        return FALHA
    finally:
        liberar_bloqueio(conn_controle)


def main():
    faulthandler.dump_traceback_later(LIMITE_TOTAL_SEGUNDOS, exit=True)  # vale desde o início, inclusive ao conectar
    fonte = None
    try:
        try:
            fonte = abrir_databricks()
        except Exception as erro:  # noqa: BLE001 - só o tipo do erro é impresso
            imprimir(f"falha ao conectar no Databricks: {type(erro).__name__}")
            return FALHA
        with psycopg.connect(autocommit=True) as conn_controle, psycopg.connect(autocommit=True) as conn_dados:
            return executar(fonte, conn_controle, conn_dados)
    except psycopg.Error as erro:
        imprimir(f"falha ao conectar no PostgreSQL: {type(erro).__name__}")
        return FALHA
    finally:
        faulthandler.cancel_dump_traceback_later()
        if fonte is not None:
            fonte.fechar()


if __name__ == "__main__":
    sys.exit(main())

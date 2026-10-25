"""Tudo que ESCREVE no PostgreSQL: o bloqueio, o log da carga e a troca dos dados em uma única transação.

As duas conexões usadas aqui estão em modo autocommit: cada comando vale na hora, e a troca dos dados
(gravar_dados) abre a sua própria transação de verdade com "with conn.transaction()".
"""

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

from carga.esquema import COLUNAS, ORDEM_APAGAR, ORDEM_INSERCAO
from carga.extracao import ErroDeExtracao
from carga.validacao import ErroDeValidacao

CHAVE_DO_BLOQUEIO = 7_240_001  # número fixo e arbitrário, só para este programa


class ErroDeLog(Exception):
    """O registro da carga no log não está como esperado. A mensagem é fixa, sem valores."""


def obter_bloqueio(conn_controle):
    """Tenta pegar o cadeado da carga SEM esperar. Devolve False se outra carga já o tem."""
    return conn_controle.execute("SELECT pg_try_advisory_lock(%s)", (CHAVE_DO_BLOQUEIO,)).fetchone()[0]


def liberar_bloqueio(conn_controle):
    try:
        conn_controle.execute("SELECT pg_advisory_unlock(%s)", (CHAVE_DO_BLOQUEIO,))
    except psycopg.Error:
        pass  # se a conexão caiu, o PostgreSQL já liberou o cadeado sozinho


def marcar_interrompidas(conn_controle):
    """Com o cadeado na mão, nenhuma carga legítima está rodando: o que está 'em_andamento' foi esquecido."""
    cursor = conn_controle.execute(
        "UPDATE carga_log SET status = 'falha', concluida_em = now(), erro = %s WHERE status = 'em_andamento'",
        ("interrompida: o processo terminou antes de concluir",),
    )
    return cursor.rowcount


def iniciar_log(conn_controle):
    """Transação A: grava 'em_andamento' e confirma na hora."""
    return conn_controle.execute("INSERT INTO carga_log DEFAULT VALUES RETURNING carga_id").fetchone()[0]


def contar_tabelas(conn):
    return {
        nome: conn.execute(sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(nome))).fetchone()[0]
        for nome in ORDEM_INSERCAO
    }


def gravar_dados(conn_dados, carga_id, dados, meta, contagens):
    """Transação B: troca as 6 tabelas e marca o log como 'concluida', TUDO OU NADA."""
    with conn_dados.transaction(), conn_dados.cursor() as cursor:
        for nome in ORDEM_APAGAR:  # filhas primeiro
            cursor.execute(sql.SQL("DELETE FROM {}").format(sql.Identifier(nome)))
        for nome in ORDEM_INSERCAO:  # pais primeiro
            comando = sql.SQL("COPY {} ({}) FROM STDIN").format(
                sql.Identifier(nome), sql.SQL(", ").join(sql.Identifier(coluna) for coluna in COLUNAS[nome])
            )
            with cursor.copy(comando) as copia:
                for linha in dados[nome]:
                    copia.write_row(linha)
        cursor.execute(
            "UPDATE carga_log SET status = 'concluida', concluida_em = now(), data_referencia_score = %s,"
            " snapshot_estoque_global = %s, contagens = %s WHERE carga_id = %s AND status = 'em_andamento'",
            (meta["data_referencia_score"], meta["snapshot_estoque_global"], Jsonb(contagens), carga_id),
        )
        if cursor.rowcount != 1:
            # Outra carga pode ter marcado esta como interrompida: desfaz a troca em vez de sobrescrever o log.
            raise ErroDeLog("a carga não está mais 'em_andamento' no log (outra carga a marcou como interrompida)")


def descrever_erro(etapa, erro):
    """Texto SEGURO para o log: nunca inclui valores de linhas.

    O str() de um erro do PostgreSQL traz o campo DETAIL, que repete os valores da linha. Por isso, de um erro
    do PostgreSQL só entram o código, a tabela, a restrição e, nas violações de integridade (classe 23), a
    mensagem principal, que não tem valores. Erros desconhecidos entram só pelo tipo.
    """
    if isinstance(erro, (ErroDeValidacao, ErroDeExtracao, ErroDeLog)):
        texto = f"etapa={etapa}; tipo={type(erro).__name__}; {erro}"
    elif isinstance(erro, psycopg.Error):
        diag = erro.diag
        partes = [f"etapa={etapa}", f"tipo={type(erro).__name__}", f"sqlstate={diag.sqlstate}"]
        if diag.table_name:
            partes.append(f"tabela={diag.table_name}")
        if diag.constraint_name:
            partes.append(f"restricao={diag.constraint_name}")
        if (diag.sqlstate or "").startswith("23") and diag.message_primary:
            partes.append(f"mensagem={diag.message_primary}")
        texto = "; ".join(partes)
    else:
        texto = f"etapa={etapa}; tipo={type(erro).__name__}; mensagem omitida por segurança"
    return texto[:500]


def registrar_falha(conn_controle, carga_id, etapa, erro, contagens=None):
    """Transação C: marca a carga como 'falha' e guarda o erro (em outra conexão, fora da transação B).

    Só mexe numa carga que ainda esteja 'em_andamento': nunca troca uma 'concluida' por 'falha'.
    """
    conn_controle.execute(
        "UPDATE carga_log SET status = 'falha', concluida_em = now(), erro = %s, contagens = %s"
        " WHERE carga_id = %s AND status = 'em_andamento'",
        (descrever_erro(etapa, erro), Jsonb(contagens) if contagens else None, carga_id),
    )

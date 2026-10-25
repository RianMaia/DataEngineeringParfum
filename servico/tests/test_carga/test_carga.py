import re
from decimal import Decimal

import psycopg
import pytest

from carga.esquema import ORDEM_INSERCAO
from carga.executar import FALHA, JA_EM_ANDAMENTO, SUCESSO, executar
from carga.gravacao import descrever_erro, obter_bloqueio

from .dados_falsos import FonteFalsa, contagens, gerar, impressao, log

ISCAS = ("SECRETO", "SECRETA", "987654", "SEGREDO")
LINHAS_PERMITIDAS = [
    r"^carga \d+ iniciada$",
    r"^extraído em [\d.]+s: " + ", ".join(rf"{nome}=\d+" for nome in ORDEM_INSERCAO) + "$",
    r"^conferência: ok$",
    r"^gravado em [\d.]+s$",
    r"^carga \d+ concluída$",
    r"^\d+ carga\(s\) esquecida\(s\) em andamento marcada\(s\) como falha$",
    r"^outra carga está em andamento; esta execução desistiu sem alterar nada$",
    r"^carga \d+ falhou: etapa=\w+; tipo=\w+; .+$",
]


def rodar(conexoes, dados, meta, **opcoes):
    controle, conn_dados = conexoes
    return executar(FonteFalsa(dados, meta), controle, conn_dados, **opcoes)


def sem_iscas(texto):
    return not any(isca in texto for isca in ISCAS)


def test_carga_completa_grava_tudo_e_fecha_o_log(conexoes, capsys):
    dados, meta = gerar()
    assert rodar(conexoes, dados, meta) == SUCESSO
    assert contagens(conexoes[1]) == {nome: len(linhas) for nome, linhas in dados.items()}
    (linha,) = log(conexoes[1])
    _, status, erro, contagens_log, referencia, snapshot, concluida_em = linha
    assert status == "concluida" and erro is None and concluida_em is not None
    assert contagens_log == {nome: len(linhas) for nome, linhas in dados.items()}
    assert (referencia, snapshot) == (meta["data_referencia_score"], meta["snapshot_estoque_global"])
    assert "concluída" in capsys.readouterr().out


def test_tipos_chegam_exatos_ao_postgres(conexoes):
    dados, meta = gerar()
    rodar(conexoes, dados, meta)
    banco = conexoes[1]
    assert banco.execute("SELECT meta_mensal FROM vendedores WHERE vendedor_id = 1").fetchone()[0] == Decimal("1234.50")
    score_enviado = dados["fila_semanal"][0][8]
    assert banco.execute("SELECT score FROM fila_semanal ORDER BY cliente_id LIMIT 1").fetchone()[0] == score_enviado
    ruptura = banco.execute("SELECT ruptura, saldo FROM produtos ORDER BY sku LIMIT 1").fetchone()
    assert ruptura == (dados["produtos"][0][5], dados["produtos"][0][4])
    assert banco.execute("SELECT data_snapshot FROM produtos LIMIT 1").fetchone()[0] == dados["produtos"][0][6]


def test_carga_repetida_e_idempotente(conexoes):
    dados, meta = gerar()
    rodar(conexoes, dados, meta)
    primeira = impressao(conexoes[1])
    rodar(conexoes, dados, meta)
    assert impressao(conexoes[1]) == primeira
    assert [linha[1] for linha in log(conexoes[1])] == ["concluida", "concluida"]


def test_nova_carga_substitui_os_dados_antigos(conexoes):
    antigos, meta = gerar(n_clientes=50, semente=1)
    novos, _ = gerar(n_clientes=40, semente=2)
    rodar(conexoes, antigos, meta)
    assert rodar(conexoes, novos, meta) == SUCESSO
    assert contagens(conexoes[1]) == {nome: len(linhas) for nome, linhas in novos.items()}
    assert (
        conexoes[1]
        .execute("SELECT count(*) FROM clientes WHERE cliente_id = %s", (antigos["clientes"][-1][0],))
        .fetchone()[0]
        == 0
    )


def test_falha_no_meio_desfaz_tudo_e_registra_a_falha(conexoes):
    antigos, meta = gerar(semente=1)
    rodar(conexoes, antigos, meta)
    antes = impressao(conexoes[1])
    novos, _ = gerar(semente=2)
    novos["sugestoes_cliente"][0] = (
        novos["sugestoes_cliente"][0][:2] + (0,) + novos["sugestoes_cliente"][0][3:]
    )  # ordem = 0
    assert rodar(conexoes, novos, meta) == FALHA
    assert impressao(conexoes[1]) == antes  # os dados antigos continuam EXATAMENTE iguais
    ultima = log(conexoes[1])[-1]
    assert ultima[1] == "falha" and ultima[6] is not None
    assert "sugestoes_ordem_positiva" in ultima[2] and "sqlstate=23514" in ultima[2] and "etapa=gravacao" in ultima[2]
    assert ultima[3] == {nome: len(linhas) for nome, linhas in novos.items()}  # contagens extraídas, sem valores
    assert sem_iscas(ultima[2])


def test_o_str_do_erro_do_postgres_traz_valores_mas_o_log_nao(banco, servidor):
    """Prova de que a precaução é necessária: o texto bruto do erro vaza a linha inteira."""
    with psycopg.connect(dbname=banco, autocommit=True, **servidor) as conn:
        conn.execute("BEGIN")
        conn.execute("INSERT INTO clientes VALUES (987654000)")
        conn.execute("INSERT INTO vendedores VALUES (1, 'NOME', NULL, NULL, NULL, NULL, NULL, true)")
        with pytest.raises(psycopg.errors.CheckViolation) as erro:
            conn.execute(
                "INSERT INTO fila_semanal VALUES"
                " (987654000, 1, 'NOME', 1, 1, 'RAZAO_SECRETA_X', 'c', 'u', 2.0, 'f', 1.0, 'm', 's')"
            )
        conn.execute("ROLLBACK")
    assert "RAZAO_SECRETA_X" in str(erro.value)  # o texto bruto VAZA o valor da linha
    seguro = descrever_erro("gravacao", erro.value)
    assert "RAZAO_SECRETA_X" not in seguro and "fila_score_entre_0_e_1" in seguro and "sqlstate=23514" in seguro


def test_erro_de_dado_invalido_omite_a_mensagem_que_traria_o_valor(conexoes):
    dados, meta = gerar()
    linha = list(dados["fila_semanal"][0])
    linha[10] = "SEGREDO_NO_LUGAR_DE_UM_NUMERO"  # ticket_medio é DOUBLE PRECISION
    dados["fila_semanal"][0] = tuple(linha)
    assert rodar(conexoes, dados, meta) == FALHA
    ultima = log(conexoes[1])[-1]
    assert ultima[1] == "falha" and "tipo=" in ultima[2] and "sqlstate=22" in ultima[2]
    assert sem_iscas(ultima[2])
    assert contagens(conexoes[1]) == {nome: 0 for nome in ORDEM_INSERCAO}  # primeira carga falhou: nada ficou


def test_segunda_carga_ao_mesmo_tempo_desiste_sem_alterar_nada(conexoes, banco, servidor, capsys):
    dados, meta = gerar()
    rodar(conexoes, dados, meta)
    antes, logs_antes = impressao(conexoes[1]), len(log(conexoes[1]))
    with psycopg.connect(dbname=banco, autocommit=True, **servidor) as outra:
        assert obter_bloqueio(outra) is True  # outra carga está "rodando"
        assert rodar(conexoes, dados, meta) == JA_EM_ANDAMENTO
    assert impressao(conexoes[1]) == antes and len(log(conexoes[1])) == logs_antes
    assert "desistiu sem alterar nada" in capsys.readouterr().out


def test_o_bloqueio_e_liberado_no_fim_com_sucesso_e_com_falha(conexoes, banco, servidor):
    dados, meta = gerar()
    with psycopg.connect(dbname=banco, autocommit=True, **servidor) as outra:
        assert rodar(conexoes, dados, meta) == SUCESSO
        assert obter_bloqueio(outra) is True
        outra.execute("SELECT pg_advisory_unlock_all()")
        dados["clientes"] = []
        assert rodar(conexoes, dados, meta) == FALHA
        assert obter_bloqueio(outra) is True


def test_cargas_esquecidas_em_andamento_viram_falha(conexoes, capsys):
    controle = conexoes[0]
    controle.execute("INSERT INTO carga_log DEFAULT VALUES")
    controle.execute("INSERT INTO carga_log DEFAULT VALUES")
    dados, meta = gerar()
    assert rodar(conexoes, dados, meta) == SUCESSO
    estados = [(linha[1], linha[2]) for linha in log(conexoes[1])]
    assert [estado for estado, _ in estados] == ["falha", "falha", "concluida"]
    assert all(erro.startswith("interrompida") for estado, erro in estados if estado == "falha")
    assert "2 carga(s) esquecida(s)" in capsys.readouterr().out


def test_extracao_vazia_nao_apaga_nada(conexoes):
    antigos, meta = gerar()
    rodar(conexoes, antigos, meta)
    antes = impressao(conexoes[1])
    vazios = dict(antigos)
    vazios["clientes"] = []
    assert rodar(conexoes, vazios, meta) == FALHA
    assert impressao(conexoes[1]) == antes
    ultima = log(conexoes[1])[-1]
    assert ultima[1] == "falha"
    assert "clientes: extração vazia (0 linhas)" in ultima[2]
    assert "etapa=conferencia" in ultima[2]


def test_carga_muito_menor_que_a_anterior_e_recusada_antes_de_apagar(conexoes):
    grandes, meta = gerar(n_clientes=100, n_fila=20, semente=1)
    rodar(conexoes, grandes, meta)
    antes = impressao(conexoes[1])
    pequenos, _ = gerar(n_clientes=30, n_fila=10, semente=2)
    assert rodar(conexoes, pequenos, meta) == FALHA
    assert impressao(conexoes[1]) == antes
    assert "clientes: 30 linhas, menos de 50% das 100" in log(conexoes[1])[-1][2]


def test_dado_inconsistente_e_recusado_na_conferencia_sem_tocar_no_banco(conexoes):
    antigos, meta = gerar()
    rodar(conexoes, antigos, meta)
    antes = impressao(conexoes[1])
    ruins, _ = gerar(semente=3)
    ruins["clientes"] = ruins["clientes"] + [ruins["clientes"][0]]
    assert rodar(conexoes, ruins, meta) == FALHA
    assert impressao(conexoes[1]) == antes
    assert "clientes: 1 linhas repetem a chave (cliente_id)" in log(conexoes[1])[-1][2]


def test_a_saida_impressa_so_tem_formatos_permitidos_e_nenhum_valor(conexoes, capsys):
    dados, meta = gerar()
    rodar(conexoes, dados, meta)
    ruins, _ = gerar(semente=4)
    ruins["sugestoes_cliente"][0] = ruins["sugestoes_cliente"][0][:2] + (0,) + ruins["sugestoes_cliente"][0][3:]
    rodar(conexoes, ruins, meta)
    saida = capsys.readouterr().out
    assert sem_iscas(saida)
    estranhas = [linha for linha in saida.splitlines() if not any(re.match(p, linha) for p in LINHAS_PERMITIDAS)]
    assert not estranhas, estranhas


def test_erro_desconhecido_entra_so_pelo_tipo(conexoes):
    class FonteQueExplode(FonteFalsa):
        def ler(self, nome):
            raise KeyError("VALOR_SECRETO_NA_MENSAGEM")

    controle, conn_dados = conexoes
    assert executar(FonteQueExplode({}, {}), controle, conn_dados) == FALHA
    ultima = log(conn_dados)[-1]
    assert "tipo=KeyError" in ultima[2] and "mensagem omitida" in ultima[2] and sem_iscas(ultima[2])

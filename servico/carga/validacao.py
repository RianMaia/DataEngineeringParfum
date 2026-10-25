"""Conferências feitas na memória, ANTES de tocar no banco. As mensagens só têm nomes e contagens, nunca valores."""

from carga.esquema import COLUNAS, ORDEM_INSERCAO, REFERENCIAS, UNICIDADES


class ErroDeValidacao(Exception):
    """Os dados extraídos não passaram nas conferências. A mensagem só traz nomes de tabelas e contagens."""


def _posicoes(tabela, colunas):
    return [COLUNAS[tabela].index(coluna) for coluna in colunas]


def _chaves(linhas, posicoes):
    return [tuple(linha[i] for i in posicoes) for linha in linhas]


def validar(dados, contagens_anteriores, minimo_relativo=0.5):
    """Devolve a lista de problemas (vazia se está tudo certo)."""
    problemas = []
    for nome in ORDEM_INSERCAO:
        total = len(dados[nome])
        anterior = contagens_anteriores.get(nome, 0)
        if total == 0:
            problemas.append(f"{nome}: extração vazia (0 linhas)")
        elif anterior > 0 and total < anterior * minimo_relativo:
            problemas.append(f"{nome}: {total} linhas, menos de {minimo_relativo:.0%} das {anterior} da carga anterior")
    for nome, conjuntos in UNICIDADES.items():
        for colunas in conjuntos:
            chaves = _chaves(dados[nome], _posicoes(nome, colunas))
            repetidas = len(chaves) - len(set(chaves))
            if repetidas:
                problemas.append(f"{nome}: {repetidas} linhas repetem a chave ({', '.join(colunas)})")
    for filha, colunas_filha, pai, colunas_pai in REFERENCIAS:
        existentes = set(_chaves(dados[pai], _posicoes(pai, colunas_pai)))
        sem_pai = sum(1 for chave in _chaves(dados[filha], _posicoes(filha, colunas_filha)) if chave not in existentes)
        if sem_pai:
            problemas.append(f"{filha}: {sem_pai} linhas sem correspondente em {pai} ({', '.join(colunas_filha)})")
    return problemas

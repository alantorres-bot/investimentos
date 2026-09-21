"""Evolução do patrimônio: o que já aconteceu e a projeção para a frente.

O patrimônio começa em zero e cresce conforme o dinheiro entra e rende:

    patrimônio(mês) = Σ aportes − Σ resgates − Σ impostos pagos
                      + Σ rendimentos, tudo até aquele mês

Assim a linha acompanha os aportes reais: em janeiro o patrimônio é o que havia
sido aplicado até janeiro, não o capital de hoje.

A projeção aplica, mês a mês, a taxa do **último mês fechado** — o rendimento
daquele mês dividido pelo patrimônio no início dele — capitalizando sobre o
saldo anterior e somando o aporte mensal previsto, se houver:

    previsto(mês + 1) = (previsto(mês) + aporte) × (1 + taxa)

O mês em curso nunca entra nessa conta: como ainda não terminou, o rendimento
lançado até aqui é parcial. É uma projeção de ritmo atual, não uma promessa:
taxa de um mês só, mantida constante por doze meses.
"""

from __future__ import annotations

from dataclasses import dataclass

MESES_PROJECAO = 12


@dataclass
class Ponto:
    competencia: str      # AAAA-MM
    valor: float          # patrimônio no fim do mês
    aportado: float = 0.0  # capital líquido aplicado até o mês
    rendimento: float = 0.0  # rendimento do próprio mês
    previsto: bool = False


def _mes_anterior(competencia: str) -> str:
    ano, mes = int(competencia[:4]), int(competencia[5:])
    mes -= 1
    if mes == 0:
        mes, ano = 12, ano - 1
    return f"{ano:04d}-{mes:02d}"


def _mes_seguinte(competencia: str) -> str:
    ano, mes = int(competencia[:4]), int(competencia[5:])
    mes += 1
    if mes > 12:
        mes, ano = 1, ano + 1
    return f"{ano:04d}-{mes:02d}"


def _intervalo(primeiro: str, ultimo: str) -> list[str]:
    meses, atual = [], primeiro
    while atual <= ultimo:
        meses.append(atual)
        atual = _mes_seguinte(atual)
    return meses


def serie_realizada(
    movimentacoes: dict[str, float], rendimentos: dict[str, float]
) -> list[Ponto]:
    """Patrimônio mês a mês, partindo de zero antes do primeiro aporte.

    `movimentacoes` traz o efeito líquido de cada mês (aportes positivos,
    resgates e impostos negativos); `rendimentos`, o retorno de cada mês.
    """
    if not movimentacoes and not rendimentos:
        return []

    meses_com_dados = sorted(set(movimentacoes) | set(rendimentos))
    meses = _intervalo(meses_com_dados[0], meses_com_dados[-1])

    pontos = [Ponto(_mes_anterior(meses[0]), 0.0)]
    aportado = 0.0
    acumulado = 0.0
    for mes in meses:
        aportado += float(movimentacoes.get(mes, 0.0))
        rendimento = float(rendimentos.get(mes, 0.0))
        acumulado += rendimento
        pontos.append(
            Ponto(
                competencia=mes,
                valor=round(aportado + acumulado, 2),
                aportado=round(aportado, 2),
                rendimento=round(rendimento, 2),
            )
        )
    return pontos


def taxa_do_mes(pontos: list[Ponto], competencia: str) -> float:
    """Retorno de um mês sobre o patrimônio que havia no começo dele.

    Usa só o rendimento — aportes e resgates do mês não contam como retorno.
    """
    for i in range(1, len(pontos)):
        if pontos[i].competencia == competencia:
            anterior = pontos[i - 1]
            if anterior.valor <= 0:
                return 0.0
            return pontos[i].rendimento / anterior.valor * 100
    return 0.0


def taxa_ultimo_mes_fechado(
    pontos: list[Ponto], mes_corrente: str
) -> tuple[float, str]:
    """Taxa de retorno do último mês já encerrado.

    O mês corrente fica de fora: ele ainda não terminou, então o rendimento
    lançado até aqui é parcial e puxaria a projeção para baixo. Meses fechados
    sem nenhum rendimento registrado também são pulados — seriam falta de
    lançamento, não retorno zero.

    Devolve a taxa em % e a competência usada.
    """
    for i in range(len(pontos) - 1, 0, -1):
        ponto = pontos[i]
        if ponto.competencia >= mes_corrente:
            continue
        anterior = pontos[i - 1]
        if anterior.valor <= 0 or ponto.rendimento <= 0:
            continue
        return ponto.rendimento / anterior.valor * 100, ponto.competencia
    return 0.0, ""


def projetar(
    ponto_final: Ponto,
    taxa_pct: float,
    meses: int = MESES_PROJECAO,
    aporte_mensal: float = 0.0,
) -> list[Ponto]:
    """Projeta o patrimônio à frente, capitalizando a taxa informada."""
    pontos, valor, competencia = [], ponto_final.valor, ponto_final.competencia
    aportado = ponto_final.aportado
    for _ in range(meses):
        competencia = _mes_seguinte(competencia)
        aportado += float(aporte_mensal)
        rendimento = (valor + float(aporte_mensal)) * taxa_pct / 100
        valor = valor + float(aporte_mensal) + rendimento
        pontos.append(
            Ponto(
                competencia=competencia,
                valor=round(valor, 2),
                aportado=round(aportado, 2),
                rendimento=round(rendimento, 2),
                previsto=True,
            )
        )
    return pontos

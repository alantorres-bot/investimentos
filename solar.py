"""Cálculo do retorno da energia solar (compensação de créditos, GD II).

A distribuidora não paga nada em dinheiro: o retorno do investimento é a
**economia** na conta de luz. Ela é a diferença entre o que a conta custaria sem
o sistema e o que foi efetivamente pago no mês:

    custo sem solar = consumo (kWh) × tarifa cheia com tributos
                      + contribuição de iluminação pública
                      + adicional de bandeira

    custo com solar = total da fatura − multa/juros de atraso

    economia do mês = custo sem solar − custo com solar

A multa e os juros de atraso saem do cálculo porque são custo de atraso no
pagamento, não do sistema de energia. O saldo de créditos em kWh é guardado à
parte: é economia futura já garantida, que ainda não entrou na conta.

Os campos vêm todos da DANF3E (conta da Energisa) — veja `CAMPOS`.
"""

from __future__ import annotations

from dataclasses import dataclass

CATEGORIA = "Energia solar"

# Onde achar cada dado na fatura (usado como ajuda na tela)
CAMPOS = {
    "dias": "Cabeçalho da fatura: número de dias entre a leitura anterior e a atual.",
    "consumo_kwh": "Item “Consumo em kWh” — a quantidade (ex.: 416,00).",
    "tarifa_cheia": "Item “Consumo em kWh” — o preço unitário com tributos "
                    "(ex.: 1,194080).",
    "tarifa_fio_b": "Item “Ajuste GDII - TRF Reduzida (Lei 14.300/22)” — o preço "
                    "unitário (ex.: 0,189080). Opcional, só para acompanhamento.",
    "ilum_publica": "Item “Contrib de Ilum Pub” — o valor em R$.",
    "bandeira": "Item “Adic. B. Amarela/Vermelha” — o valor em R$ (0 se não houver).",
    "mora": "Multa e juros por atraso, se a fatura foi paga depois do vencimento.",
    "total_pago": "Valor total da fatura (o que você pagou).",
    "saldo_creditos": "Rodapé: “Saldo Acumulado” em kWh.",
}


@dataclass
class ResultadoMes:
    custo_sem_solar: float
    custo_com_solar: float
    economia: float

    @property
    def percentual_economia(self) -> float:
        """Quanto da conta o sistema eliminou, em %."""
        if not self.custo_sem_solar:
            return 0.0
        return self.economia / self.custo_sem_solar * 100


def calcular_mes(
    consumo_kwh: float,
    tarifa_cheia: float,
    total_pago: float,
    ilum_publica: float = 0.0,
    bandeira: float = 0.0,
    mora: float = 0.0,
) -> ResultadoMes:
    """Economia do mês a partir dos dados de uma fatura."""
    custo_sem = float(consumo_kwh) * float(tarifa_cheia) + float(ilum_publica) + float(bandeira)
    custo_com = float(total_pago) - float(mora)
    return ResultadoMes(
        custo_sem_solar=round(custo_sem, 2),
        custo_com_solar=round(custo_com, 2),
        economia=round(custo_sem - custo_com, 2),
    )


@dataclass
class Retorno:
    meses: int
    economia_acumulada: float
    economia_media: float
    retorno_acumulado_pct: float
    retorno_medio_mensal_pct: float
    payback_meses: float | None
    falta_recuperar: float
    saldo_creditos: float | None


def resumo_retorno(faturas, investimento: float) -> Retorno:
    """Indicadores de retorno a partir das faturas já registradas."""
    economias = [
        calcular_mes(
            f["consumo_kwh"], f["tarifa_cheia"], f["total_pago"],
            f["ilum_publica"], f["bandeira"], f["mora"],
        ).economia
        for f in faturas
    ]
    meses = len(economias)
    acumulada = round(sum(economias), 2)
    media = round(acumulada / meses, 2) if meses else 0.0
    investimento = float(investimento or 0)

    saldo = None
    for f in faturas:
        if f["saldo_creditos"] is not None:
            saldo = float(f["saldo_creditos"])

    return Retorno(
        meses=meses,
        economia_acumulada=acumulada,
        economia_media=media,
        retorno_acumulado_pct=(acumulada / investimento * 100) if investimento else 0.0,
        retorno_medio_mensal_pct=(media / investimento * 100) if investimento else 0.0,
        payback_meses=(investimento / media) if media else None,
        falta_recuperar=round(max(investimento - acumulada, 0), 2),
        saldo_creditos=saldo,
    )

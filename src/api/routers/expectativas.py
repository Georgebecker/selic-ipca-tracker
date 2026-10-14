"""Endpoints das expectativas de mercado (boletim Focus, via Olinda)."""

from __future__ import annotations

from fastapi import APIRouter

from src.api.schemas import ExpectativaOut, ExpectativasOut
from src.db.repository import abrir_sessao, ultimos_valores
from src.etl.bcb_olinda import expectativas_do_focus

router = APIRouter(tags=["expectativas"])

# Série oficial do IPCA acumulado em 12 meses: é contra ela que o mercado se compara.
CODIGO_IPCA_12_MESES = 13522


def _montar(item: dict | None) -> ExpectativaOut | None:
    if not item:
        return None
    return ExpectativaOut(
        indicador=item.get("indicador") or "",
        referencia=item.get("referencia"),
        data=item.get("data"),
        mediana=item.get("mediana"),
        media=item.get("media"),
        minimo=item.get("minimo"),
        maximo=item.get("maximo"),
        respondentes=item.get("respondentes"),
    )


@router.get(
    "/expectativas",
    response_model=ExpectativasOut,
    summary="O que o mercado espera (Focus) e quanto está longe do realizado",
)
def get_expectativas() -> ExpectativasOut:
    focus = expectativas_do_focus()

    with abrir_sessao() as sessao:
        oficiais = ultimos_valores(sessao, CODIGO_IPCA_12_MESES, 1)

    realizado = oficiais[-1].valor if oficiais else None
    realizado_data = oficiais[-1].data if oficiais else None

    esperado = _montar(focus.get("ipca_12_meses"))
    diferenca = None
    if esperado is not None and esperado.mediana is not None and realizado is not None:
        diferenca = round(esperado.mediana - realizado, 4)

    return ExpectativasOut(
        fonte="BCB/Olinda - boletim Focus",
        disponivel=bool(focus.get("disponivel")),
        motivo=focus.get("motivo"),
        data_referencia=esperado.data if esperado else None,
        ipca_12_meses=esperado,
        igpm_12_meses=_montar(focus.get("igpm_12_meses")),
        ipca_anual=_montar(focus.get("ipca_anual")),
        selic=_montar(focus.get("selic")),
        realizado_ipca_12m=realizado,
        realizado_data=realizado_data,
        diferenca_pp=diferenca,
    )

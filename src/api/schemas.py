"""Contratos de entrada e saída da API (Pydantic v2)."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SerieOut(BaseModel):
    """Metadados de uma série disponível."""

    model_config = ConfigDict(from_attributes=True)

    codigo_sgs: int
    nome: str
    descricao: str | None = None
    unidade: str | None = None
    periodicidade: str | None = None
    fonte: str
    total_valores: int = 0


class PontoOut(BaseModel):
    """Um ponto da série."""

    data: date
    valor: float


class SerieDadosOut(BaseModel):
    """Série com seus valores."""

    codigo_sgs: int
    nome: str
    unidade: str | None = None
    total: int
    valores: list[PontoOut]


class IndicadorOut(BaseModel):
    """KPIs de um indicador: valor atual, variação mensal e acumulado 12 meses."""

    nome: str
    serie: int
    atual: float | None = None
    data: date | None = None
    variacao_mensal_pp: float | None = None
    acumulado_12m: float | None = None
    acumulado_12m_oficial: float | None = None


class ResumoOut(BaseModel):
    """Resumo dos quatro indicadores principais."""

    selic: IndicadorOut
    ipca: IndicadorOut
    igpm: IndicadorOut
    inpc: IndicadorOut
    ultima_atualizacao: datetime | None = None


class SerieAlinhadaOut(BaseModel):
    """Série alinhada no eixo de meses do comparativo."""

    codigo_sgs: int
    nome: str
    unidade: str | None = None
    valores: list[float | None]


class ComparacaoOut(BaseModel):
    """Comparativo entre índices, alinhado mês a mês."""

    de: date | None = None
    ate: date | None = None
    eixo: list[str]
    series: list[SerieAlinhadaOut]


class ExpectativaOut(BaseModel):
    """Uma expectativa do boletim Focus (mediana, faixa e nº de respondentes)."""

    indicador: str
    referencia: str | None = None
    data: date | None = None
    mediana: float | None = None
    media: float | None = None
    minimo: float | None = None
    maximo: float | None = None
    respondentes: int | None = None


class ExpectativasOut(BaseModel):
    """Expectativas do mercado comparadas com o realizado.

    `disponivel=False` (com `motivo`) quando o Olinda não respondeu: a interface mostra o
    aviso e o resto do painel continua funcionando.
    """

    fonte: str
    disponivel: bool = True
    motivo: str | None = None
    data_referencia: date | None = None
    ipca_12_meses: ExpectativaOut | None = None
    igpm_12_meses: ExpectativaOut | None = None
    ipca_anual: ExpectativaOut | None = None
    selic: ExpectativaOut | None = None
    realizado_ipca_12m: float | None = None
    realizado_data: date | None = None
    diferenca_pp: float | None = None


class CorrecaoRequest(BaseModel):
    """Pedido de correção monetária."""

    valor: float = Field(gt=0, description="Valor original")
    data_inicial: date
    data_final: date
    indice: str = Field(default="IPCA", description="IPCA, IGP-M, INPC ou Selic")

    @model_validator(mode="after")
    def validar_periodo(self) -> "CorrecaoRequest":
        if self.data_final < self.data_inicial:
            raise ValueError("data_final precisa ser igual ou posterior a data_inicial")
        return self


class CorrecaoResponse(BaseModel):
    """Resultado da correção monetária."""

    valor_original: float
    valor_corrigido: float
    fator_acumulado: float
    variacao_percentual: float
    indice: str
    periodo: str
    meses: int


class ProgressoColetaOut(BaseModel):
    """Progresso da coleta em segundo plano (alimenta o botão "Atualizar")."""

    em_andamento: bool
    total_series: int = 0
    concluidas: int = 0
    iniciado_em: datetime | None = None
    finalizado_em: datetime | None = None
    status: str | None = None
    mensagem: str | None = None


class StatusOut(BaseModel):
    """Estado do serviço: última coleta, séries monitoradas e coleta em andamento."""

    ultima_atualizacao: datetime | None = None
    proxima_atualizacao: datetime | None = None
    segundos_restantes: int
    intervalo_horas: int
    series_monitoradas: int
    coleta_automatica: bool = False
    coleta: ProgressoColetaOut

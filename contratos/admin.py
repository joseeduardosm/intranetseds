"""
Configuração do Django Admin para o app `contratos`.

Define como a entidade `Contrato` é exibida/filtrada no painel administrativo,
facilitando operação interna sem necessidade de telas customizadas.
"""

from django.contrib import admin

from .models import Contrato


@admin.register(Contrato)
class ContratoAdmin(admin.ModelAdmin):
    """
    Customização da listagem administrativa de contratos.

    Papel:
    - expor colunas-chave de acompanhamento;
    - habilitar filtros e busca textual para suporte operacional.
    """

    list_display = (
        "nro_sei",
        "nro_contrato",
        "data_inicial",
        "vigencia_meses",
        "data_fim",
        "prorrogacao_maxima_meses",
        "valor_total",
        "valor_mensal",
    )
    list_filter = ("vigencia_meses", "prorrogacao_maxima_meses")
    search_fields = ("nro_sei", "nro_contrato", "objeto")

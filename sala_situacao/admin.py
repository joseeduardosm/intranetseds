"""
Configuração de Django Admin do app `sala_situacao`.

Este módulo define como os modelos estratégicos/táticos aparecem no painel
administrativo, facilitando operação, auditoria manual e suporte funcional.
"""

from django.contrib import admin

from .models import (
    Entrega,
    IndicadorCicloHistorico,
    IndicadorCicloMonitoramento,
    IndicadorCicloValor,
    IndicadorEstrategico,
    IndicadorTatico,
    IndicadorVariavel,
    IndicadorVariavelCicloMonitoramento,
    NotaItem,
    Processo,
    SalaSituacaoPainel,
)


@admin.register(SalaSituacaoPainel)
class SalaSituacaoPainelAdmin(admin.ModelAdmin):
    """Admin do objeto raiz de configuração do painel de situação."""

    list_display = ("id", "titulo", "atualizado_em")
    search_fields = ("titulo",)


@admin.register(IndicadorEstrategico)
class IndicadorEstrategicoAdmin(admin.ModelAdmin):
    """Admin de indicadores estratégicos usados no topo da cadeia de metas."""

    list_display = ("id", "nome", "tipo_indicador", "meta_valor", "atualizado_em")
    list_filter = ("tipo_indicador",)
    search_fields = ("nome",)


@admin.register(IndicadorTatico)
class IndicadorTaticoAdmin(admin.ModelAdmin):
    """Admin de indicadores táticos vinculados a indicadores estratégicos."""

    list_display = ("id", "nome", "tipo_indicador", "meta_valor", "indicadores_estrategicos_display", "atualizado_em")
    list_filter = ("tipo_indicador", "indicadores_estrategicos")
    search_fields = ("nome",)

    def indicadores_estrategicos_display(self, obj):
        """
        Concatena nomes dos indicadores estratégicos relacionados ao item.

        Retorno:
        - `str`: lista separada por vírgula para renderização na coluna do admin.
        """

        return ", ".join(obj.indicadores_estrategicos.values_list("nome", flat=True))

    indicadores_estrategicos_display.short_description = "Indicadores"


@admin.register(Processo)
class ProcessoAdmin(admin.ModelAdmin):
    """Admin de processos operacionais associados a indicadores estratégicos."""

    list_display = ("id", "nome", "indicadores_estrategicos_display", "atualizado_em")
    list_filter = ("indicadores_estrategicos",)
    search_fields = ("nome",)

    def indicadores_estrategicos_display(self, obj):
        """
        Concatena nomes dos indicadores estratégicos vinculados ao processo.

        Retorno:
        - `str`: lista separada por vírgula para coluna de relacionamento.
        """

        return ", ".join(obj.indicadores_estrategicos.values_list("nome", flat=True))

    indicadores_estrategicos_display.short_description = "Indicadores"


@admin.register(Entrega)
class EntregaAdmin(admin.ModelAdmin):
    """Admin de entregas (itens executáveis) vinculadas a processos e monitoramento."""

    list_display = ("id", "nome", "processos_display", "atualizado_em")
    list_filter = ("processos",)
    search_fields = ("nome",)

    def processos_display(self, obj):
        """
        Concatena nomes dos processos relacionados à entrega.

        Retorno:
        - `str`: lista separada por vírgula para melhorar legibilidade no admin.
        """

        return ", ".join(obj.processos.values_list("nome", flat=True))

    processos_display.short_description = "Processos"


@admin.register(NotaItem)
class NotaItemAdmin(admin.ModelAdmin):
    """Admin de notas/comentários anexados genericamente a qualquer item do domínio."""

    list_display = ("id", "content_type", "object_id", "criado_por", "criado_em")
    list_filter = ("content_type", "criado_em")
    search_fields = ("texto",)


@admin.register(IndicadorVariavel)
class IndicadorVariavelAdmin(admin.ModelAdmin):
    """Admin de variáveis de indicadores matemáticos e seus metadados numéricos."""

    list_display = ("id", "nome", "tipo_numerico", "unidade_medida", "content_type", "object_id")
    list_filter = ("tipo_numerico", "content_type")
    search_fields = ("nome", "descricao")


@admin.register(IndicadorCicloMonitoramento)
class IndicadorCicloMonitoramentoAdmin(admin.ModelAdmin):
    """Admin dos ciclos agregados de monitoramento por indicador."""

    list_display = ("id", "content_type", "object_id", "numero", "periodo_inicio", "periodo_fim", "valor_resultado")
    list_filter = ("content_type", "status")
    search_fields = ("object_id",)


@admin.register(IndicadorVariavelCicloMonitoramento)
class IndicadorVariavelCicloMonitoramentoAdmin(admin.ModelAdmin):
    """Admin dos ciclos individuais por variável monitorada."""

    list_display = ("id", "variavel", "numero", "periodo_inicio", "periodo_fim", "status")
    list_filter = ("status", "variavel")
    search_fields = ("variavel__nome",)


@admin.register(IndicadorCicloValor)
class IndicadorCicloValorAdmin(admin.ModelAdmin):
    """Admin dos valores lançados por variável dentro de cada ciclo."""

    list_display = ("id", "ciclo", "variavel", "valor", "atualizado_por", "atualizado_em")
    list_filter = ("variavel",)
    search_fields = ("variavel__nome",)


@admin.register(IndicadorCicloHistorico)
class IndicadorCicloHistoricoAdmin(admin.ModelAdmin):
    """Admin do histórico de alterações de valores monitorados."""

    list_display = ("id", "ciclo", "variavel", "valor", "registrado_por", "registrado_em")
    list_filter = ("variavel", "registrado_em")
    search_fields = ("variavel__nome",)

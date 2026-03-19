"""
Configuração do Django Admin para o app `lousa_digital`.

Permite operação administrativa dos principais registros da lousa:
processos, encaminhamentos e eventos da timeline.
"""

from django.contrib import admin

from .models import Encaminhamento, EventoTimeline, Processo


@admin.register(Processo)
class ProcessoAdmin(admin.ModelAdmin):
    """Admin de processos com filtros por status e grupo de inserção."""

    list_display = ("numero_sei", "assunto", "caixa_origem", "status", "arquivo_morto", "criado_por", "grupo_insercao", "atualizado_em")
    list_filter = ("status", "arquivo_morto", "caixa_origem", "grupo_insercao")
    search_fields = ("numero_sei", "assunto", "caixa_origem")


@admin.register(Encaminhamento)
class EncaminhamentoAdmin(admin.ModelAdmin):
    """Admin de encaminhamentos para auditoria de prazo e conclusão."""

    list_display = (
        "processo",
        "destino",
        "prazo_data",
        "email_notificacao",
        "notificado_72h_em",
        "data_inicio",
        "data_conclusao",
    )
    list_filter = ("destino", "data_conclusao", "notificado_72h_em")
    search_fields = ("processo__numero_sei", "destino", "email_notificacao")


@admin.register(EventoTimeline)
class EventoTimelineAdmin(admin.ModelAdmin):
    """Admin de eventos cronológicos associados aos processos."""

    list_display = ("processo", "tipo", "usuario", "criado_em")
    list_filter = ("tipo",)
    search_fields = ("processo__numero_sei", "descricao")

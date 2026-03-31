from django.contrib import admin

from .models import (
    AnexoHistoricoEtapa,
    EntregaSistema,
    EtapaSistema,
    HistoricoEtapaSistema,
    InteressadoSistema,
    InteressadoSistemaManual,
    Sistema,
)


@admin.register(Sistema)
class SistemaAdmin(admin.ModelAdmin):
    list_display = ("nome", "criado_por", "criado_em", "atualizado_em")
    search_fields = ("nome", "descricao")


@admin.register(EntregaSistema)
class EntregaSistemaAdmin(admin.ModelAdmin):
    list_display = ("titulo", "sistema", "ordem", "criado_em")
    list_filter = ("sistema",)
    search_fields = ("titulo", "sistema__nome")


@admin.register(EtapaSistema)
class EtapaSistemaAdmin(admin.ModelAdmin):
    list_display = ("entrega", "tipo_etapa", "status", "data_etapa", "tempo_desde_etapa_anterior_em_dias")
    list_filter = ("tipo_etapa", "status")
    search_fields = ("entrega__sistema__nome", "entrega__titulo", "ticket_externo")


@admin.register(HistoricoEtapaSistema)
class HistoricoEtapaSistemaAdmin(admin.ModelAdmin):
    list_display = ("etapa", "tipo_evento", "criado_por", "criado_em")
    list_filter = ("tipo_evento",)
    search_fields = ("etapa__entrega__sistema__nome", "descricao", "justificativa")


@admin.register(AnexoHistoricoEtapa)
class AnexoHistoricoEtapaAdmin(admin.ModelAdmin):
    list_display = ("historico", "nome_original", "criado_em")
    search_fields = ("nome_original", "historico__etapa__entrega__sistema__nome")


@admin.register(InteressadoSistema)
class InteressadoSistemaAdmin(admin.ModelAdmin):
    list_display = ("sistema", "usuario", "tipo_interessado", "email_snapshot", "criado_em")
    list_filter = ("tipo_interessado",)
    search_fields = ("sistema__nome", "nome_snapshot", "email_snapshot", "usuario__username")


@admin.register(InteressadoSistemaManual)
class InteressadoSistemaManualAdmin(admin.ModelAdmin):
    list_display = ("sistema", "nome", "tipo_interessado", "email", "criado_em")
    list_filter = ("tipo_interessado",)
    search_fields = ("sistema__nome", "nome", "email")

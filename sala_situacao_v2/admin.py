from django.contrib import admin

from .models import Entrega, Indicador, Marcador, MarcadorVinculoAutomaticoGrupoItem, Processo


@admin.register(Indicador)
class IndicadorAdmin(admin.ModelAdmin):
    list_display = ("id", "nome", "tipo_indicador", "meta_valor", "atualizado_em")
    search_fields = ("nome", "descricao", "formula_expressao")
    filter_horizontal = ("grupos_responsaveis",)


@admin.register(Processo)
class ProcessoAdmin(admin.ModelAdmin):
    list_display = ("id", "nome", "atualizado_em")
    search_fields = ("nome", "descricao")
    filter_horizontal = ("indicadores", "grupos_responsaveis")


@admin.register(Entrega)
class EntregaAdmin(admin.ModelAdmin):
    list_display = ("id", "nome", "data_entrega_estipulada", "monitorado_em", "atualizado_em")
    search_fields = ("nome", "descricao")
    filter_horizontal = ("processos", "grupos_responsaveis")


@admin.register(Marcador)
class MarcadorAdmin(admin.ModelAdmin):
    list_display = ("id", "nome", "cor", "ativo", "atualizado_em")
    search_fields = ("nome", "nome_normalizado")
    list_filter = ("ativo",)


@admin.register(MarcadorVinculoAutomaticoGrupoItem)
class MarcadorVinculoAutomaticoGrupoItemAdmin(admin.ModelAdmin):
    list_display = ("id", "content_type", "object_id", "marcador", "grupo", "criado_em")
    search_fields = ("marcador__nome", "grupo__name")
    list_filter = ("content_type", "grupo")

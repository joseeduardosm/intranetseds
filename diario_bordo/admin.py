"""
Configuração do Django Admin para `diario_bordo`.

Define a forma de visualização e busca das entidades principais do app
no painel administrativo padrão do Django.
"""

from django.contrib import admin

from .models import BlocoTrabalho, Incremento, IncrementoCiencia


@admin.register(BlocoTrabalho)
class BlocoTrabalhoAdmin(admin.ModelAdmin):
    """Customização do admin para blocos de trabalho."""

    list_display = ("nome", "status", "criado_em")
    list_filter = ("status", "criado_em")
    search_fields = ("nome", "descricao")
    fields = ("nome", "descricao", "status", "criado_em")


@admin.register(Incremento)
class IncrementoAdmin(admin.ModelAdmin):
    """Customização do admin para incrementos dos blocos."""

    list_display = ("bloco", "criado_em")
    list_filter = ("criado_em",)
    search_fields = ("texto", "bloco__nome")
    fields = ("bloco", "texto", "anexo", "criado_em")


@admin.register(IncrementoCiencia)
class IncrementoCienciaAdmin(admin.ModelAdmin):
    """Customização do admin para registros de ciência dos incrementos."""

    list_display = ("incremento", "usuario", "criado_em")
    list_filter = ("criado_em",)
    search_fields = ("texto", "usuario__username", "usuario__first_name", "incremento__bloco__nome")


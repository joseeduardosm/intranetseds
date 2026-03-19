"""
Configuração do Django Admin para o app `reserva_salas`.

Este módulo define como modelos de sala e reserva são visualizados e filtrados
no painel administrativo do Django, apoiando operação e auditoria manual.
"""

from django.contrib import admin

from .models import Reserva, Sala


@admin.register(Sala)
class SalaAdmin(admin.ModelAdmin):
    """
    Configura listagem administrativa de salas e seus recursos disponíveis.
    """

    list_display = (
        "nome",
        "capacidade",
        "localizacao",
        "cor",
        "televisao",
        "projetor",
        "som",
        "microfone_evento",
        "som_evento",
        "mesa_som_evento",
        "videowall",
        "wifi",
    )
    list_filter = (
        "televisao",
        "projetor",
        "som",
        "microfone_evento",
        "som_evento",
        "mesa_som_evento",
        "videowall",
        "wifi",
    )
    # Busca textual para acelerar identificação de salas por nome/local.
    search_fields = ("nome", "localizacao")


@admin.register(Reserva)
class ReservaAdmin(admin.ModelAdmin):
    """
    Configura listagem administrativa de reservas e dados operacionais.
    """

    list_display = (
        "nome_evento",
        "sala",
        "data",
        "hora_inicio",
        "hora_fim",
        "quantidade_pessoas",
        "responsavel_evento",
        "registrado_por",
    )
    list_filter = ("sala", "data")
    # Permite localizar reservas por evento, responsável ou sala vinculada.
    search_fields = ("nome_evento", "responsavel_evento", "sala__nome")

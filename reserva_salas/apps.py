"""
Configuração da aplicação Django `reserva_salas`.

Este arquivo registra metadados do app no Django App Registry, permitindo que o
framework identifique o pacote, migrações e permissões associadas aos modelos.
"""

from django.apps import AppConfig


class ReservaSalasConfig(AppConfig):
    """
    Classe de configuração do app de reservas de salas.

    Papel na arquitetura:
    - Define o nome técnico do app (`name`) e o tipo padrão de chave primária
      para novos modelos (`default_auto_field`).
    - `verbose_name` é usado em interfaces como o Django Admin.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "reserva_salas"
    verbose_name = "Reserva de Salas"

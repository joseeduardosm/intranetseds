"""
Configuração de inicialização do app `lousa_digital`.

Este módulo integra o app ao ciclo de boot do Django, permitindo:
- registro em `INSTALLED_APPS`;
- descoberta de modelos, comandos de management e templatetags;
- aplicação de convenções de chave primária e metadados do app.
"""

from django.apps import AppConfig


class LousaDigitalConfig(AppConfig):
    """Define metadados de carregamento do app na arquitetura Django."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "lousa_digital"

"""
Configuracao de inicializacao do app Django `administracao`.

Este arquivo registra metadados do app no ciclo de boot do Django
(nome tecnico, nome exibido e tipo de chave primaria padrao).
Ele se integra ao projeto via `INSTALLED_APPS` e permite que models,
views, formularios e templates do modulo sejam descobertos pelo framework.
"""

from django.apps import AppConfig


class AdministracaoConfig(AppConfig):
    """
    Classe de configuracao do app na arquitetura Django.

    Nao contem regra de negocio; serve para registrar o modulo e
    definir convencoes globais de persistencia para os models do app.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "administracao"
    verbose_name = "Administracao"

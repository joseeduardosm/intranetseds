"""
Configuração do app `ramais` dentro da arquitetura Django.

A classe definida neste módulo é utilizada pelo framework para registrar o app
no ciclo de inicialização, permitindo descoberta de modelos, migrações, admin
e templates associados.
"""
from django.apps import AppConfig


class RamaisConfig(AppConfig):
    """
    Classe de configuração do app de ramais.

    Papel arquitetural:
    - Identificar o app para o `INSTALLED_APPS`.
    - Servir como ponto de extensão para inicializações futuras (ex.: signals).
    """
    name = 'ramais'

"""
Configuração do app `prepostos` dentro da arquitetura Django.

Este módulo fornece a classe de configuração usada pelo framework para
registrar o app, localizar seus componentes e habilitar integração com
migrações, admin, templates e roteamento.
"""
from django.apps import AppConfig


class PrepostosConfig(AppConfig):
    """
    Classe de configuração principal do app.

    Papel arquitetural:
    - Identificar o app para o carregamento do Django.
    - Servir de ponto de extensão para inicializações futuras (ex.: sinais).
    """
    name = 'prepostos'

"""
Configuracao de inicializacao do app `auditoria`.

Este arquivo registra o app no ciclo de boot do Django e define
o gancho `ready()` para ativar os signal handlers de auditoria.
Sem essa integracao, eventos de create/update/delete/m2m nao seriam
capturados para persistencia em `AuditLog`.
"""

from django.apps import AppConfig


class AuditoriaConfig(AppConfig):
    """
    Classe de configuracao do app na arquitetura Django.

    Papel:
    - declarar nome tecnico e defaults do app;
    - carregar sinais no momento certo de inicializacao.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "auditoria"

    def ready(self):
        """
        Importa o modulo de sinais para registrar receivers.

        Retorno:
        - Nao retorna valor.

        Regra de arquitetura:
        - O import tardio evita efeitos colaterais prematuros na fase
          de importacao de modulos e garante registro dos receivers.
        """

        from . import signals  # noqa: F401

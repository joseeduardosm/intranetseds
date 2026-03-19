"""
Configuração da aplicação Django `usuarios`.

Este arquivo registra o app no App Registry e conecta hooks de inicialização:
- registro de sinais do módulo (`signals.py`);
- garantia do grupo ADMIN após migrações (`post_migrate`).
"""

from django.apps import AppConfig


class UsuariosConfig(AppConfig):
    """
    Classe de configuração do app de gestão de usuários e grupos.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "usuarios"

    def ready(self):
        """
        Executa inicialização tardia do app após carregamento de modelos.

        Integrações:
        - conecta sinal `post_migrate` para garantir bootstrap do grupo ADMIN;
        - importa `signals` para registrar receivers de usuário/grupo.
        """
        from django.db.models.signals import post_migrate

        from .auth_backends import ensure_setor_nodes_for_all_groups
        from .permissions import ensure_admin_group
        from . import signals  # noqa: F401

        post_migrate.connect(
            lambda **kwargs: (ensure_admin_group(), ensure_setor_nodes_for_all_groups()),
            sender=self,
        )

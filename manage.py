#!/usr/bin/env python
"""Utilitário de linha de comando do Django para tarefas administrativas."""
import os
import sys


def main():
    """Executa tarefas administrativas via manage.py."""
    # Define o módulo de configurações padrão caso não esteja definido.
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'intranet.settings')
    try:
        # Importa o executor de comandos do Django.
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        # Erro comum quando o Django não está instalado/ativado no ambiente.
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    # Repassa os argumentos do terminal para o Django.
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    # Ponto de entrada quando o arquivo é executado diretamente.
    main()

"""
Comando de management do app `auditoria` (desativado).

Este comando é mantido para compatibilidade operacional/documental.
Na política atual do sistema ele não executa normalização para preservar
texto UTF-8 conforme armazenado pelas aplicações.
"""

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    """
    Comando Django para normalização textual (inativo por regra de negócio).

    Fluxo:
    - quando executado, apenas informa que a rotina está desativada.
    """

    help = "Comando desativado para preservar acentos/cedilha e demais caracteres Unicode."

    def handle(self, *args, **options):
        """
        Ponto de entrada do comando.

        Parâmetros:
        - `*args`, `**options`: argumentos padrão do Django management.

        Retorno:
        - não retorna valor útil; imprime aviso em stdout.
        """

        self.stdout.write(
            self.style.WARNING(
                "Comando normalize_texts desativado: textos agora devem manter acentos e caracteres UTF-8."
            )
        )

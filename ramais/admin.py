"""
Configuração do Django Admin para o app `ramais`.

Este módulo registra `PessoaRamal` no painel administrativo e define
customizações para listagem e busca, facilitando operação de cadastro interno.
"""
from django.contrib import admin

from .models import PessoaRamal


@admin.register(PessoaRamal)
class PessoaRamalAdmin(admin.ModelAdmin):
    """
    Customiza a gestão de ramais no Django Admin.

    Papel arquitetural:
    - Expor campos operacionais em listagem.
    - Oferecer busca textual em dados de usuário e perfil.
    """
    # Colunas exibidas na listagem.
    list_display = (
        'usuario',
        'nome_display',
        'cargo',
        'setor',
        'ramal',
        'email_display',
        'superior',
        'atualizado_em',
    )
    # Campos pesquisaveis.
    search_fields = (
        'usuario__first_name',
        'usuario__username',
        'usuario__email',
        'nome',
        'cargo',
        'setor',
        'ramal',
        'email',
        'bio',
    )

    def nome_display(self, obj):
        """
        Retorna nome normalizado para coluna de listagem.

        Parâmetros:
            obj (PessoaRamal): registro exibido na linha do admin.

        Retorno:
            str: nome resolvido via propriedade `nome_display`.
        """
        return obj.nome_display

    def email_display(self, obj):
        """
        Retorna e-mail normalizado para coluna de listagem.

        Parâmetros:
            obj (PessoaRamal): registro exibido na linha do admin.

        Retorno:
            str: e-mail resolvido via propriedade `email_display`.
        """
        return obj.email_display

    nome_display.short_description = 'Nome'
    email_display.short_description = 'Email'

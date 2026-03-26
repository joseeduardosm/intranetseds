"""
Views compartilhadas do projeto `intranet`.

Este módulo concentra endpoints transversais ao projeto, como autenticação,
quando precisamos de comportamento adicional sobre as views padrão do Django.
"""

from django.contrib.auth.views import LoginView
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import ensure_csrf_cookie


@method_decorator(never_cache, name="dispatch")
@method_decorator(ensure_csrf_cookie, name="dispatch")
class IntranetLoginView(LoginView):
    """
    Tela de login com cabeçalhos anti-cache e cookie CSRF sempre renovado.

    Isso reduz falhas em páginas antigas abertas em outra aba ou reaproveitadas
    via botão "voltar", cenário em que o HTML pode carregar um token vencido.
    """


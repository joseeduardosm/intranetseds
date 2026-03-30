"""
Views compartilhadas do projeto `intranet`.

Este módulo concentra endpoints transversais ao projeto, como autenticação,
quando precisamos de comportamento adicional sobre as views padrão do Django.
"""

from django.db.utils import OperationalError, ProgrammingError
from django.contrib.auth.views import LoginView
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.generic import TemplateView

from administracao.models import AtalhoAdministracao, AtalhoServico
from administracao.navigation import get_administracao_home_items_map


@method_decorator(never_cache, name="dispatch")
@method_decorator(ensure_csrf_cookie, name="dispatch")
class IntranetLoginView(LoginView):
    """
    Tela de login com cabeçalhos anti-cache e cookie CSRF sempre renovado.

    Isso reduz falhas em páginas antigas abertas em outra aba ou reaproveitadas
    via botão "voltar", cenário em que o HTML pode carregar um token vencido.
    """


class HomeView(TemplateView):
    """Home da intranet com duas colunas independentes de atalhos."""

    template_name = "home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        home_items_map = get_administracao_home_items_map()
        try:
            configuracoes = AtalhoAdministracao.objects.filter(ativo=True)
        except (OperationalError, ProgrammingError):
            configuracoes = AtalhoAdministracao.objects.none()
        atalhos_administracao = []
        for configuracao in configuracoes:
            item = home_items_map.get(configuracao.funcionalidade)
            if not item:
                continue
            atalhos_administracao.append(
                {
                    "funcionalidade": configuracao.funcionalidade,
                    "titulo": item["titulo"],
                    "url": item["url"],
                    "imagem": configuracao.imagem,
                }
            )
        atalhos_administracao.sort(key=lambda item: item["titulo"].casefold())
        context["atalhos_administracao"] = atalhos_administracao
        try:
            context["atalhos_servicos"] = AtalhoServico.objects.filter(ativo=True)
        except (OperationalError, ProgrammingError):
            context["atalhos_servicos"] = AtalhoServico.objects.none()
        return context

"""
Views do app `noticias`.

Este módulo concentra os fluxos HTTP de listagem, detalhe e manutenção (CRUD)
de notícias. As views consomem o model `Noticia`, resolvem autorização por
permissão Django e entregam dados para templates HTML.

Integrações relevantes:
- `administracao.models.AtalhoServico`: injeta atalhos ativos no contexto da home.
- `django.contrib.auth.mixins`: aplica regras de autenticação/autorização.
- Templates em `templates/noticias/`: renderizam a camada de apresentação.
"""
from django.contrib.auth.mixins import PermissionRequiredMixin, UserPassesTestMixin
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from administracao.models import AtalhoServico
from .models import Noticia


class NoticiaListView(ListView):
    """
    Controla o endpoint de listagem de notícias.

    Fluxo HTTP:
    - Recebe requisição GET.
    - Consulta notícias com ordenação definida no model.
    - Pagina resultados e renderiza template de listagem.
    """
    model = Noticia
    template_name = 'noticias/noticia_list.html'
    context_object_name = 'noticias'
    paginate_by = 6

    def get_context_data(self, **kwargs):
        """
        Enriquecer o contexto da listagem com atalhos de serviços ativos.

        Parâmetros:
            **kwargs: contexto base fornecido pela `ListView`.

        Retorno:
            dict: contexto final para renderização do template.

        Regra de negócio:
    - Apenas atalhos com `ativo=True` devem aparecer na listagem, evitando
      exibição de funcionalidades desativadas operacionalmente.
        """
        context = super().get_context_data(**kwargs)
        # Consulta ORM para recuperar atalhos disponíveis na home.
        # Resultado esperado: queryset de `AtalhoServico` ativos.
        context["atalhos_servicos"] = AtalhoServico.objects.filter(ativo=True)
        return context


class NoticiaDetailView(DetailView):
    """
    Controla o endpoint de detalhe de uma notícia.

    Fluxo HTTP:
    - Recebe GET com `pk`.
    - Carrega uma instância de `Noticia` pelo identificador.
    - Renderiza template de detalhe com os dados completos.
    """
    model = Noticia
    template_name = 'noticias/noticia_detail.html'


class StaffOnlyMixin(UserPassesTestMixin):
    """
    Mixin de autorização para restringir acesso a usuários internos (staff).

    Papel arquitetural:
    - Centralizar uma política de acesso reutilizável em views sensíveis.
    - Evitar repetição de regra de autenticação/autorização por classe.
    """
    def test_func(self) -> bool:
        """
        Valida se o usuário da requisição pode acessar o recurso protegido.

        Retorno:
            bool: `True` quando autenticado e com flag `is_staff`.
        """
        # Regra de negócio: operações de backoffice exigem vínculo staff.
        return self.request.user.is_authenticated and self.request.user.is_staff


class NoticiaCreateView(PermissionRequiredMixin, CreateView):
    """
    Controla o fluxo HTTP de criação de notícia.

    Fluxo HTTP:
    - GET: exibe formulário.
    - POST: valida e persiste nova notícia no banco.

    Segurança:
    - Exige permissão Django `noticias.add_noticia`.
    """
    model = Noticia
    fields = ['titulo', 'texto', 'data_publicacao', 'categoria', 'imagem_destaque']
    template_name = 'noticias/noticia_form.html'
    success_url = reverse_lazy('noticia_list')
    permission_required = "noticias.add_noticia"


class NoticiaUpdateView(PermissionRequiredMixin, UpdateView):
    """
    Controla o fluxo HTTP de edição de notícia existente.

    Fluxo HTTP:
    - GET: carrega a notícia por `pk` e exibe formulário preenchido.
    - POST: valida alterações e atualiza a entidade.

    Segurança:
    - Exige permissão Django `noticias.change_noticia`.
    """
    model = Noticia
    fields = ['titulo', 'texto', 'data_publicacao', 'categoria', 'imagem_destaque']
    template_name = 'noticias/noticia_form.html'
    success_url = reverse_lazy('noticia_list')
    permission_required = "noticias.change_noticia"


class NoticiaDeleteView(PermissionRequiredMixin, DeleteView):
    """
    Controla o fluxo HTTP de exclusão de notícia.

    Fluxo HTTP:
    - GET: apresenta tela de confirmação.
    - POST: remove registro e redireciona para home.

    Segurança:
    - Exige permissão Django `noticias.delete_noticia`.
    """
    model = Noticia
    template_name = 'noticias/noticia_confirm_delete.html'
    success_url = reverse_lazy('noticia_list')
    permission_required = "noticias.delete_noticia"

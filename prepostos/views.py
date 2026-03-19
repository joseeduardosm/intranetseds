"""
Views do app `prepostos`.

Este módulo implementa os fluxos HTTP de listagem, criação, edição, detalhe e
exclusão de prepostos. As classes utilizam Generic Views do Django para reduzir
boilerplate e manter consistência no CRUD.

Integração arquitetural:
- Model: `Preposto` (camada de dados).
- Templates: `templates/prepostos/*` (camada de apresentação).
- URLs: mapeadas em `prepostos/urls.py`.
- Autenticação: `LoginRequiredMixin` restringe acesso a usuários logados.
"""
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from .models import Preposto


class PrepostoListView(LoginRequiredMixin, ListView):
    """
    Controla o endpoint de listagem de prepostos.

    Fluxo HTTP:
    - Recebe GET autenticado.
    - Consulta `Preposto` via queryset padrão da `ListView`.
    - Renderiza a lista no template definido.
    """
    model = Preposto
    template_name = "prepostos/preposto_list.html"
    context_object_name = "prepostos"


class PrepostoCreateView(LoginRequiredMixin, CreateView):
    """
    Controla o endpoint de criação de preposto.

    Fluxo HTTP:
    - GET: exibe formulário de cadastro.
    - POST: valida dados e persiste novo `Preposto`.
    """
    model = Preposto
    fields = ["nome", "cpf", "telefone", "email", "empresa"]
    template_name = "prepostos/preposto_form.html"
    success_url = reverse_lazy("prepostos_list")


class PrepostoUpdateView(LoginRequiredMixin, UpdateView):
    """
    Controla o endpoint de edição de preposto existente.

    Fluxo HTTP:
    - GET: carrega registro por `pk` e exibe formulário preenchido.
    - POST: valida alteração e atualiza o registro.
    """
    model = Preposto
    fields = ["nome", "cpf", "telefone", "email", "empresa"]
    template_name = "prepostos/preposto_form.html"

    def get_success_url(self):
        """
        Define redirecionamento após atualização com sucesso.

        Retorno:
            str: URL do detalhe do preposto recém-atualizado.

        Regra de UX:
        - Após editar, direciona para a tela de detalhe para conferência dos
          dados persistidos, em vez de retornar diretamente para a listagem.
        """
        return reverse_lazy("prepostos_detail", kwargs={"pk": self.object.pk})


class PrepostoDetailView(LoginRequiredMixin, DetailView):
    """
    Controla o endpoint de detalhe de um preposto.

    Fluxo HTTP:
    - Recebe GET com `pk`.
    - Carrega o registro específico e renderiza seus dados completos.
    """
    model = Preposto
    template_name = "prepostos/preposto_detail.html"
    context_object_name = "preposto"


class PrepostoDeleteView(LoginRequiredMixin, DeleteView):
    """
    Controla o endpoint de exclusão de preposto.

    Fluxo HTTP:
    - GET: exibe página de confirmação de exclusão.
    - POST: remove o registro e redireciona para listagem.
    """
    model = Preposto
    template_name = "prepostos/preposto_confirm_delete.html"
    success_url = reverse_lazy("prepostos_list")

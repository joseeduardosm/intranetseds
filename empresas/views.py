"""
Views do app `empresas`.

Este módulo controla os fluxos HTTP de CRUD de empresas (listagem, criação,
edição, detalhe e exclusão), integrando:
- ORM de `Empresa` para persistência/consulta;
- templates `empresas/*` para renderização;
- relacionamentos com `prepostos` e `contratos` no detalhe.
"""

from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from .models import Empresa


class EmpresaListView(LoginRequiredMixin, ListView):
    """Lista empresas cadastradas para usuários autenticados."""

    model = Empresa
    template_name = "empresas/empresa_list.html"
    context_object_name = "empresas"

    def get_queryset(self):
        """
        Retorna queryset de empresas com pré-carregamento de prepostos.

        Consulta ORM:
        - `prefetch_related("prepostos")` reduz N+1 ao acessar relacionamentos.
        """

        return Empresa.objects.prefetch_related("prepostos")


class EmpresaCreateView(LoginRequiredMixin, CreateView):
    """Fluxo HTTP de criação de empresa."""

    model = Empresa
    fields = ["nome", "cnpj"]
    template_name = "empresas/empresa_form.html"
    success_url = reverse_lazy("empresas_list")


class EmpresaUpdateView(LoginRequiredMixin, UpdateView):
    """Fluxo HTTP de edição de empresa existente."""

    model = Empresa
    fields = ["nome", "cnpj"]
    template_name = "empresas/empresa_form.html"

    def get_success_url(self):
        """
        Redireciona para tela de detalhe após atualização.

        Retorno:
        - `str`: URL nomeada `empresas_detail` do objeto editado.
        """

        return reverse_lazy("empresas_detail", kwargs={"pk": self.object.pk})


class EmpresaDetailView(LoginRequiredMixin, DetailView):
    """Exibe detalhes da empresa e relacionamentos operacionais."""

    model = Empresa
    template_name = "empresas/empresa_detail.html"
    context_object_name = "empresa"

    def get_context_data(self, **kwargs):
        """
        Enriquecimento de contexto com prepostos e contratos da empresa.

        Consulta ORM:
        - usa relacionamentos reversos para listar vínculos operacionais.
        """

        context = super().get_context_data(**kwargs)
        context["prepostos"] = self.object.prepostos.all()
        context["contratos"] = self.object.contratos.all()
        return context


class EmpresaDeleteView(LoginRequiredMixin, DeleteView):
    """Fluxo HTTP de exclusão de empresa."""

    model = Empresa
    template_name = "empresas/empresa_confirm_delete.html"
    success_url = reverse_lazy("empresas_list")

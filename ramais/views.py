"""
Views do app `ramais`.

Este módulo implementa os fluxos HTTP do diretório de pessoas/ramais, incluindo
listagem com busca, detalhe, CRUD e visualização hierárquica (organograma).

Integrações arquiteturais:
- Model `PessoaRamal` para persistência e relacionamentos.
- Form `PessoaRamalForm` para controle de campos e permissões.
- Templates em `templates/ramais/` para renderização da interface.
"""
from django.contrib.auth.mixins import PermissionRequiredMixin, UserPassesTestMixin
from django.db.models import Q
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView


from .models import PessoaRamal
from .forms import PessoaRamalForm


RAMAIS_EXCLUDED_USERNAMES = {"admin"}


class PessoaRamalListView(ListView):
    """
    Controla o endpoint de listagem de ramais com busca textual.

    Fluxo HTTP:
    - GET sem `q`: lista padrão paginada.
    - GET com `q`: aplica filtros OR em múltiplos campos de identificação.
    """
    model = PessoaRamal
    template_name = 'ramais/ramais_list.html'
    context_object_name = 'ramais'
    paginate_by = 12

    def get_queryset(self):
        """
        Monta o queryset de listagem com otimização e filtro opcional.

        Retorno:
            QuerySet[PessoaRamal]: registros aptos à listagem.

        Decisões de implementação:
        - `select_related` reduz N+1 queries em usuário/superior.
        - `usuario__isnull=False` garante foco em perfis vinculados ao auth.
        - Busca livre usa `Q` para combinar campos por OR sem excluir resultados
          relevantes para o usuário final.
        """
        queryset = (
            super()
            .get_queryset()
            .select_related('usuario', 'superior', 'superior__usuario')
            .filter(usuario__isnull=False)
            .exclude(usuario__username__in=RAMAIS_EXCLUDED_USERNAMES)
        )
        termo = self.request.GET.get('q', '').strip()
        if termo:
            # Consulta ORM de busca textual abrangente para suportar diferentes
            # formas de localização (nome, setor, ramal, e-mail etc.).
            queryset = queryset.filter(
                Q(usuario__first_name__icontains=termo)
                | Q(usuario__username__icontains=termo)
                | Q(usuario__email__icontains=termo)
                | Q(nome__icontains=termo)
                | Q(cargo__icontains=termo)
                | Q(setor__icontains=termo)
                | Q(ramal__icontains=termo)
                | Q(email__icontains=termo)
            )
        return queryset


class PessoaRamalDetailView(DetailView):
    """
    Controla o endpoint de detalhe de um ramal específico.

    Fluxo HTTP:
    - GET com `pk`.
    - Carrega registro com relacionamento de superior e usuário.
    """
    model = PessoaRamal
    template_name = 'ramais/ramais_detail.html'

    def get_queryset(self):
        """
        Define queryset com joins necessários para tela de detalhe.

        Retorno:
            QuerySet[PessoaRamal]: conjunto com relacionamentos carregados.
        """
        return (
            super()
            .get_queryset()
            .select_related('usuario', 'superior', 'superior__usuario')
        )


class PessoaRamalCreateView(PermissionRequiredMixin, CreateView):
    """
    Controla o fluxo HTTP de criação de perfil de ramal.

    Segurança:
    - Exige permissão `ramais.add_pessoaramal`.
    """
    model = PessoaRamal
    form_class = PessoaRamalForm
    template_name = 'ramais/ramais_form.html'
    success_url = reverse_lazy('ramais_list')
    permission_required = "ramais.add_pessoaramal"

    def get_form_kwargs(self):
        """
        Injeta usuário da requisição no formulário.

        Retorno:
            dict: kwargs do formulário com `user` para regras de permissão.
        """
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs


class PessoaRamalUpdateView(UserPassesTestMixin, UpdateView):
    """
    Controla o fluxo HTTP de edição de ramal.

    Segurança:
    - Staff e usuários com permissão de alteração global podem editar qualquer
      registro.
    - Usuário comum pode editar apenas o próprio perfil vinculado.
    """
    model = PessoaRamal
    form_class = PessoaRamalForm
    template_name = 'ramais/ramais_form.html'
    success_url = reverse_lazy('ramais_list')

    def test_func(self):
        """
        Valida autorização de edição do objeto alvo.

        Retorno:
            bool: `True` quando o usuário pode editar o registro.
        """
        user = self.request.user
        if not user.is_authenticated:
            return False
        if user.is_staff or user.has_perm("ramais.change_pessoaramal"):
            return True
        return self.get_object().usuario_id == user.id

    def get_form_kwargs(self):
        """
        Injeta usuário corrente no formulário para restrições dinâmicas.

        Retorno:
            dict: kwargs de formulário com chave `user`.
        """
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs


class PessoaRamalDeleteView(PermissionRequiredMixin, DeleteView):
    """
    Controla o fluxo HTTP de exclusão de ramal.

    Segurança:
    - Exige permissão `ramais.delete_pessoaramal`.
    """
    model = PessoaRamal
    template_name = 'ramais/ramais_confirm_delete.html'
    success_url = reverse_lazy('ramais_list')
    permission_required = "ramais.delete_pessoaramal"


class OrganogramaView(ListView):
    """
    Controla o endpoint de visualização do organograma institucional.

    Fluxo HTTP:
    - Recupera pessoas com vínculo de usuário.
    - Constrói árvore em memória com base na relação `superior`.
    - Entrega estrutura hierárquica ao template.
    """
    model = PessoaRamal
    template_name = 'ramais/organograma.html'
    context_object_name = 'pessoas'

    def get_queryset(self):
        """
        Recupera pessoas para construção do organograma.

        Retorno:
            QuerySet[PessoaRamal]: base plana para montagem da árvore.

        Observação de performance:
        - `select_related` antecipa joins para evitar consultas extras durante
          a renderização da hierarquia.
        """
        return (
            PessoaRamal.objects.select_related('usuario', 'superior', 'superior__usuario')
            .filter(usuario__isnull=False)
            .exclude(usuario__username__in=RAMAIS_EXCLUDED_USERNAMES)
            .all()
        )

    def _build_tree(self, pessoas):
        """
        Converte lista plana de pessoas em árvore hierárquica.

        Parâmetros:
            pessoas (iterable[PessoaRamal]): coleção de registros carregados.

        Retorno:
            list[dict]: nós raiz com estrutura `{pessoa, children}`.

        Decisão algorítmica:
        - Usa mapa `id -> nó` para montar a árvore em O(n), evitando buscas
          repetidas por superior em listas (que degradariam para O(n²)).
        """
        nodes = {p.id: {'pessoa': p, 'children': []} for p in pessoas}
        roots = []
        for p in pessoas:
            if p.superior_id and p.superior_id in nodes:
                nodes[p.superior_id]['children'].append(nodes[p.id])
            else:
                roots.append(nodes[p.id])
        return roots

    def get_context_data(self, **kwargs):
        """
        Injeta dados hierárquicos no contexto da página de organograma.

        Parâmetros:
            **kwargs: contexto base da `ListView`.

        Retorno:
            dict: contexto final com `org_tree` para renderização recursiva.
        """
        context = super().get_context_data(**kwargs)
        context['org_tree'] = self._build_tree(context['pessoas'])
        return context

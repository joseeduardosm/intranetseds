"""
Views do app `usuarios`.

Este módulo implementa os fluxos HTTP de administração de usuários e grupos,
utilizando modelos nativos do Django (`auth.User` e `auth.Group`) e formulários
customizados do app para aplicar regras de perfil/permissão.

Integração na arquitetura Django:
- `forms.py`: validações e persistência de perfis, grupos e dados de ramal;
- `permissions.py`: matriz de perfis e convenções de grupo ADMIN;
- templates `templates/usuarios/*`: renderização das telas de gestão;
- `auditoria.AuditLog`: ajuste de vínculo em exclusão de usuário.
"""

from django.contrib.auth.mixins import UserPassesTestMixin
from django.contrib.auth.models import Group, User
from django.contrib import messages
from django.db import transaction
from django.db.models import Case, CharField, Count, Min, Prefetch, Q, Value, When
from django.db.models.functions import Coalesce
from django.db.utils import IntegrityError
from django.http import QueryDict
from django.http import HttpResponseRedirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from auditoria.models import AuditLog

from .forms import GrupoCreateForm, GrupoUpdateForm, UsuarioCreateForm, UsuarioUpdateForm
from .models import GrantEffect, PermissionResolutionAudit, SetorGrant, SetorNode, UserSetorMembership
from .permissions import ADMIN_GROUP_NAME, build_profile_matrix, get_profile_permission_ids_map


def _compute_inherited_profile_names_for_group(group: Group | None) -> set[str]:
    """Calcula perfis herdados por grants ALLOW/DENY dos setores ancestrais."""
    if not group or not getattr(group, "pk", None):
        return set()

    setor = SetorNode.objects.select_related("parent").filter(group=group).first()
    if not setor:
        return set()

    ancestry = setor.get_ancestry()[1:]
    if not ancestry:
        return set()

    ancestry_ids = [node.id for node in ancestry if node and node.id]
    if not ancestry_ids:
        return set()

    allow_ids = set(
        SetorGrant.objects.filter(setor_id__in=ancestry_ids, effect=GrantEffect.ALLOW).values_list(
            "permission_id", flat=True
        )
    )
    deny_ids = set(
        SetorGrant.objects.filter(setor_id__in=ancestry_ids, effect=GrantEffect.DENY).values_list(
            "permission_id", flat=True
        )
    )
    inherited_perm_ids = allow_ids - deny_ids
    if not inherited_perm_ids:
        return set()

    inherited_profiles = set()
    for profile_name, required_perm_ids in get_profile_permission_ids_map().items():
        if required_perm_ids and required_perm_ids.issubset(inherited_perm_ids):
            inherited_profiles.add(profile_name)
    return inherited_profiles


def _build_perfil_matrix_context(form, inherited_profiles: set[str] | None = None):
    """Monta matriz app x nível, marcando e bloqueando perfis herdados."""
    inherited_profiles = set(inherited_profiles or set())
    checkbox_map = {}
    if form is not None:
        checkbox_map = {item.data["value"]: item for item in form["perfis"]}
    matrix = []
    for row in build_profile_matrix():
        cells = []
        for level in row["levels"]:
            profile_name = level["group"]
            checkbox = checkbox_map.get(profile_name)
            cells.append(
                {
                    "checkbox": checkbox,
                    "profile_name": profile_name,
                    "is_inherited": profile_name in inherited_profiles,
                }
            )
        matrix.append({"label": row["label"], "cells": cells})
    return matrix


class StaffOnlyMixin(UserPassesTestMixin):
    """
    Mixin de autorização para páginas administrativas de usuários/grupos.

    Regra de negócio:
    - Permite acesso para staff/superuser ou para usuários com permissões de
      CRUD de `auth.User`.
    """

    def test_func(self) -> bool:
        """
        Valida se o usuário autenticado pode acessar a view.

        Retorno:
        - `bool`: `True` quando o usuário tem privilégio administrativo.
        """
        user = self.request.user
        if not user.is_authenticated:
            return False
        return bool(
            user.is_staff
            or user.is_superuser
            or user.has_perm("auth.view_user")
            or user.has_perm("auth.change_user")
            or user.has_perm("auth.add_user")
            or user.has_perm("auth.delete_user")
        )


class UsuarioListView(StaffOnlyMixin, ListView):
    """
    Lista usuários do sistema com busca textual.

    Fluxo HTTP controlado:
    - `GET /usuarios/`.
    """

    model = User
    template_name = "usuarios/user_list.html"
    context_object_name = "usuarios"
    paginate_by = 11
    SORT_FIELDS = {
        "nome": ("first_name", "last_name", "username"),
        "login": ("username",),
        "email": ("email", "username"),
        "setor": ("setor_sort", "username"),
    }

    @staticmethod
    def _build_setor_filter(term: str) -> Q:
        """Monta filtro de setor considerando rótulos exibidos na tela."""

        filtro = Q(groups__name__icontains=term) | Q(
            setor_memberships__setor__group__name__icontains=term
        )
        if "admin" in term.lower():
            filtro |= Q(is_superuser=True)
        return filtro

    def get_queryset(self):
        """
        Retorna queryset de usuários ordenados e filtrados por termo opcional.

        Consulta ORM:
        - Base: `User.objects.order_by("username")`.
        - Filtro: busca em username, nome, sobrenome, email e nome de grupo.

        Retorno:
        - `QuerySet[User]` com `distinct()` quando há filtro por relacionamento.
        """
        queryset = User.objects.prefetch_related(
            "groups",
            Prefetch(
                "setor_memberships",
                queryset=UserSetorMembership.objects.select_related("setor__group").order_by(
                    "setor__group__name"
                ),
            ),
        ).annotate(
            setor_sort=Coalesce(
                Case(
                    When(is_superuser=True, then=Value("Admin")),
                    default=Coalesce(Min("setor_memberships__setor__group__name"), Min("groups__name")),
                    output_field=CharField(),
                ),
                Value(""),
            )
        )
        term = self.request.GET.get("q", "").strip()
        nome = self.request.GET.get("nome", "").strip()
        login = self.request.GET.get("login", "").strip()
        email = self.request.GET.get("email", "").strip()
        setor = self.request.GET.get("setor", "").strip()
        sort = self.request.GET.get("sort", "login").strip().lower()
        direction = self.request.GET.get("dir", "asc").strip().lower()

        if term:
            queryset = queryset.filter(
                Q(username__icontains=term)
                | Q(first_name__icontains=term)
                | Q(last_name__icontains=term)
                | Q(email__icontains=term)
                | self._build_setor_filter(term)
            )
        if nome:
            queryset = queryset.filter(Q(first_name__icontains=nome) | Q(last_name__icontains=nome))
        if login:
            queryset = queryset.filter(username__icontains=login)
        if email:
            queryset = queryset.filter(email__icontains=email)
        if setor:
            queryset = queryset.filter(self._build_setor_filter(setor))
        if term or setor:
            queryset = queryset.distinct()

        if sort not in self.SORT_FIELDS:
            sort = "login"
        if direction not in {"asc", "desc"}:
            direction = "asc"

        ordering = list(self.SORT_FIELDS[sort])
        if direction == "desc":
            ordering = [f"-{field}" for field in ordering]
        return queryset.order_by(*ordering)

    def get_context_data(self, **kwargs):
        """Expõe valores atuais de filtro e querystring para paginação."""

        context = super().get_context_data(**kwargs)
        filtros = {
            "q": self.request.GET.get("q", "").strip(),
            "nome": self.request.GET.get("nome", "").strip(),
            "login": self.request.GET.get("login", "").strip(),
            "email": self.request.GET.get("email", "").strip(),
            "setor": self.request.GET.get("setor", "").strip(),
        }
        current_sort = self.request.GET.get("sort", "login").strip().lower()
        current_dir = self.request.GET.get("dir", "asc").strip().lower()
        if current_sort not in self.SORT_FIELDS:
            current_sort = "login"
        if current_dir not in {"asc", "desc"}:
            current_dir = "asc"
        pagination_query = QueryDict(mutable=True)
        for chave, valor in filtros.items():
            if valor:
                pagination_query[chave] = valor
        pagination_query["sort"] = current_sort
        pagination_query["dir"] = current_dir

        sort_links = {}
        for field in self.SORT_FIELDS:
            params = QueryDict(mutable=True)
            for chave, valor in filtros.items():
                if valor:
                    params[chave] = valor
            params["sort"] = field
            params["dir"] = "desc" if current_sort == field and current_dir == "asc" else "asc"
            sort_links[field] = params.urlencode()

        context["filtros"] = filtros
        context["current_sort"] = current_sort
        context["current_dir"] = current_dir
        context["pagination_query"] = pagination_query.urlencode()
        context["sort_links"] = sort_links
        return context


class UsuarioCreateView(StaffOnlyMixin, CreateView):
    """
    Cria novo usuário com configuração de perfis e dados de ramal.

    Fluxo HTTP controlado:
    - `GET /usuarios/novo/`.
    - `POST /usuarios/novo/`.
    """

    model = User
    form_class = UsuarioCreateForm
    template_name = "usuarios/user_form.html"
    success_url = reverse_lazy("usuarios_list")

    def get_form_kwargs(self):
        """
        Injeta o usuário autenticado no formulário para regras condicionais.

        Retorno:
        - `dict`: kwargs padrão + `current_user`.
        """
        kwargs = super().get_form_kwargs()
        kwargs["current_user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        """
        Persiste usuário com senha criptografada e dados complementares.

        Regras de negócio:
        - senha é definida via `set_password` para armazenamento seguro;
        - perfis/grupos e perfil de ramal são aplicados após salvar usuário.

        Retorno:
        - `HttpResponseRedirect` para listagem de usuários.
        """
        self.object = form.save(commit=False)
        self.object.set_password(form.cleaned_data["password"])
        self.object.save()
        form.apply_profiles(self.object)
        form.save_setor_memberships(self.object)
        form.save_ramal(self.object)
        return HttpResponseRedirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        """
        Monta matriz de perfis para renderização tabular no template.

        Problema que resolve:
        - exibe checkboxes de perfil em layout por app x nível de acesso.

        Retorno:
        - `dict`: contexto padrão acrescido de `perfil_matrix`.
        """
        context = super().get_context_data(**kwargs)
        form = context.get("form")
        checkbox_map = {}
        if form is not None:
            checkbox_map = {item.data["value"]: item for item in form["perfis"]}
        matrix = []
        for row in build_profile_matrix():
            cells = []
            for level in row["levels"]:
                checkbox = checkbox_map.get(level["group"])
                cells.append(checkbox.tag if checkbox else "")
            matrix.append({"label": row["label"], "cells": cells})
        context["perfil_matrix"] = matrix
        return context


class UsuarioUpdateView(StaffOnlyMixin, UpdateView):
    """
    Atualiza dados de usuário existente, incluindo perfis e ramal.

    Fluxo HTTP controlado:
    - `GET /usuarios/<pk>/editar/`.
    - `POST /usuarios/<pk>/editar/`.
    """

    model = User
    form_class = UsuarioUpdateForm
    template_name = "usuarios/user_form.html"
    success_url = reverse_lazy("usuarios_list")

    def get_form_kwargs(self):
        """
        Injeta `current_user` para permitir bloqueio condicional de campos.
        """
        kwargs = super().get_form_kwargs()
        kwargs["current_user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        """
        Salva alterações do usuário e aplica atualizações complementares.

        Regras de negócio:
        - se senha foi informada, atualiza hash no usuário;
        - reaplica perfis/permissões e dados de ramal.

        Retorno:
        - resposta de redirecionamento da `UpdateView`.
        """
        response = super().form_valid(form)
        senha = form.cleaned_data.get("password")
        if senha:
            self.object.set_password(senha)
            self.object.save(update_fields=["password"])
        form.apply_profiles(self.object)
        form.save_setor_memberships(self.object)
        form.save_ramal(self.object)
        return response

    def get_context_data(self, **kwargs):
        """
        Reutiliza montagem da matriz de perfis para tela de edição.
        """
        context = super().get_context_data(**kwargs)
        form = context.get("form")
        checkbox_map = {}
        if form is not None:
            checkbox_map = {item.data["value"]: item for item in form["perfis"]}
        matrix = []
        for row in build_profile_matrix():
            cells = []
            for level in row["levels"]:
                checkbox = checkbox_map.get(level["group"])
                cells.append(checkbox.tag if checkbox else "")
            matrix.append({"label": row["label"], "cells": cells})
        context["perfil_matrix"] = matrix
        return context


class UsuarioDeleteView(StaffOnlyMixin, DeleteView):
    """
    Exclui usuário, com tratamento de integridade para auditoria legado.

    Fluxo HTTP controlado:
    - `GET /usuarios/<pk>/excluir/`.
    - `POST /usuarios/<pk>/excluir/`.
    """

    model = User
    template_name = "usuarios/user_confirm_delete.html"
    success_url = reverse_lazy("usuarios_list")

    def post(self, request, *args, **kwargs):
        """
        Executa exclusão em transação e trata conflitos de integridade.

        Regra de negócio:
        - antes de excluir usuário, remove referência em `AuditLog.user` para
          evitar falha em bancos legados com restrição de FK mais rígida.

        Retorno:
        - redireciona para listagem em sucesso ou em erro tratado.
        """
        self.object = self.get_object()
        try:
            with transaction.atomic():
                # Protege contra FK legado no MySQL que ainda bloqueia delete em audit log.
                AuditLog.objects.filter(user=self.object).update(user=None)
                return super().post(request, *args, **kwargs)
        except IntegrityError:
            messages.error(
                request,
                "Nao foi possivel excluir o usuario devido a vinculos de integridade no banco.",
            )
            return HttpResponseRedirect(self.success_url)


class GrupoListView(StaffOnlyMixin, ListView):
    """
    Lista grupos de acesso com busca por nome e membros.

    Fluxo HTTP controlado:
    - `GET /usuarios/grupos/`.
    """

    model = SetorNode
    template_name = "usuarios/group_list.html"
    context_object_name = "setores"
    paginate_by = 11

    def get_queryset(self):
        """
        Retorna grupos ordenados, com filtro textual opcional.

        Consulta ORM:
        - Base: `Group.objects.order_by("name")`.
        - Filtro: nome do grupo e atributos de usuários membros.

        Retorno:
        - `QuerySet[SetorNode]`.
        """
        term = self.request.GET.get("q", "").strip()
        queryset = SetorNode.objects.select_related("group", "parent__group").annotate(
            member_count=Count("memberships", distinct=True)
        )
        if term:
            queryset = queryset.filter(
                Q(group__name__icontains=term)
                | Q(parent__group__name__icontains=term)
                | Q(memberships__user__username__icontains=term)
                | Q(memberships__user__first_name__icontains=term)
                | Q(memberships__user__email__icontains=term)
            ).distinct()
        return queryset.order_by("group__name")


class GrupoCreateView(StaffOnlyMixin, CreateView):
    """
    Cria grupo e aplica membros/perfis associados.

    Fluxo HTTP controlado:
    - `GET /usuarios/grupos/novo/`.
    - `POST /usuarios/grupos/novo/`.
    """

    model = Group
    form_class = GrupoCreateForm
    template_name = "usuarios/group_form.html"
    success_url = reverse_lazy("setores_list")

    def form_valid(self, form):
        """
        Salva grupo e aplica vínculos de usuários e permissões derivadas.
        """
        response = super().form_valid(form)
        form.save_membership_and_permissions(self.object)
        return response

    def get_context_data(self, **kwargs):
        """
        Fornece matriz de perfis para a tela de criação de grupo.
        """
        context = super().get_context_data(**kwargs)
        form = context.get("form")
        context["perfil_matrix"] = _build_perfil_matrix_context(form)
        return context


class GrupoUpdateView(StaffOnlyMixin, UpdateView):
    """
    Atualiza dados de grupo e reaplica membros/perfis.

    Fluxo HTTP controlado:
    - `GET /usuarios/grupos/<pk>/editar/`.
    - `POST /usuarios/grupos/<pk>/editar/`.
    """

    model = Group
    form_class = GrupoUpdateForm
    template_name = "usuarios/group_form.html"
    success_url = reverse_lazy("setores_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["inherited_profile_names"] = _compute_inherited_profile_names_for_group(self.object)
        return kwargs

    def form_valid(self, form):
        """
        Salva metadados do grupo e sincroniza associação/permissões.
        """
        response = super().form_valid(form)
        form.save_membership_and_permissions(self.object)
        return response

    def get_context_data(self, **kwargs):
        """
        Fornece matriz de perfis para a tela de edição de grupo.
        """
        context = super().get_context_data(**kwargs)
        form = context.get("form")
        inherited_profiles = set(getattr(form, "inherited_profile_names", set()) or set())
        context["perfil_matrix"] = _build_perfil_matrix_context(form, inherited_profiles=inherited_profiles)
        return context


class GrupoDeleteView(StaffOnlyMixin, DeleteView):
    """
    Exclui grupos de acesso, exceto o grupo ADMIN protegido.

    Fluxo HTTP controlado:
    - `GET /usuarios/grupos/<pk>/excluir/`.
    - `POST /usuarios/grupos/<pk>/excluir/`.
    """

    model = Group
    template_name = "usuarios/group_confirm_delete.html"
    success_url = reverse_lazy("setores_list")

    def get_queryset(self):
        """
        Restringe queryset para impedir exclusão do grupo ADMIN.

        Consulta ORM:
        - `Group.objects.exclude(name=ADMIN_GROUP_NAME)`.

        Retorno:
        - `QuerySet[Group]` sem grupo administrativo raiz.
        """
        return Group.objects.exclude(name=ADMIN_GROUP_NAME)


class PermissionAuditListView(StaffOnlyMixin, ListView):
    """
    Exibe trilha de auditoria das resoluções de permissão.
    """

    model = PermissionResolutionAudit
    template_name = "usuarios/permission_audit_list.html"
    context_object_name = "audits"
    paginate_by = 30

    def get_queryset(self):
        queryset = PermissionResolutionAudit.objects.select_related("user", "source_setor__group")
        user_id = self.request.GET.get("user", "").strip()
        permission_code = self.request.GET.get("permission", "").strip()
        if user_id.isdigit():
            queryset = queryset.filter(user_id=int(user_id))
        if permission_code:
            queryset = queryset.filter(permission_code__icontains=permission_code)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["users"] = User.objects.order_by("first_name", "username")
        context["selected_user"] = self.request.GET.get("user", "").strip()
        context["selected_permission"] = self.request.GET.get("permission", "").strip()
        return context

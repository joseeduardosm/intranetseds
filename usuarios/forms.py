"""
Formulários do app `usuarios`.

Este módulo centraliza validação e persistência dos dados de gestão de usuários
(`auth.User`) e grupos (`auth.Group`), incluindo:
- mapeamento de perfis para permissões;
- vínculo com dados complementares de ramal (`ramais.PessoaRamal`);
- regras de segurança para campos sensíveis de folha de ponto.

Integração na arquitetura Django:
- consumido por `views.py` em fluxos Create/Update;
- utiliza utilitários de `permissions.py` para calcular perfis;
- persiste atributos extras no app `ramais`.
"""

from django import forms
from django.contrib.auth.models import Group, Permission, User
from django.db import transaction

from ramais.models import PessoaRamal

from .auth_backends import ensure_setor_node_for_group
from .models import GrantEffect, SetorGrant, SetorNode, UserSetorMembership
from .permissions import (
    ADMIN_GROUP_NAME,
    PROFILE_DEFINITIONS,
    build_group_name,
    ensure_profiles,
    get_profile_permission_ids_map,
)
from .utils import usuarios_visiveis


def _profile_choices():
    """
    Monta opções de escolha de perfis para checkboxes do formulário.

    Retorno:
    - `list[tuple[str, str]]`: pares `(nome_do_grupo, rótulo_exibido)`.
    """
    label_map = {
        "Leitura": "Leitura (Consultar)",
        "Edicao": "Edicao (Criar/Editar)",
        "Administracao": "Administracao (Excluir)",
    }
    choices = []
    for app_label, config in PROFILE_DEFINITIONS.items():
        for level, _actions in config["levels"]:
            label = label_map.get(level, level)
            choices.append((build_group_name(app_label, level), f"{app_label} - {label}"))
    return choices


def _infer_profiles_from_permission_ids(permission_ids):
    """
    Infere perfis selecionados a partir de um conjunto de permissões do usuário.

    Parâmetros:
    - `permission_ids`: conjunto/lista de ids de permissões já atribuídas.

    Retorno:
    - `list[str]`: nomes de perfis cujo conjunto de permissões está contido no
      conjunto informado.
    """
    profile_perm_ids = get_profile_permission_ids_map()
    selected = []
    for profile_name, required_perm_ids in profile_perm_ids.items():
        if required_perm_ids and required_perm_ids.issubset(permission_ids):
            selected.append(profile_name)
    return selected


def _setor_choices(valor_atual=""):
    """
    Monta lista de setores a partir dos grupos existentes no sistema.

    Se o usuário já tiver um setor salvo fora da lista atual, preserva a opção
    para evitar perda de dados ao editar o cadastro.
    """
    nomes = list(
        SetorNode.objects.select_related("group")
        .filter(ativo=True)
        .order_by("group__name")
        .values_list("group__name", flat=True)
    )
    valor_atual = (valor_atual or "").strip()
    if valor_atual and valor_atual not in nomes:
        nomes.append(valor_atual)
    return [(nome, nome) for nome in nomes]


class SuperiorChoiceField(forms.ModelChoiceField):
    """
    Campo de seleção de superior hierárquico com rótulo amigável.
    """

    def label_from_instance(self, obj):
        """
        Define exibição priorizando nome completo e fallback para username.
        """
        return obj.get_full_name() or obj.first_name or obj.username


class UsuarioGrupoChoiceField(forms.ModelMultipleChoiceField):
    """
    Campo de seleção múltipla de usuários para composição de grupos.
    """

    def label_from_instance(self, obj):
        """
        Exibe nome mais legível do usuário nas listas de escolha.
        """
        nome = (obj.get_full_name() or "").strip()
        if nome:
            return nome
        nome = (obj.first_name or "").strip()
        if nome:
            return nome
        return obj.username


class UsuarioBaseForm(forms.ModelForm):
    """
    Formulário base de usuário com dados nativos e complementares de ramal.

    Papel no domínio:
    - além dos campos de `auth.User`, administra perfil de acesso, indicador de
      admin e informações organizacionais/funcionais da pessoa.
    """

    admin = forms.BooleanField(
        label="Admin (acesso total)",
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )
    perfis = forms.MultipleChoiceField(
        label="Perfis",
        required=False,
        choices=_profile_choices(),
        widget=forms.CheckboxSelectMultiple,
    )
    ramal = forms.CharField(
        label="Ramal",
        required=True,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    cargo = forms.CharField(
        label="Cargo",
        required=True,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    setor = forms.ChoiceField(
        label="Setor",
        required=True,
        choices=(),
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    setores_acesso = forms.ModelMultipleChoiceField(
        label="Setores de acesso",
        required=False,
        queryset=SetorNode.objects.none(),
        widget=forms.SelectMultiple(attrs={"class": "form-control", "size": 10}),
    )
    superior_usuario = SuperiorChoiceField(
        label="Superior hierarquico",
        required=False,
        queryset=User.objects.none(),
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    bio = forms.CharField(
        label="Bio",
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}),
    )
    jornada_horas_semanais = forms.IntegerField(
        label="Jornada de Trabalho/Horas Semanais",
        required=False,
        min_value=0,
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )
    horario_trabalho_inicio = forms.TimeField(
        label="Horario de Trabalho - Inicio",
        required=False,
        widget=forms.TimeInput(attrs={"class": "form-control", "type": "time"}),
    )
    horario_trabalho_fim = forms.TimeField(
        label="Horario de Trabalho - Fim",
        required=False,
        widget=forms.TimeInput(attrs={"class": "form-control", "type": "time"}),
    )
    intervalo_inicio = forms.TimeField(
        label="Intervalo de Almoco e Descanso - Inicio",
        required=False,
        widget=forms.TimeInput(attrs={"class": "form-control", "type": "time"}),
    )
    intervalo_fim = forms.TimeField(
        label="Intervalo de Almoco e Descanso - Fim",
        required=False,
        widget=forms.TimeInput(attrs={"class": "form-control", "type": "time"}),
    )
    rg = forms.CharField(
        label="RG",
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    regime_plantao = forms.TypedChoiceField(
        label="Regime de Plantao",
        required=False,
        choices=((True, "S"), (False, "N")),
        coerce=lambda x: x in (True, "True", "true", "1", 1),
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    horario_estudante = forms.TypedChoiceField(
        label="Horario de Estudante",
        required=False,
        choices=((True, "S"), (False, "N")),
        coerce=lambda x: x in (True, "True", "true", "1", 1),
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    foto = forms.ImageField(
        label="Foto",
        required=False,
    )

    class Meta:
        model = User
        fields = ["first_name", "username", "email"]
        widgets = {
            "first_name": forms.TextInput(attrs={"class": "form-control"}),
            "username": forms.TextInput(attrs={"class": "form-control"}),
            "email": forms.EmailInput(attrs={"class": "form-control"}),
        }
        labels = {
            "first_name": "Nome",
            "username": "Login",
            "email": "Email",
        }

    def __init__(self, *args, **kwargs):
        """
        Inicializa formulário e aplica dados iniciais/contextuais.

        Regras de negócio:
        - garante bootstrap do grupo ADMIN (`ensure_profiles`);
        - carrega dados de `PessoaRamal` quando usuário já existe;
        - desabilita campos de folha para usuários sem permissão específica.
        """
        self.current_user = kwargs.pop("current_user", None)
        super().__init__(*args, **kwargs)
        ensure_profiles()
        # Remove help text padrao do Django para campos de usuario.
        for field in self.fields.values():
            field.help_text = ""
        self.fields["first_name"].required = True
        self.fields["username"].required = True
        self.fields["email"].required = True
        self.fields["setores_acesso"].queryset = SetorNode.objects.select_related("group").order_by(
            "group__name"
        )
        self.fields["setor"].choices = _setor_choices()

        # Consulta ORM para listar possíveis superiores (exceto o próprio usuário).
        superiores_qs = usuarios_visiveis(User.objects.order_by("first_name", "username"))
        if self.instance and self.instance.pk:
            superiores_qs = superiores_qs.exclude(pk=self.instance.pk)
        self.fields["superior_usuario"].queryset = superiores_qs

        self._ramal_profile = None
        if self.instance and self.instance.pk:
            self.fields["admin"].initial = self.instance.groups.filter(
                name=ADMIN_GROUP_NAME
            ).exists()
            user_perm_ids = set(self.instance.user_permissions.values_list("id", flat=True))
            self.fields["perfis"].initial = _infer_profiles_from_permission_ids(
                user_perm_ids
            )
            # Consulta ORM: busca perfil de ramal associado ao usuário em edição.
            self._ramal_profile = PessoaRamal.objects.filter(usuario=self.instance).first()
            if self._ramal_profile:
                self.fields["setor"].choices = _setor_choices(self._ramal_profile.setor)
                self.fields["ramal"].initial = self._ramal_profile.ramal
                self.fields["cargo"].initial = self._ramal_profile.cargo
                self.fields["setor"].initial = self._ramal_profile.setor
                if self._ramal_profile.superior:
                    self.fields["superior_usuario"].initial = self._ramal_profile.superior.usuario_id
                self.fields["bio"].initial = self._ramal_profile.bio
                self.fields["jornada_horas_semanais"].initial = self._ramal_profile.jornada_horas_semanais
                self.fields["horario_trabalho_inicio"].initial = self._ramal_profile.horario_trabalho_inicio
                self.fields["horario_trabalho_fim"].initial = self._ramal_profile.horario_trabalho_fim
                self.fields["intervalo_inicio"].initial = self._ramal_profile.intervalo_inicio
                self.fields["intervalo_fim"].initial = self._ramal_profile.intervalo_fim
                self.fields["rg"].initial = self._ramal_profile.rg
                self.fields["regime_plantao"].initial = self._ramal_profile.regime_plantao
                self.fields["horario_estudante"].initial = self._ramal_profile.horario_estudante
            memberships = list(
                UserSetorMembership.objects.filter(user=self.instance)
                .select_related("setor")
                .values_list("setor_id", flat=True)
            )
            if not memberships:
                memberships = list(
                    SetorNode.objects.filter(group__in=self.instance.groups.exclude(name=ADMIN_GROUP_NAME))
                    .values_list("id", flat=True)
                )
            self.fields["setores_acesso"].initial = memberships

        can_edit_folha_fields = bool(
            self.current_user
            and (
                self.current_user.is_superuser
                or self.current_user.has_perm("folha_ponto.change_feriado")
                or self.current_user.has_perm("folha_ponto.change_feriasservidor")
            )
        )
        if not can_edit_folha_fields:
            for field_name in [
                "jornada_horas_semanais",
                "horario_trabalho_inicio",
                "horario_trabalho_fim",
                "intervalo_inicio",
                "intervalo_fim",
                "regime_plantao",
                "horario_estudante",
            ]:
                self.fields[field_name].disabled = True

    def apply_profiles(self, user: User):
        """
        Aplica permissões efetivas ao usuário conforme perfis selecionados.

        Parâmetros:
        - `user`: instância de `auth.User` já persistida.

        Regras de negócio:
        - substitui permissões diretas do usuário pelo conjunto calculado;
        - alterna pertencimento ao grupo ADMIN conforme checkbox `admin`.
        """
        perfis = self.cleaned_data.get("perfis") or []
        profile_perm_ids = get_profile_permission_ids_map()
        final_perm_ids = set()
        for profile_name in perfis:
            final_perm_ids.update(profile_perm_ids.get(profile_name, set()))
        perms = Permission.objects.filter(id__in=final_perm_ids)
        user.user_permissions.set(perms)

        admin_group, _created = Group.objects.get_or_create(name=ADMIN_GROUP_NAME)
        if self.cleaned_data.get("admin"):
            user.groups.add(admin_group)
        else:
            user.groups.remove(admin_group)

    def save_ramal(self, user: User):
        """
        Cria/atualiza o perfil `PessoaRamal` associado ao usuário.

        Integração externa:
        - persiste dados no app `ramais`, incluindo relação com superior.

        Regra de negócio:
        - campos de folha são salvos somente quando o operador atual possui
          permissões de edição correspondentes.
        """
        profile, _created = PessoaRamal.objects.get_or_create(usuario=user)
        profile.cargo = self.cleaned_data.get("cargo", "")
        profile.setor = self.cleaned_data.get("setor", "")
        profile.ramal = self.cleaned_data.get("ramal", "")
        profile.bio = self.cleaned_data.get("bio", "")
        profile.rg = self.cleaned_data.get("rg", "")
        can_edit_folha_fields = bool(
            self.current_user
            and (
                self.current_user.is_superuser
                or self.current_user.has_perm("folha_ponto.change_feriado")
                or self.current_user.has_perm("folha_ponto.change_feriasservidor")
            )
        )
        if can_edit_folha_fields:
            profile.jornada_horas_semanais = self.cleaned_data.get("jornada_horas_semanais")
            profile.horario_trabalho_inicio = self.cleaned_data.get("horario_trabalho_inicio")
            profile.horario_trabalho_fim = self.cleaned_data.get("horario_trabalho_fim")
            profile.intervalo_inicio = self.cleaned_data.get("intervalo_inicio")
            profile.intervalo_fim = self.cleaned_data.get("intervalo_fim")
            profile.regime_plantao = self.cleaned_data.get("regime_plantao")
            profile.horario_estudante = self.cleaned_data.get("horario_estudante")
        superior_user = self.cleaned_data.get("superior_usuario")
        profile.superior = PessoaRamal.objects.filter(usuario=superior_user).first() if superior_user else None
        foto = self.cleaned_data.get("foto")
        if foto is not None:
            profile.foto = foto
        profile.save()
        if user:
            from .models import UserAccessState

            state, _created = UserAccessState.objects.get_or_create(user=user)
            if state.force_profile_update:
                state.force_profile_update = False
                state.save(update_fields=["force_profile_update", "updated_at"])

    def save_setor_memberships(self, user: User):
        """
        Sincroniza vínculo de acesso do usuário com setores selecionados.

        Regra de negócio:
        - memberships (`UserSetorMembership`) viram fonte canônica;
        - vínculo legado em `auth.Group` é mantido em paralelo para compatibilidade.
        """
        setores = list(self.cleaned_data.get("setores_acesso") or [])
        setor_principal_nome = (self.cleaned_data.get("setor") or "").strip()
        if setor_principal_nome:
            setor_principal = (
                SetorNode.objects.select_related("group")
                .filter(group__name__iexact=setor_principal_nome)
                .first()
            )
            if setor_principal and setor_principal.id not in [setor.id for setor in setores]:
                setores.append(setor_principal)
        setor_ids = [setor.id for setor in setores]
        with transaction.atomic():
            UserSetorMembership.objects.filter(user=user).exclude(setor_id__in=setor_ids).delete()
            existentes = set(
                UserSetorMembership.objects.filter(user=user, setor_id__in=setor_ids).values_list(
                    "setor_id", flat=True
                )
            )
            UserSetorMembership.objects.bulk_create(
                [
                    UserSetorMembership(user=user, setor=setor)
                    for setor in setores
                    if setor.id not in existentes
                ],
                ignore_conflicts=True,
            )

            admin_group = Group.objects.filter(name=ADMIN_GROUP_NAME).first()
            setor_group_ids = set(SetorNode.objects.values_list("group_id", flat=True))
            final_group_ids = set(user.groups.exclude(id__in=setor_group_ids).values_list("id", flat=True))
            final_group_ids.update(setor.group_id for setor in setores if setor.group_id)
            if self.cleaned_data.get("admin") and admin_group:
                final_group_ids.add(admin_group.id)
            if not self.cleaned_data.get("admin") and admin_group and admin_group.id in final_group_ids:
                final_group_ids.remove(admin_group.id)
            user.groups.set(Group.objects.filter(id__in=final_group_ids))

    def clean_foto(self):
        """Exige foto no cadastro e para perfis que ainda não possuem imagem."""

        foto = self.cleaned_data.get("foto")
        if foto is not None:
            return foto

        profile = getattr(self, "_ramal_profile", None)
        if profile and getattr(profile, "foto", None):
            return profile.foto
        raise forms.ValidationError("A foto é obrigatória.")


class UsuarioCreateForm(UsuarioBaseForm):
    """
    Formulário de criação de usuário com senha obrigatória.
    """

    password = forms.CharField(
        label="Senha",
        widget=forms.PasswordInput(attrs={"class": "form-control"}),
    )


class UsuarioUpdateForm(UsuarioBaseForm):
    """
    Formulário de edição de usuário com senha opcional.

    Regra de negócio:
    - senha em branco mantém credencial atual.
    """

    password = forms.CharField(
        label="Senha",
        required=False,
        widget=forms.PasswordInput(attrs={"class": "form-control"}),
    )


class GrupoBaseForm(forms.ModelForm):
    """
    Formulário base de grupos para gerenciar membros e perfis de acesso.
    """

    perfis = forms.MultipleChoiceField(
        label="Perfis de acesso",
        required=False,
        choices=_profile_choices(),
        widget=forms.CheckboxSelectMultiple,
    )
    usuarios = UsuarioGrupoChoiceField(
        label="Usuarios do setor",
        required=False,
        queryset=User.objects.none(),
        widget=forms.SelectMultiple(attrs={"class": "form-control", "size": 14}),
    )
    parent = forms.ModelChoiceField(
        label="Setor pai",
        required=False,
        queryset=SetorNode.objects.none(),
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    allow_permissions = forms.ModelMultipleChoiceField(
        label="Permissoes allow do setor",
        required=False,
        queryset=Permission.objects.none(),
        widget=forms.SelectMultiple(attrs={"class": "form-control", "size": 10}),
    )
    deny_permissions = forms.ModelMultipleChoiceField(
        label="Permissoes deny do setor",
        required=False,
        queryset=Permission.objects.none(),
        widget=forms.SelectMultiple(attrs={"class": "form-control", "size": 10}),
    )

    class Meta:
        model = Group
        fields = ["name"]
        labels = {"name": "Nome do setor"}
        widgets = {
            "name": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Ex.: RH - Gestores"}
            )
        }

    def __init__(self, *args, **kwargs):
        """
        Inicializa formulário com usuários e perfis atuais do grupo.
        """
        self.inherited_profile_names = set(kwargs.pop("inherited_profile_names", []) or [])
        super().__init__(*args, **kwargs)
        ensure_profiles()
        self.fields["parent"].queryset = SetorNode.objects.select_related("group").order_by("group__name")
        self.fields["allow_permissions"].queryset = Permission.objects.select_related("content_type").order_by(
            "content_type__app_label", "codename"
        )
        self.fields["deny_permissions"].queryset = Permission.objects.select_related("content_type").order_by(
            "content_type__app_label", "codename"
        )
        for field in self.fields.values():
            field.help_text = ""
        self.fields["usuarios"].queryset = usuarios_visiveis(
            User.objects.order_by("first_name", "last_name", "username")
        )

        if self.instance and self.instance.pk:
            setor_node = ensure_setor_node_for_group(self.instance)
            self.fields["usuarios"].initial = list(
                UserSetorMembership.objects.filter(setor=setor_node).values_list("user_id", flat=True)
            )
            self.fields["perfis"].initial = self._infer_initial_profiles()
            self.fields["parent"].initial = setor_node.parent_id
            self.fields["allow_permissions"].initial = list(
                SetorGrant.objects.filter(setor=setor_node, effect=GrantEffect.ALLOW).values_list(
                    "permission_id", flat=True
                )
            )
            self.fields["deny_permissions"].initial = list(
                SetorGrant.objects.filter(setor=setor_node, effect=GrantEffect.DENY).values_list(
                    "permission_id", flat=True
                )
            )

    def clean_name(self):
        """
        Impede renomear o grupo ADMIN para preservar convenção do sistema.
        """
        name = (self.cleaned_data.get("name") or "").strip()
        if self.instance and self.instance.pk and self.instance.name == ADMIN_GROUP_NAME:
            if name != ADMIN_GROUP_NAME:
                raise forms.ValidationError("O setor ADMIN nao pode ser renomeado.")
        return name

    def clean(self):
        cleaned_data = super().clean()
        inherited = set(self.inherited_profile_names)
        if inherited:
            selected_profiles = [profile for profile in (cleaned_data.get("perfis") or []) if profile not in inherited]
            cleaned_data["perfis"] = selected_profiles
        allow_permissions = set(cleaned_data.get("allow_permissions") or [])
        deny_permissions = set(cleaned_data.get("deny_permissions") or [])
        duplicated = allow_permissions.intersection(deny_permissions)
        if duplicated:
            nomes = ", ".join(sorted(perm.codename for perm in duplicated))
            raise forms.ValidationError(
                f"As permissoes nao podem estar simultaneamente em allow e deny: {nomes}."
            )
        parent = cleaned_data.get("parent")
        if parent and self.instance and self.instance.pk:
            setor_node = ensure_setor_node_for_group(self.instance)
            if parent.pk == setor_node.pk:
                self.add_error("parent", "Um setor nao pode ser pai de si mesmo.")
        return cleaned_data

    def _infer_initial_profiles(self):
        """
        Infere perfis selecionados a partir das permissões atuais do grupo.
        """
        profile_perm_ids = get_profile_permission_ids_map()
        current_perm_ids = set(self.instance.permissions.values_list("id", flat=True))
        initial = []
        for profile_name, required_perm_ids in profile_perm_ids.items():
            if required_perm_ids and required_perm_ids.issubset(current_perm_ids):
                initial.append(profile_name)
        return initial

    def save_membership_and_permissions(self, group: Group):
        """
        Sincroniza membros e permissões efetivas do grupo.

        Regras de negócio:
        - grupo ADMIN recebe todas as permissões (`Permission.objects.all()`);
        - demais grupos recebem permissões derivadas dos perfis selecionados.
        """
        selected_users = list(self.cleaned_data.get("usuarios") or [])
        selected_parent = self.cleaned_data.get("parent")
        allow_permissions = list(self.cleaned_data.get("allow_permissions") or [])
        deny_permissions = list(self.cleaned_data.get("deny_permissions") or [])

        with transaction.atomic():
            setor_node = ensure_setor_node_for_group(group)
            setor_node.parent = selected_parent
            setor_node.full_clean()
            setor_node.save()

            selected_user_ids = [user.id for user in selected_users]
            UserSetorMembership.objects.filter(setor=setor_node).exclude(user_id__in=selected_user_ids).delete()
            existing_member_ids = set(
                UserSetorMembership.objects.filter(setor=setor_node, user_id__in=selected_user_ids).values_list(
                    "user_id", flat=True
                )
            )
            UserSetorMembership.objects.bulk_create(
                [
                    UserSetorMembership(user=user, setor=setor_node)
                    for user in selected_users
                    if user.id not in existing_member_ids
                ],
                ignore_conflicts=True,
            )
            # Compatibilidade com consultas legadas que usam Group.user_set.
            group.user_set.set(selected_users)

            if group.name == ADMIN_GROUP_NAME:
                group.permissions.set(Permission.objects.all())
                SetorGrant.objects.filter(setor=setor_node).delete()
                return

            selected_profiles = self.cleaned_data.get("perfis") or []
            profile_perm_ids = get_profile_permission_ids_map()
            final_perm_ids = set()
            for profile_name in selected_profiles:
                final_perm_ids.update(profile_perm_ids.get(profile_name, set()))
            group.permissions.set(final_perm_ids)

            # Espelha permissões efetivas do grupo em grants de setor para habilitar
            # herança hierárquica pelo backend customizado.
            group_perm_ids = set(group.permissions.values_list("id", flat=True))
            manual_allow_ids = {perm.id for perm in allow_permissions}
            deny_perm_ids = {perm.id for perm in deny_permissions}
            allow_ids = (group_perm_ids | manual_allow_ids) - deny_perm_ids

            SetorGrant.objects.filter(setor=setor_node).delete()
            SetorGrant.objects.bulk_create(
                [SetorGrant(setor=setor_node, permission_id=perm_id, effect=GrantEffect.ALLOW) for perm_id in allow_ids]
                + [SetorGrant(setor=setor_node, permission_id=perm_id, effect=GrantEffect.DENY) for perm_id in deny_perm_ids],
                ignore_conflicts=True,
            )


class GrupoCreateForm(GrupoBaseForm):
    """
    Formulário de criação de grupo (especialização sem regras extras).
    """

    pass


class GrupoUpdateForm(GrupoBaseForm):
    """
    Formulário de edição de grupo (especialização sem regras extras).
    """

    pass

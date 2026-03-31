"""
Testes automatizados do app `usuarios`.

Este módulo valida regras de negócio críticas implementadas por sinais:
- concessão de permissões padrão de reserva de salas ao criar usuário;
- sincronização de `is_staff`/`is_superuser` conforme mudanças no grupo ADMIN.
"""

from django.contrib.auth.models import Group, Permission, User
from django.test import RequestFactory, TestCase
from unittest.mock import patch

from ramais.models import PessoaRamal

from .forms import GrupoUpdateForm, UsuarioUpdateForm
from .models import GrantEffect, SetorGrant, SetorNode, UserGrant, UserSetorMembership
from .permissions import ADMIN_GROUP_NAME
from .signals import RESERVA_SALAS_DEFAULT_CODENAMES
from .views import UsuarioListView, _compute_inherited_profile_names_for_group


class UsuarioSignalsTests(TestCase):
    """
    Cenários de regressão para sinais de usuário e grupo.
    """

    def test_novo_usuario_recebe_permissoes_padrao_reserva_salas(self):
        """
        Garante que criação de usuário conceda permissões mínimas esperadas.
        """
        user = User.objects.create_user(username="novo_usuario", password="senha123")
        user_perm_codenames = set(user.user_permissions.values_list("codename", flat=True))
        for codename in RESERVA_SALAS_DEFAULT_CODENAMES:
            self.assertIn(codename, user_perm_codenames)

    def test_usuario_existente_nao_recebe_permissoes_automaticamente_em_update(self):
        """
        Garante que atualização de usuário existente não reaplique permissões default.
        """
        user = User.objects.create_user(username="usuario_update", password="senha123")
        user.user_permissions.clear()
        user.first_name = "Atualizado"
        user.save(update_fields=["first_name"])
        user_perm_codenames = set(user.user_permissions.values_list("codename", flat=True))
        for codename in RESERVA_SALAS_DEFAULT_CODENAMES:
            self.assertNotIn(codename, user_perm_codenames)

    def test_group_user_set_add_synca_flags_admin(self):
        """
        Garante que incluir usuário no grupo ADMIN habilite flags administrativas.
        """
        admin_group, _created = Group.objects.get_or_create(name=ADMIN_GROUP_NAME)
        user = User.objects.create_user(username="grupo_set_add", password="senha123")
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

        admin_group.user_set.set([user])
        user.refresh_from_db()

        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)

    def test_group_user_set_clear_synca_flags_admin(self):
        """
        Garante que remover usuário do grupo ADMIN desabilite flags administrativas.
        """
        admin_group, _created = Group.objects.get_or_create(name=ADMIN_GROUP_NAME)
        user = User.objects.create_user(username="grupo_set_clear", password="senha123")
        admin_group.user_set.set([user])
        user.refresh_from_db()
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)

        admin_group.user_set.clear()
        user.refresh_from_db()
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)


class UsuarioListViewTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.admin = User.objects.create_user(
            username="admin_lista",
            password="senha123",
            is_staff=True,
        )
        self.setor_ti = Group.objects.create(name="Tecnologia")
        self.setor_rh = Group.objects.create(name="RH")

        self.user_ti = User.objects.create_user(
            username="joao.ti",
            password="senha123",
            first_name="Joao",
            last_name="Silva",
            email="joao.ti@example.com",
        )
        self.user_ti.groups.add(self.setor_ti)

        self.user_rh = User.objects.create_user(
            username="maria.rh",
            password="senha123",
            first_name="Maria",
            last_name="Souza",
            email="maria.rh@example.com",
        )
        self.user_rh.groups.add(self.setor_rh)

        self.superuser = User.objects.create_user(
            username="super.admin",
            password="senha123",
            first_name="Super",
            email="super.admin@example.com",
            is_superuser=True,
        )
        self.tmp_user = User.objects.create_user(
            username="tmpnota",
            password="senha123",
            first_name="Tmp",
            email="tmp@example.com",
        )

    def _get_queryset(self, params=None):
        request = self.factory.get("/usuarios/", data=params or {})
        request.user = self.admin
        view = UsuarioListView()
        view.request = request
        return view.get_queryset()

    def test_filtro_por_nome_consulta_queryset_completo(self):
        queryset = self._get_queryset({"nome": "Maria"})

        self.assertQuerySetEqual(queryset, [self.user_rh], transform=lambda user: user)

    def test_filtro_por_setor_encontra_grupo_no_banco(self):
        queryset = self._get_queryset({"setor": "Tecnologia"})

        self.assertQuerySetEqual(queryset, [self.user_ti], transform=lambda user: user)

    def test_busca_por_admin_inclui_superusuario(self):
        queryset = self._get_queryset({"setor": "Admin"})

        self.assertIn(self.superuser, queryset)

    def test_ordenacao_por_nome_usa_queryset_completo(self):
        queryset = list(self._get_queryset({"sort": "nome", "dir": "asc"}))

        self.assertLess(queryset.index(self.user_ti), queryset.index(self.user_rh))
        self.assertLess(queryset.index(self.user_rh), queryset.index(self.superuser))

    def test_ordenacao_por_email_desc_usa_banco_todo(self):
        queryset = self._get_queryset({"sort": "email", "dir": "desc"})

        self.assertEqual(list(queryset[:3]), [self.superuser, self.user_rh, self.user_ti])

    def test_lista_de_usuarios_oculta_contas_tecnicas_tmp_e_smoke(self):
        queryset = self._get_queryset()

        self.assertNotIn(self.tmp_user, queryset)


class UsuariosOcultosFormsTests(TestCase):
    def test_formulario_de_usuario_exibe_perfil_acompanhamento_de_sistemas(self):
        usuario_editado = User.objects.create_user(username="usuario_perfis", password="senha123", first_name="Perfis")

        form = UsuarioUpdateForm(instance=usuario_editado)
        labels = [label for _value, label in form.fields["perfis"].choices]

        self.assertTrue(
            any(label.startswith("Acompanhamento de Sistemas - ") for label in labels)
        )

    def test_formulario_de_usuario_nao_lista_superior_tecnico(self):
        usuario_editado = User.objects.create_user(username="usuario_editado", password="senha123", first_name="Editado")
        visivel = User.objects.create_user(username="usuario_comum", password="senha123", first_name="Usuario")
        oculto = User.objects.create_user(username="tmpuser", password="senha123", first_name="Tmp")

        form = UsuarioUpdateForm(instance=usuario_editado)

        self.assertIn(visivel, form.fields["superior_usuario"].queryset)
        self.assertNotIn(oculto, form.fields["superior_usuario"].queryset)

    def test_formulario_de_grupo_nao_lista_usuario_tecnico(self):
        visivel = User.objects.create_user(username="grupo_visivel", password="senha123", first_name="Grupo")
        oculto = User.objects.create_user(username="smokev2", password="senha123", first_name="Smoke")
        group = Group.objects.create(name="Grupo Teste")

        form = GrupoUpdateForm(instance=group)

        self.assertIn(visivel, form.fields["usuarios"].queryset)
        self.assertNotIn(oculto, form.fields["usuarios"].queryset)


class SetorPermissionBackendTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="setor_teste", password="senha123")
        self.pai_group = Group.objects.create(name="Pai")
        self.filho_group = Group.objects.create(name="Filho")
        self.pai = SetorNode.objects.create(group=self.pai_group)
        self.filho = SetorNode.objects.create(group=self.filho_group, parent=self.pai)
        UserSetorMembership.objects.create(user=self.user, setor=self.filho)
        self.permission = Permission.objects.filter(
            content_type__app_label="auth",
            codename="view_user",
        ).first()

    def test_allow_herdado_do_pai_concede_permissao(self):
        SetorGrant.objects.create(setor=self.pai, permission=self.permission, effect=GrantEffect.ALLOW)
        self.assertTrue(self.user.has_perm("auth.view_user"))

    def test_deny_no_filho_bloqueia_allow_herdado(self):
        SetorGrant.objects.create(setor=self.pai, permission=self.permission, effect=GrantEffect.ALLOW)
        SetorGrant.objects.create(setor=self.filho, permission=self.permission, effect=GrantEffect.DENY)
        self.assertFalse(self.user.has_perm("auth.view_user"))

    def test_deny_direto_no_usuario_bloqueia_tudo(self):
        SetorGrant.objects.create(setor=self.pai, permission=self.permission, effect=GrantEffect.ALLOW)
        UserGrant.objects.create(user=self.user, permission=self.permission, effect=GrantEffect.DENY)
        self.assertFalse(self.user.has_perm("auth.view_user"))


class GrupoFormMirrorGrantsTests(TestCase):
    def setUp(self):
        self.group = Group.objects.create(name="Grupo Espelho")
        self.permission = Permission.objects.filter(
            content_type__app_label="auth",
            codename="view_user",
        ).first()

    def test_save_espelha_group_permissions_em_setorgrant_allow(self):
        initial_form = GrupoUpdateForm(instance=self.group)
        perfil = initial_form.fields["perfis"].choices[0][0]

        with patch("usuarios.forms.get_profile_permission_ids_map", return_value={perfil: {self.permission.id}}):
            form = GrupoUpdateForm(
                data={
                    "name": self.group.name,
                    "usuarios": [],
                    "perfis": [perfil],
                    "parent": "",
                    "allow_permissions": [],
                    "deny_permissions": [],
                },
                instance=self.group,
            )
            self.assertTrue(form.is_valid(), form.errors)
            form.save_membership_and_permissions(self.group)

        setor = SetorNode.objects.get(group=self.group)
        self.assertTrue(self.group.permissions.filter(id=self.permission.id).exists())
        self.assertTrue(
            SetorGrant.objects.filter(
                setor=setor,
                permission=self.permission,
                effect=GrantEffect.ALLOW,
            ).exists()
        )

    def test_deny_explicito_remove_allow_espelhado(self):
        initial_form = GrupoUpdateForm(instance=self.group)
        perfil = initial_form.fields["perfis"].choices[0][0]

        with patch("usuarios.forms.get_profile_permission_ids_map", return_value={perfil: {self.permission.id}}):
            form = GrupoUpdateForm(
                data={
                    "name": self.group.name,
                    "usuarios": [],
                    "perfis": [perfil],
                    "parent": "",
                    "allow_permissions": [],
                    "deny_permissions": [str(self.permission.id)],
                },
                instance=self.group,
            )
            self.assertTrue(form.is_valid(), form.errors)
            form.save_membership_and_permissions(self.group)

        setor = SetorNode.objects.get(group=self.group)
        self.assertFalse(
            SetorGrant.objects.filter(
                setor=setor,
                permission=self.permission,
                effect=GrantEffect.ALLOW,
            ).exists()
        )
        self.assertTrue(
            SetorGrant.objects.filter(
                setor=setor,
                permission=self.permission,
                effect=GrantEffect.DENY,
            ).exists()
        )

    def test_perfil_herdado_enviado_no_post_e_ignorado_como_direto(self):
        grupo = Group.objects.create(name="Filho Heranca")
        SetorNode.objects.create(group=grupo)

        initial_form = GrupoUpdateForm(instance=grupo)
        perfil = initial_form.fields["perfis"].choices[0][0]

        with patch("usuarios.forms.get_profile_permission_ids_map", return_value={perfil: {self.permission.id}}):
            form = GrupoUpdateForm(
                data={
                    "name": grupo.name,
                    "usuarios": [],
                    "perfis": [perfil],
                    "parent": "",
                    "allow_permissions": [],
                    "deny_permissions": [],
                },
                instance=grupo,
                inherited_profile_names={perfil},
            )
            self.assertTrue(form.is_valid(), form.errors)
            form.save_membership_and_permissions(grupo)

        self.assertFalse(
            grupo.permissions.filter(id=self.permission.id).exists(),
            "Perfil herdado nao deve virar permissao direta do grupo filho.",
        )

    def test_compute_inherited_profile_names_usando_grants_do_pai(self):
        perfil = "Perfil Herdado Teste"
        pai_group = Group.objects.create(name="Pai Heranca 2")
        filho_group = Group.objects.create(name="Filho Heranca 2")
        pai = SetorNode.objects.create(group=pai_group)
        SetorNode.objects.create(group=filho_group, parent=pai)
        SetorGrant.objects.create(setor=pai, permission=self.permission, effect=GrantEffect.ALLOW)

        with patch("usuarios.views.get_profile_permission_ids_map", return_value={perfil: {self.permission.id}}):
            inherited_profiles = _compute_inherited_profile_names_for_group(filho_group)

        self.assertIn(perfil, inherited_profiles)


class UsuarioFormFotoObrigatoriaTests(TestCase):
    def test_usuario_update_exige_foto_quando_perfil_nao_tem_imagem(self):
        user = User.objects.create_user(
            username="usuario_foto",
            password="senha123",
            first_name="Usuario Foto",
            email="usuario.foto@exemplo.gov.br",
        )
        group = Group.objects.create(name="Financeiro")
        SetorNode.objects.create(group=group)
        PessoaRamal.objects.create(
            usuario=user,
            nome="Usuario Foto",
            cargo="Analista",
            setor="Financeiro",
            ramal="1234",
            email="usuario.foto@exemplo.gov.br",
        )

        form = UsuarioUpdateForm(
            data={
                "first_name": "Usuario Foto",
                "username": "usuario_foto",
                "email": "usuario.foto@exemplo.gov.br",
                "ramal": "1234",
                "cargo": "Analista",
                "setor": "Financeiro",
            },
            instance=user,
            current_user=user,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("foto", form.errors)

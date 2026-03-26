"""
Suite de testes do app `ramais`.

Este módulo é o ponto de entrada para cenários automatizados de regras de
negócio, persistência e fluxos HTTP relacionados ao diretório de ramais.
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import RequestFactory, TestCase

from intranet.context_processors import ramal_profile
from usuarios.models import SetorNode, UserSetorMembership
from usuarios.permissions import ADMIN_GROUP_NAME

from .forms import PessoaRamalForm
from .models import PessoaRamal
from .views import PessoaRamalListView


class PessoaRamalSetorAcessoSyncTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="ramal_sync", password="123456")
        self.grupo_setor = Group.objects.create(name="Assessoria Técnica de Gabinete")
        self.setor_node = SetorNode.objects.create(group=self.grupo_setor)

    def test_setor_principal_cria_setor_acesso_quando_usuario_nao_tem_vinculos(self):
        perfil = PessoaRamal.objects.create(
            usuario=self.user,
            nome="Usuário Teste",
            cargo="Analista",
            setor="Assessoria Técnica de Gabinete",
            ramal="1234",
            email="ramal_sync@exemplo.gov.br",
        )

        self.assertTrue(
            UserSetorMembership.objects.filter(user=self.user, setor=self.setor_node).exists()
        )
        self.assertTrue(self.user.groups.filter(pk=self.grupo_setor.pk).exists())
        self.assertEqual(perfil.setor, "Assessoria Técnica de Gabinete")

    def test_nao_substitui_setor_acesso_quando_usuario_ja_possui_vinculo(self):
        outro_grupo = Group.objects.create(name="Chefia de Gabinete")
        outro_setor = SetorNode.objects.create(group=outro_grupo)
        UserSetorMembership.objects.create(user=self.user, setor=outro_setor)

        PessoaRamal.objects.create(
            usuario=self.user,
            nome="Usuário Teste",
            cargo="Analista",
            setor="Assessoria Técnica de Gabinete",
            ramal="1234",
            email="ramal_sync@exemplo.gov.br",
        )

        self.assertTrue(UserSetorMembership.objects.filter(user=self.user, setor=outro_setor).exists())
        self.assertFalse(UserSetorMembership.objects.filter(user=self.user, setor=self.setor_node).exists())


class PessoaRamalFormTests(TestCase):
    def test_campo_setor_nao_lista_grupo_admin(self):
        admin_group, _created = Group.objects.get_or_create(name=ADMIN_GROUP_NAME)
        financeiro_group, _created = Group.objects.get_or_create(name="Financeiro")
        SetorNode.objects.get_or_create(group=admin_group)
        SetorNode.objects.get_or_create(group=financeiro_group)

        form = PessoaRamalForm()

        choices = [value for value, _label in form.fields["setor"].choices]
        self.assertIn("Financeiro", choices)
        self.assertNotIn(ADMIN_GROUP_NAME, choices)

    def test_campo_setor_comeca_em_branco_no_formulario(self):
        financeiro_group, _created = Group.objects.get_or_create(name="Financeiro")
        SetorNode.objects.get_or_create(group=financeiro_group)
        perfil = PessoaRamal.objects.create(
            nome="Usuario Teste",
            cargo="Analista",
            setor="Financeiro",
            ramal="1000",
            email="usuario.teste@exemplo.gov.br",
        )

        form = PessoaRamalForm(instance=perfil)

        self.assertEqual(form.fields["setor"].initial, "")
        self.assertIn(("", "Selecione um setor"), form.fields["setor"].choices)

    def test_nao_permite_salvar_sem_setor(self):
        financeiro_group, _created = Group.objects.get_or_create(name="Financeiro")
        SetorNode.objects.get_or_create(group=financeiro_group)

        form = PessoaRamalForm(data={"setor": ""})

        self.assertFalse(form.is_valid())
        self.assertIn("setor", form.errors)

    def test_nao_permite_salvar_sem_foto(self):
        financeiro_group, _created = Group.objects.get_or_create(name="Financeiro")
        SetorNode.objects.get_or_create(group=financeiro_group)

        form = PessoaRamalForm(data={"setor": "Financeiro"})

        self.assertFalse(form.is_valid())
        self.assertIn("foto", form.errors)


class PessoaRamalAdminExclusionTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.admin_user = get_user_model().objects.create_user(username="admin", password="123456")
        self.admin_profile = PessoaRamal.objects.create(
            usuario=self.admin_user,
            nome="Administrador do SGI",
            cargo="Administrador",
            setor="Tecnologia",
            ramal="9999",
            email="admin@exemplo.gov.br",
        )
        self.common_user = get_user_model().objects.create_user(username="maria", password="123456")
        self.common_profile = PessoaRamal.objects.create(
            usuario=self.common_user,
            nome="Maria Silva",
            cargo="Analista",
            setor="Financeiro",
            ramal="1234",
            email="maria@exemplo.gov.br",
        )

    def test_usuario_admin_nao_exige_atualizacao_de_ramal(self):
        request = self.factory.get("/")
        request.user = self.admin_user

        context = ramal_profile(request)

        self.assertFalse(context["ramal_profile_requires_update"])
        self.assertFalse(context["ramal_missing_fields"])
        self.assertIsNone(context["ramal_profile"])

    def test_usuario_admin_nao_aparece_na_lista_de_ramais(self):
        request = self.factory.get("/ramais/")
        request.user = self.common_user
        view = PessoaRamalListView()
        view.request = request

        queryset = list(view.get_queryset())

        self.assertNotIn(self.admin_profile, queryset)
        self.assertIn(self.common_profile, queryset)

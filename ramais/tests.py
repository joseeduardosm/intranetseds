"""
Suite de testes do app `ramais`.

Este módulo é o ponto de entrada para cenários automatizados de regras de
negócio, persistência e fluxos HTTP relacionados ao diretório de ramais.
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase

from usuarios.models import SetorNode, UserSetorMembership

from .models import PessoaRamal


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

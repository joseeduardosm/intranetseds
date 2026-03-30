"""
Suite de testes do app `noticias`.

Este módulo é o ponto de entrada para testes automatizados do domínio de
notícias (modelos, fluxos HTTP e permissões). Mesmo estando minimalista no
momento, ele integra com o runner de testes do Django para evolução contínua.
"""
from django.test import Client, TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission

from .models import Noticia
from .views import NoticiaCreateView, NoticiaDeleteView, NoticiaUpdateView

# Espaço para testes automatizados do app de notícias.


class LoginViewCsrfTests(TestCase):
    """
    Regressões do fluxo de login renderizado a partir da home/base.
    """

    def test_login_page_define_cookie_csrf_e_headers_sem_cache(self):
        client = Client(enforce_csrf_checks=True)

        response = client.get(reverse("login"))

        self.assertEqual(response.status_code, 200)
        self.assertIn("csrftoken", response.cookies)
        self.assertIn("csrfmiddlewaretoken", response.content.decode())
        self.assertIn("no-cache", response.headers.get("Cache-Control", ""))


class NoticiasRoutingTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="noticias",
            email="noticias@exemplo.gov.br",
            password="123456",
        )
        self.user.user_permissions.add(
            Permission.objects.get(codename="add_noticia"),
            Permission.objects.get(codename="change_noticia"),
            Permission.objects.get(codename="delete_noticia"),
        )

    def test_listagem_de_noticias_fica_em_rota_explicita(self):
        response = self.client.get(reverse("noticia_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Noticias")

    def test_crud_redireciona_para_listagem_de_noticias(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("noticia_create"),
            data={
                "titulo": "Nova noticia",
                "texto": "Conteudo",
                "data_publicacao": "2026-03-30",
                "categoria": "Comunicado",
            },
        )

        self.assertRedirects(response, reverse("noticia_list"))
        noticia = Noticia.objects.get(titulo="Nova noticia")
        self.assertEqual(NoticiaCreateView.success_url, reverse("noticia_list"))
        self.assertEqual(NoticiaUpdateView.success_url, reverse("noticia_list"))
        self.assertEqual(NoticiaDeleteView.success_url, reverse("noticia_list"))

        response = self.client.post(
            reverse("noticia_update", args=[noticia.pk]),
            data={
                "titulo": "Nova noticia atualizada",
                "texto": "Conteudo atualizado",
                "data_publicacao": "2026-03-30",
                "categoria": "Comunicado",
            },
        )
        self.assertRedirects(response, reverse("noticia_list"))

        response = self.client.post(reverse("noticia_delete", args=[noticia.pk]))
        self.assertRedirects(response, reverse("noticia_list"))

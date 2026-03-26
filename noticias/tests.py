"""
Suite de testes do app `noticias`.

Este módulo é o ponto de entrada para testes automatizados do domínio de
notícias (modelos, fluxos HTTP e permissões). Mesmo estando minimalista no
momento, ele integra com o runner de testes do Django para evolução contínua.
"""
from django.test import Client, TestCase
from django.urls import reverse

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

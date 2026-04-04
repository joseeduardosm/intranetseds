import json

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import DesktopAPIToken, NotificacaoUsuario
from .services import SOURCE_ACOMPANHAMENTO_SISTEMAS, emitir_notificacao


@override_settings(ROOT_URLCONF="intranet.urls")
class NotificacoesDesktopTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="desktop-user",
            password="senha-123",
            email="desktop@example.com",
            first_name="Desktop",
        )
        self.outro = get_user_model().objects.create_user(
            username="desktop-outro",
            password="senha-123",
            email="outro@example.com",
        )

    def _login_api(self):
        response = self.client.post(
            reverse("desktop_api_login"),
            data=json.dumps({"username": "desktop-user", "password": "senha-123"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        return response.json()["token"]

    def test_login_desktop_retorna_token(self):
        response = self.client.post(
            reverse("desktop_api_login"),
            data=json.dumps({"username": "desktop-user", "password": "senha-123"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["token"])
        self.assertEqual(DesktopAPIToken.objects.filter(user=self.user).count(), 1)

    def test_login_desktop_rejeita_credenciais_invalidas(self):
        response = self.client.post(
            reverse("desktop_api_login"),
            data=json.dumps({"username": "desktop-user", "password": "senha-errada"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 401)

    def test_lista_notificacoes_retorna_apenas_usuario_autenticado(self):
        emitir_notificacao(
            users=[self.user],
            source_app=SOURCE_ACOMPANHAMENTO_SISTEMAS,
            event_type="nota_sistema",
            title="Nota 1",
            body_short="Nova nota",
            target_url="/acompanhamento-sistemas/1/",
        )
        emitir_notificacao(
            users=[self.outro],
            source_app=SOURCE_ACOMPANHAMENTO_SISTEMAS,
            event_type="nota_sistema",
            title="Nota 2",
            body_short="Outra nota",
            target_url="/acompanhamento-sistemas/2/",
        )
        token = self._login_api()

        response = self.client.get(
            reverse("desktop_api_notificacoes_list"),
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["results"]), 1)
        self.assertEqual(response.json()["results"][0]["title"], "Nota 1")

    def test_since_id_retorna_apenas_notificacoes_novas(self):
        primeira = emitir_notificacao(
            users=[self.user],
            source_app=SOURCE_ACOMPANHAMENTO_SISTEMAS,
            event_type="publicacao_ciclo",
            title="Primeira",
            body_short="Primeira notificação",
            target_url="/acompanhamento-sistemas/1/",
        )[0]
        emitir_notificacao(
            users=[self.user],
            source_app=SOURCE_ACOMPANHAMENTO_SISTEMAS,
            event_type="publicacao_ciclo",
            title="Segunda",
            body_short="Segunda notificação",
            target_url="/acompanhamento-sistemas/1/",
            dedupe_key="seg",
        )
        token = self._login_api()

        response = self.client.get(
            reverse("desktop_api_notificacoes_list") + f"?since_id={primeira.id}",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["results"]), 1)
        self.assertEqual(response.json()["results"][0]["title"], "Segunda")

    def test_marcar_lida_e_exibida_funcionam_sem_confundir_campos(self):
        item = emitir_notificacao(
            users=[self.user],
            source_app=SOURCE_ACOMPANHAMENTO_SISTEMAS,
            event_type="nota_etapa",
            title="Nova etapa",
            body_short="Comentário",
            target_url="/acompanhamento-sistemas/etapas/1/",
        )[0]
        token = self._login_api()

        exibida = self.client.post(
            reverse("desktop_api_notificacao_marcar_exibida", kwargs={"pk": item.pk}),
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        item.refresh_from_db()
        self.assertEqual(exibida.status_code, 200)
        self.assertIsNotNone(item.displayed_at)
        self.assertIsNone(item.read_at)

        lida = self.client.post(
            reverse("desktop_api_notificacao_marcar_lida", kwargs={"pk": item.pk}),
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        item.refresh_from_db()
        self.assertEqual(lida.status_code, 200)
        self.assertIsNotNone(item.read_at)

    def test_deduplicacao_bloqueia_repeticao_na_janela(self):
        emitir_notificacao(
            users=[self.user],
            source_app=SOURCE_ACOMPANHAMENTO_SISTEMAS,
            event_type="nota_sistema",
            title="Duplicada",
            body_short="Mensagem",
            target_url="/acompanhamento-sistemas/1/",
            dedupe_key="chave-duplicada",
        )
        emitir_notificacao(
            users=[self.user],
            source_app=SOURCE_ACOMPANHAMENTO_SISTEMAS,
            event_type="nota_sistema",
            title="Duplicada",
            body_short="Mensagem",
            target_url="/acompanhamento-sistemas/1/",
            dedupe_key="chave-duplicada",
        )

        self.assertEqual(NotificacaoUsuario.objects.filter(user=self.user).count(), 1)

    def test_marcar_lida_nao_permite_acessar_item_de_outro_usuario(self):
        item = emitir_notificacao(
            users=[self.outro],
            source_app=SOURCE_ACOMPANHAMENTO_SISTEMAS,
            event_type="nota_sistema",
            title="Privada",
            body_short="Mensagem",
            target_url="/acompanhamento-sistemas/1/",
        )[0]
        token = self._login_api()

        response = self.client.post(
            reverse("desktop_api_notificacao_marcar_lida", kwargs={"pk": item.pk}),
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

        self.assertEqual(response.status_code, 404)

    def test_comando_de_simulacao_cria_notificacao_para_usuario(self):
        call_command(
            "simular_notificacao_desktop",
            "desktop-user",
            title="Sistema: Teste",
            body="Ciclo: Exemplo\nEtapa: Requisitos - nota adicionada.\nAutor, 04/04/2026 10:00",
            target_url="/acompanhamento-sistemas/1/",
        )

        notificacao = NotificacaoUsuario.objects.get(user=self.user, event_type="simulacao_manual")
        self.assertEqual(notificacao.title, "Sistema: Teste")
        self.assertIn("Etapa: Requisitos - nota adicionada.", notificacao.body_short)

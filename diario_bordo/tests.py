from datetime import date, datetime
from unittest.mock import patch

from django.contrib.auth.models import Permission
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from .models import BlocoLeitura, BlocoTrabalho, DiarioMarcador, DiarioMarcadorVinculo, Incremento
from .views import _dias_desde
from notificacoes.models import NotificacaoUsuario


class DiasDesdeTests(SimpleTestCase):
    def test_retorna_um_dia_quando_foi_atualizado_ontem_mesmo_com_menos_de_24h(self):
        atualizado_em = timezone.make_aware(datetime(2026, 3, 9, 15, 12))
        with patch("diario_bordo.views.timezone.localdate", return_value=date(2026, 3, 10)):
            self.assertEqual(_dias_desde(atualizado_em), 1)

    def test_retorna_zero_quando_atualizado_no_mesmo_dia(self):
        atualizado_em = timezone.make_aware(datetime(2026, 3, 10, 1, 0))
        with patch("diario_bordo.views.timezone.localdate", return_value=date(2026, 3, 10)):
            self.assertEqual(_dias_desde(atualizado_em), 0)


class BlocoTrabalhoUpdateViewTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.editor = user_model.objects.create_superuser(
            username="editor",
            email="editor@example.com",
            password="senha-forte-123",
        )
        self.participante_antigo = user_model.objects.create_user(
            username="participante_antigo",
            first_name="Participante",
            last_name="Antigo",
        )
        self.participante_novo = user_model.objects.create_user(
            username="participante_novo",
            first_name="Participante",
            last_name="Novo",
        )
        self.marcador_antigo = DiarioMarcador.objects.create(
            nome="Urgente",
            nome_normalizado="urgente",
            cor="#111111",
        )
        self.marcador_novo = DiarioMarcador.objects.create(
            nome="Prioridade Alta",
            nome_normalizado="prioridade alta",
            cor="#222222",
        )
        self.bloco = BlocoTrabalho.objects.create(
            nome="Bloco original",
            descricao="Descricao antiga",
            status=BlocoTrabalho.Status.A_FAZER,
        )
        self.bloco.participantes.add(self.participante_antigo)
        DiarioMarcadorVinculo.objects.create(bloco=self.bloco, marcador=self.marcador_antigo)
        self.client.force_login(self.editor)

    def test_registra_incrementos_com_valores_anteriores_e_novos_ao_editar_bloco(self):
        response = self.client.post(
            reverse("diario_bordo_update", kwargs={"pk": self.bloco.pk}),
            {
                "nome": "Bloco revisado",
                "descricao": "Descricao nova",
                "status": BlocoTrabalho.Status.CONCLUIDO,
                "marcadores_ids": str(self.marcador_novo.pk),
                "participantes": [self.participante_novo.pk],
            },
        )

        self.assertRedirects(response, self.bloco.get_absolute_url())
        textos = list(
            Incremento.objects.filter(bloco=self.bloco)
            .order_by("id")
            .values_list("texto", flat=True)
        )

        self.assertIn("Participante Novo inserido no bloco de trabalho", textos)
        self.assertIn("Participante Antigo removido do bloco de trabalho", textos)
        self.assertIn("Alterou nome de Bloco original para Bloco revisado", textos)
        self.assertIn("Alterou descricao de Descricao antiga para Descricao nova", textos)
        self.assertIn("Alterou status de À Fazer para Concluído", textos)
        self.assertNotIn("Alterou participantes de Participante Antigo para Participante Novo", textos)
        self.assertIn("Alterou marcadores de Urgente para Prioridade Alta", textos)


class DiarioBordoNotificacoesTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.autor = user_model.objects.create_superuser(
            username="autor_diario",
            email="autor@example.com",
            password="senha-forte-123",
        )
        self.participante = user_model.objects.create_user(
            username="participante_diario",
            first_name="Participante",
            last_name="Diario",
            password="senha-forte-123",
        )
        self.bloco = BlocoTrabalho.objects.create(
            nome="Bloco notificacoes",
            descricao="Descricao",
            status=BlocoTrabalho.Status.EM_ANDAMENTO,
        )
        self.bloco.participantes.add(self.autor, self.participante)

    def test_incremento_notifica_participante_e_nao_autor(self):
        self.client.force_login(self.autor)

        response = self.client.post(
            reverse("diario_bordo_incremento_create", kwargs={"pk": self.bloco.pk}),
            {"texto": "Nova atualização operacional"},
        )

        self.assertEqual(response.status_code, 302)
        notificacao = NotificacaoUsuario.objects.get(user=self.participante, source_app="diario_bordo")
        self.assertEqual(notificacao.event_type, "incremento")
        self.assertEqual(notificacao.title, f"Diário de Bordo: {self.bloco.nome}")
        self.assertIn("Incremento: Nova atualização operacional", notificacao.body_short)
        self.assertIn(self.bloco.get_absolute_url(), notificacao.target_url)
        self.assertFalse(NotificacaoUsuario.objects.filter(user=self.autor, source_app="diario_bordo").exists())

    def test_ciencia_notifica_outros_participantes(self):
        incremento = Incremento.objects.create(
            bloco=self.bloco,
            texto="Incremento base",
            criado_por=self.autor,
        )
        self.client.force_login(self.autor)

        response = self.client.post(
            reverse("diario_bordo_incremento_ciente", kwargs={"pk": incremento.pk}),
        )

        self.assertEqual(response.status_code, 302)
        notificacao = NotificacaoUsuario.objects.get(user=self.participante, event_type="ciencia_incremento")
        self.assertEqual(notificacao.title, f"Diário de Bordo: {self.bloco.nome}")
        self.assertIn("Ciência registrada no incremento: Incremento base", notificacao.body_short)

    def test_incremento_marcar_lido_atualiza_cursor_do_bloco(self):
        incremento = Incremento.objects.create(
            bloco=self.bloco,
            texto="Incremento exibido no modal",
            criado_por=self.autor,
        )
        permissao = Permission.objects.get(codename="view_blocotrabalho")
        self.participante.user_permissions.add(permissao)
        self.client.force_login(self.participante)

        response = self.client.post(
            reverse("diario_bordo_incremento_marcar_lido", kwargs={"pk": incremento.pk}),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        leitura = BlocoLeitura.objects.get(usuario=self.participante, bloco=self.bloco)
        self.assertEqual(leitura.ultimo_incremento_visto_em, incremento.criado_em)

import importlib.util
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Reserva, Sala


class ReservaDashboardViewTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="teste",
            password="senha123",
            first_name="Teste",
            last_name="Usuario",
        )
        self.user_2 = User.objects.create_user(
            username="outro",
            password="senha123",
            first_name="Outro",
            last_name="Usuario",
        )
        self.client.force_login(self.user)
        self.sala_1 = Sala.objects.create(
            nome="Sala Azul",
            capacidade=12,
            localizacao="Andar 1",
        )
        self.sala_2 = Sala.objects.create(
            nome="Sala Verde",
            capacidade=10,
            localizacao="Andar 2",
        )

    def _nova_reserva(self, sala, data, responsavel, registrado_por=None):
        return Reserva.objects.create(
            sala=sala,
            data=data,
            hora_inicio="09:00",
            hora_fim="10:00",
            nome_evento=f"Evento {responsavel}",
            responsavel_evento=responsavel,
            quantidade_pessoas=5,
            registrado_por=registrado_por or self.user,
        )

    def test_dashboard_calcula_cards_e_rankings(self):
        hoje = timezone.localdate()
        ontem = hoje - timedelta(days=1)
        mes_anterior = (hoje.replace(day=1) - timedelta(days=1)).replace(day=10)

        self._nova_reserva(self.sala_1, hoje, "Ana")
        self._nova_reserva(self.sala_1, hoje, "Ana")
        self._nova_reserva(self.sala_2, ontem, "Bruno")
        self._nova_reserva(self.sala_2, mes_anterior, "Carla")
        self._nova_reserva(self.sala_2, hoje, "Dora", registrado_por=self.user_2)

        response = self.client.get(reverse("reservas_dashboard"))
        self.assertEqual(response.status_code, 200)

        self.assertEqual(response.context["total_reunioes_mes"], 4)
        self.assertEqual(response.context["salas_ativas_mes"], 2)
        self.assertEqual(response.context["media_reunioes_por_dia"], 2.0)

        ranking = list(response.context["ranking_pessoas"])
        self.assertEqual(ranking[0]["nome"], "Teste Usuario")
        self.assertIn("ramal", ranking[0])
        self.assertIn("email", ranking[0])
        self.assertEqual(ranking[0]["total"], 4)

    def test_dashboard_exportar_filtra_por_mes(self):
        if importlib.util.find_spec("openpyxl") is None:
            self.skipTest("openpyxl não instalado no ambiente de teste.")
        hoje = timezone.localdate()
        mes_anterior = (hoje.replace(day=1) - timedelta(days=1)).replace(day=10)

        self._nova_reserva(self.sala_1, hoje, "Ana")
        self._nova_reserva(self.sala_2, mes_anterior, "Bruno")

        response = self.client.get(
            reverse("reservas_dashboard_exportar"),
            {"mes_ref": hoje.strftime("%m/%Y")},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", response["Content-Type"])
        self.assertIn(".xlsx", response["Content-Disposition"])
        self.assertGreater(len(response.content), 0)

    def test_dashboard_exportar_filtra_por_sala(self):
        if importlib.util.find_spec("openpyxl") is None:
            self.skipTest("openpyxl não instalado no ambiente de teste.")
        hoje = timezone.localdate()
        self._nova_reserva(self.sala_1, hoje, "Ana")
        self._nova_reserva(self.sala_2, hoje, "Bruno")

        response = self.client.get(
            reverse("reservas_dashboard_exportar"),
            {"sala_nome": self.sala_2.nome},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", response["Content-Type"])
        self.assertIn(".xlsx", response["Content-Disposition"])
        self.assertGreater(len(response.content), 0)

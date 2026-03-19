from datetime import date, datetime
from unittest.mock import patch

from django.test import SimpleTestCase
from django.utils import timezone

from .views import _dias_desde


class DiasDesdeTests(SimpleTestCase):
    def test_retorna_um_dia_quando_foi_atualizado_ontem_mesmo_com_menos_de_24h(self):
        atualizado_em = timezone.make_aware(datetime(2026, 3, 9, 15, 12))
        with patch("diario_bordo.views.timezone.localdate", return_value=date(2026, 3, 10)):
            self.assertEqual(_dias_desde(atualizado_em), 1)

    def test_retorna_zero_quando_atualizado_no_mesmo_dia(self):
        atualizado_em = timezone.make_aware(datetime(2026, 3, 10, 1, 0))
        with patch("diario_bordo.views.timezone.localdate", return_value=date(2026, 3, 10)):
            self.assertEqual(_dias_desde(atualizado_em), 0)
